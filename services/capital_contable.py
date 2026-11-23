"""Prueba CC-01: capital contable en el PUC frente al 30 % de una AD.

Alcance: Manual DGOP León PR-DGOP/DACF-011, rev. 02, sección 3, hoja 2.
El manual exige capital registrado en el PUC a fecha de asignación.
Separamos el RESULTADO ARITMÉTICO de la COMPROBACIÓN HISTÓRICA.

Solo lee tablas guardadas de Sheets. No descarga ni envía documentos a Gemini,
no altera la extracción original ni presume que un PUC posterior acredita
el capital efectivamente registrado en la asignación.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
import re
import unicodedata
from typing import Any, Mapping, Sequence

from services.contract_display import normalize_award_method, short_date
from services.contract_normalization import normalized_values
from services.contract_portfolio import ContractRecord, currency_group, parse_amount
from services.dictamen_schema import DICTAMEN_HEADERS
from services.extraction_store import EXTRACTION_HEADERS
from services.puc_schema import PUC_HEADERS, PUC_SCHEMA_VERSION, PucExtractionV1
from services.sheets_service import _last_column
from services.sync_engine import HEADERS as INVENTORY_HEADERS
from services.puc_history import PucReview


CAPITAL_RATIO = Decimal("0.30")
CENT = Decimal("0.01")
MANUAL_CODE = "PR-DGOP/DACF-011 · Rev. 02 · sección 3, hoja 2"
MANUAL_URL = (
    "https://www.leon.gob.mx/modulos/img/documentos/obrapublica/"
    "procedimientos%20y%20formatos/Manual%20de%20procesos%20y%20procedimientos/"
    "14.%20Contrataci%C3%B3n%20de%20obra%20p%C3%BAblica%20y%20servicios%20"
    "por%20adjudicaci%C3%B3n%20directa/"
    "Procedimiento%20rev02%20Act.%2012-08-2022.pdf"
)


class CapitalSourceError(ValueError):
    pass


@dataclass(frozen=True)
class PucEntry:
    obra_id: str
    documento_id: str
    cache_key: str
    nombre: str
    rfc: str
    registro: str
    capital_text: str
    capital: Decimal | None
    capital_page: int | None
    capital_evidence: str
    fecha_validacion: str
    fecha_impresion: str
    vigencia_desde: str
    vigencia_hasta: str
    estado_registro: str
    version: str


@dataclass(frozen=True)
class AssignmentEvidence:
    fecha: str
    fuente: str
    monto: str


@dataclass(frozen=True)
class CapitalSources:
    puc_by_work: Mapping[str, PucEntry]
    issues_by_work: Mapping[str, str]
    assignments: Mapping[str, AssignmentEvidence]


@dataclass(frozen=True)
class CapitalResult:
    state: str
    comparison: str
    historical: str
    contract_amount: Decimal | None
    requirement: Decimal | None
    capital: Decimal | None
    difference: Decimal | None
    coverage: Decimal | None
    puc: PucEntry | None
    assignment: AssignmentEvidence | None
    notes: tuple[str, ...]
    capital_constancia: Decimal | None = None
    capital_historico_acreditado: bool = False
    revision: PucReview | None = None


def _decode_table(values: Sequence[Sequence[Any]], headers: tuple[str, ...], name: str) -> list[dict[str, str]]:
    if not values or tuple(str(h) for h in values[0][:len(headers)]) != headers:
        raise CapitalSourceError(f"Encabezados de {name} incompatibles con el extractor.")
    records = []
    for line in values[1:]:
        padded = [str(x) if x is not None else "" for x in line[:len(headers)]]
        padded += [""] * (len(headers) - len(padded))
        if not any(padded):
            continue
        records.append(dict(zip(headers, padded)))
    return records


def read_capital_sources(client: Any, spreadsheet_id: str) -> CapitalSources:
    """Lee los PUC y dictámenes vigentes de la misma obra en una solicitud.

    La identidad exacta de obra/documento/resultado_id es obligatoria:
    no se mezcla un PUC de otra carpeta ni una versión histórica.
    """
    tables = {
        "Documentos": INVENTORY_HEADERS["Documentos"],
        "Extracciones": EXTRACTION_HEADERS,
        "DatosPUC": PUC_HEADERS,
        "DatosDictamenAD": DICTAMEN_HEADERS,
    }
    names = list(tables)
    ranges = [
        f"'{name}'!A1:{_last_column(len(tables[name]))}" for name in names
    ]
    response = client.spreadsheets().values().batchGet(
        spreadsheetId=spreadsheet_id, ranges=ranges,
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    groups = response.get("valueRanges") or []
    if len(groups) != len(names):
        raise CapitalSourceError("Google Sheets no devolvió todas las pestañas PUC/dictamen.")
    parsed = {
        name: _decode_table(groups[i].get("values") or [], tables[name], name)
        for i, name in enumerate(names)
    }

    doc_rows = [
        row for row in parsed["Documentos"]
        if row["activo"] == "SI" and row["tipo_documental"] == "PUC"
    ]
    extraction_by_key = {row["cache_key"]: row for row in parsed["Extracciones"]}
    data_by_key = {row["cache_key"]: row for row in parsed["DatosPUC"]}
    puc_by_work: dict[str, PucEntry] = {}
    issues: dict[str, str] = {}
    grouped: dict[str, list[dict[str, str]]] = {}
    for doc in doc_rows:
        grouped.setdefault(doc["obra_id"], []).append(doc)

    for obra_id, docs in grouped.items():
        if len(docs) != 1:
            issues[obra_id] = (
                "Hay varios documentos PUC activos en la misma obra; "
                "identificar cuál acredita la situación en la adjudicación."
            )
            continue
        document = docs[0]
        if document["estado_procesamiento"] == "Modificado desde el último análisis":
            issues[obra_id] = "El PDF del PUC cambió después de la extracción guardada."
            continue
        key = document["resultado_id"]
        if not key:
            issues[obra_id] = "PUC localizado, pero aún no analizado."
            continue
        analysis = extraction_by_key.get(key)
        flat = data_by_key.get(key)
        if not analysis or not flat or any((
            analysis["documento_id"] != document["documento_id"],
            flat["documento_id"] != document["documento_id"],
            analysis["obra_id"] != obra_id, flat["obra_id"] != obra_id,
            analysis["version_esquema"] != PUC_SCHEMA_VERSION,
            analysis["estado"] != "COMPLETADO",
            not analysis["resultado_json"],
        )):
            issues[obra_id] = (
                "PUC sin extracción completa y vigente vinculada a la obra; "
                "analizar o cotejar el documento."
            )
            continue
        try:
            extraction = PucExtractionV1.model_validate_json(analysis["resultado_json"])
        except Exception:
            issues[obra_id] = "Los campos del PUC guardado no cumplen el esquema documental."
            continue
        capital_field = extraction.capital_contable
        capital = parse_amount(capital_field.valor or "")
        raw_currency = currency_group(capital_field.valor or "")
        if raw_currency in ("USD", "EUR"):
            capital = None
        puc_by_work[obra_id] = PucEntry(
            obra_id=obra_id, documento_id=document["documento_id"],
            cache_key=key,
            nombre=extraction.contratista.valor or "",
            rfc=extraction.rfc.valor or "",
            registro=extraction.numero_registro_puc.valor or "",
            capital_text=capital_field.valor or "",
            capital=capital,
            capital_page=capital_field.pagina,
            capital_evidence=capital_field.evidencia or "",
            fecha_validacion=extraction.fecha_validacion.valor or "",
            fecha_impresion=extraction.fecha_impresion.valor or "",
            vigencia_desde=extraction.vigencia_desde.valor or "",
            vigencia_hasta=extraction.vigencia_hasta.valor or "",
            estado_registro=extraction.estado_registro.valor or "",
            version=analysis["version_prompt"],
        )

    assignments: dict[str, AssignmentEvidence] = {}
    dictamen_rows: dict[str, list[dict[str, str]]] = {}
    for doc in parsed["Documentos"]:
        if doc["activo"] == "SI" and doc["tipo_documental"] == "DICTAMEN_AD":
            dictamen_rows.setdefault(doc["obra_id"], []).append(doc)
    dictamen_data = {row["cache_key"]: row for row in parsed["DatosDictamenAD"]}
    for obra_id, docs in dictamen_rows.items():
        if len(docs) != 1:
            continue
        d = docs[0]
        key = d["resultado_id"]
        a = extraction_by_key.get(key)
        row = dictamen_data.get(key)
        if (
            a and row and a["estado"] == "COMPLETADO"
            and a["version_esquema"] == "dictamen-ad-v1"
            and a["obra_id"] == row["obra_id"] == obra_id
            and a["documento_id"] == row["documento_id"] == d["documento_id"]
        ):
            assignments[obra_id] = AssignmentEvidence(
                fecha=row["fecha_emision"],
                fuente="Fecha de emisión del dictamen AD (referencia, no asignación definitiva)",
                monto=row["monto_asignado"],
            )
    return CapitalSources(puc_by_work, issues, assignments)


def _fold(raw: str) -> str:
    s = unicodedata.normalize("NFKD", str(raw or "").casefold())
    return "".join(ch for ch in s if not unicodedata.combining(ch))


def _identity(raw: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", _fold(raw).upper())


def _puc_date(raw: str) -> date | None:
    normalized = short_date(raw or "")
    try:
        return datetime.strptime(normalized, "%d/%m/%Y").date()
    except ValueError:
        return None


def _historical(
    puc: PucEntry,
    reference: AssignmentEvidence | None,
    signature: str,
    review: PucReview | None = None,
) -> tuple[str, tuple[str, ...]]:
    """El capital de una cédula actual NO se presume vigente en el pasado.

    Validación/impresión de la cédula son metadatos, no fecha de alta de capital.
    El historial requiere monto y fecha de registro soportados en fuente
    documentada y una fecha de asignación efectivamente cotejada.
    """
    notes = []
    decision_date = _puc_date(review.fecha_asignacion) if review else None
    if not decision_date:
        decision_date = _puc_date(reference.fecha) if reference else None
        if decision_date:
            notes.append(
                "La fecha del dictamen es preliminar, no acredita por sí "
                "sola la fecha efectiva de asignación."
            )
        else:
            decision_date = _puc_date(signature)
            notes.append(
                "Sin fecha de asignación acreditada; firma usada solo como "
                "referencia contextual, no como fecha de cumplimiento."
            )

    if puc.fecha_impresion:
        notes.append(
            "La fecha de impresión no acredita ni desacredita cuándo se "
            "inscribió el capital contable ante el padrón."
        )
    if puc.fecha_validacion:
        notes.append(
            "La validación de la cédula no prueba cuándo se actualizó "
            "el importe del capital contable."
        )

    if not review or not review.capital_historico:
        return "Capital histórico por acreditar", tuple(notes + [
            "Solicitar historial de capital registrado ante el PUC a fecha "
            "de asignación; no basta la cifra de la constancia disponible."
        ])
    if not review.fecha_asignacion:
        return "Fecha de asignación por acreditar", tuple(notes + [
            "Registrar la fecha efectiva de asignación con fuente y evidencia."
        ])
    registered = _puc_date(review.fecha_registro_capital)
    if not decision_date or not registered:
        return "Capital histórico por acreditar", tuple(notes + [
            "Falta fecha verificable de asignación o registro del capital."
        ])
    if registered > decision_date:
        return "Actualización del capital posterior a la asignación", tuple(notes + [
            "La cifra histórica aportada se registró después de adjudicar; "
            "no puede acreditar retroactivamente el 30 %."
        ])
    if not review.fuente or not review.referencia:
        return "Capital histórico por acreditar", tuple(notes + [
            "Faltan fuente y referencia verificable de la actualización."
        ])
    return "Capital histórico documentado (preliminar)", tuple(notes + [
        "Verificar autenticidad, integridad y antecedentes del historial "
        "aportado por el auditor antes de concluir sobre cumplimiento."
    ])

def evaluate_capital(
    record: ContractRecord, sources: CapitalSources,
    review: PucReview | None = None,
) -> CapitalResult:
    """Compara 30 % del monto contractual TOTAL, sin convertir a base sin IVA.

    El manual dice «monto total de la obra», sin describir aquí base fiscal.
    Se usa el importe contractual tal como fue extraído/confirmado (no se
    suma IVA si es «sin IVA»). Se advierte para cotejo interpretativo.
    """
    norm, norm_notes = normalized_values(record)
    notes = list(norm_notes)
    method = normalize_award_method(norm.get("modalidad_adjudicacion", ""))
    if method != "ADJUDICACIÓN DIRECTA":
        state = "No aplica" if method in (
            "LICITACIÓN SIMPLIFICADA", "LICITACIÓN PÚBLICA",
            "INVITACIÓN RESTRINGIDA", "CONCURSO SIMPLIFICADO",
        ) else "Requiere revisión"
        return CapitalResult(
            state, "—", "No se aplica el criterio de AD" if state == "No aplica"
            else "Modalidad no identificada", None, None, None, None,
            None, None, None,
            tuple(notes + ["El criterio del manual DGOP corresponde a adjudicación directa."]),
        )

    puc = sources.puc_by_work.get(record.obra_id)
    reference = sources.assignments.get(record.obra_id)
    if review and (review.obra_id != record.obra_id
                   or review.contrato_documento_id != record.documento_id
                   or review.contrato_cache_key != record.cache_key
                   or puc is None or review.puc_documento_id != puc.documento_id
                   or review.puc_cache_key != puc.cache_key):
        notes.append("Revisión histórica de otra versión documental ignorada.")
        review = None
    if review and review.fecha_asignacion:
        reference = AssignmentEvidence(
            fecha=review.fecha_asignacion,
            fuente="Fecha efectiva asentada por auditor en RevisionesPUC",
            monto=reference.monto if reference else "",
        )
    if not puc:
        reason = sources.issues_by_work.get(
            record.obra_id, "No existe PUC analizado y vinculado con esta obra."
        )
        return CapitalResult(
            "Pendiente de PUC", "—", "Sin documento comprobable",
            None, None, None, None, None, None, reference,
            tuple(notes + [reason]),
        )

    raw_amount = norm.get("monto_contrato", "")
    manual = (record.verification or {}).get("campos") or {}
    literal = (
        raw_amount if "monto_contrato" in manual
        else (record.full_values or {}).get("monto_contrato", "") or raw_amount
    )
    foreign = currency_group(literal) in ("USD", "EUR")
    base = parse_amount(raw_amount)
    if foreign:
        base = None
        notes.append("El contrato expresa una divisa distinta de MXN; no se comparan importes.")
    if not base or base <= 0:
        notes.append("No hay un monto contractual positivo inequívoco para determinar el 30 %.")
    if puc.capital is None:
        notes.append("Capital contable no interpretable en el PUC o expresado en otra divisa.")

    contract_rfc = norm.get("rfc", "")
    contract_reg = norm.get("registro_puc", "")
    contract_name = norm.get("contratista", "")
    if contract_rfc and puc.rfc and _identity(contract_rfc) != _identity(puc.rfc):
        notes.append(
            "RFC del contrato y del PUC distintos: cotejar identidad antes de "
            "usar el capital de esa cédula."
        )
        identity_ok = False
    elif contract_reg and puc.registro and _identity(contract_reg) != _identity(puc.registro):
        notes.append("Número PUC del contrato distinto del registro PUC extraído.")
        identity_ok = False
    elif contract_rfc and puc.rfc and _identity(contract_rfc) == _identity(puc.rfc):
        identity_ok = True
    elif contract_reg and puc.registro and _identity(contract_reg) == _identity(puc.registro):
        identity_ok = True
    else:
        identity_ok = False
        notes.append(
            "Identidad del contratista no acreditada por RFC o número de registro "
            "coincidente; cotejar los datos del PUC."
        )

    historical, hist_notes = _historical(
        puc, reference, norm.get("fecha_firma_contrato", ""), review
    )
    notes.extend(hist_notes)
    verified_historical = historical == "Capital histórico documentado (preliminar)"
    historical_capital = (
        parse_amount(review.capital_historico)
        if verified_historical and review else None
    )
    if historical_capital is None:
        notes.append(
            "La comparación aritmética utiliza el capital de la constancia "
            "disponible, NO el capital histórico acreditado."
        )
    compare_capital = historical_capital if historical_capital is not None else puc.capital
    mismatched_assignment = False
    if reference and reference.monto and base is not None:
        assigned = parse_amount(reference.monto)
        if assigned is not None and abs(assigned - base) > CENT:
            mismatched_assignment = True
            notes.append(
                "El importe asignado del dictamen y el monto contractual "
                "no coinciden: cotejar el monto base para calcular el 30 %."
            )
    if norm.get("iva") == "Sin IVA":
        notes.append(
            "El importe contractual está expresado sin IVA: para este cálculo se "
            "utiliza la cantidad contractual citada, sin añadir un impuesto supuesto."
        )
    if base is not None and compare_capital is not None:
        required = (base * CAPITAL_RATIO).quantize(CENT, rounding=ROUND_HALF_UP)
        difference = (compare_capital - required).quantize(CENT, rounding=ROUND_HALF_UP)
        coverage = (compare_capital / base * Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP,
        )
        comparison = "Cubre el 30%" if difference >= 0 else "Capital inferior al 30%"
    else:
        required = difference = coverage = None
        comparison = "Sin datos comparables"
    if not identity_ok:
        state = "Requiere revisión de identidad"
    elif required is None:
        state = "Requiere revisión de importes"
    elif mismatched_assignment:
        state = "Requiere revisión del monto adjudicado"
    elif not verified_historical and (not puc.capital_evidence or puc.capital_page is None):
        state = "Requiere revisión de evidencia del capital"
        notes.append(
            "El capital contable carece de página o cita literal en la extracción PUC."
        )
    elif not verified_historical:
        state = "Capital histórico por acreditar"
    else:
        state = (
            "Capital histórico suficiente (preliminar)"
            if difference is not None and difference >= 0
            else "Capital histórico inferior al 30% (preliminar)"
        )
    return CapitalResult(
        state, comparison, historical, base, required, compare_capital,
        difference, coverage, puc, reference, tuple(notes),
        puc.capital, verified_historical, review,
    )
