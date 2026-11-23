"""Prueba CC-01: capital contable en el PUC frente al 30 % de una AD.

Alcance: Manual DGOP León PR-DGOP/DACF-011, rev. 02, sección 3, hoja 2.
El manual exige capital registrado en el PUC a fecha de asignación.
Primera pasada masiva: la FIRMA del contrato se utiliza como fecha operativa
de asignación; se verifica vigencia anual del PUC y 30 % de capital de la
cédula. La consulta de movimientos históricos ante SOP se deja para una
segunda revisión, salvo que ya exista evidencia que contradiga la hipótesis.

Solo lee tablas guardadas de Sheets; no llama Gemini ni modifica extracciones.
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
    vigencia_puc: str = ""
    vigencia_desde: str = ""
    vigencia_hasta: str = ""


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
    signature: str,
    review: PucReview | None = None,
) -> tuple[str, tuple[str, ...]]:
    """La revisión histórica es complementaria, no requisito de cada lote.

    Si ya consta una certificación oficial y muestra capital distinto, se
    utiliza ese capital únicamente si aplicaba en la fecha de referencia.
    Un registro POSTERIOR documentado bloquea la aprobación automática.
    """
    if not review or not review.capital_historico:
        return "Seguimiento histórico ante SOP: opcional", (
            "La primera revisión usa el capital de la cédula vigente en "
            "la fecha contractual; la confirmación de movimientos históricos "
            "se reservará para una solicitud complementaria a SOP.",
        )
    if review.alcance_capital not in (
        "Historial completo hasta asignación",
        "Certificación oficial del capital a fecha",
    ):
        return "Movimiento aislado: seguimiento ante SOP", (
            "Un movimiento aislado no demuestra el último capital aplicable "
            "a la fecha de firma; el cotejo masivo conserva el dato de la cédula.",
        )

    signed = _puc_date(signature)
    actual_assignment = _puc_date(review.fecha_asignacion)
    # En revisión complementaria no ignorar una fecha efectiva anterior
    # documentada por el auditor. El lote siempre usa la firma.
    reference_date = (
        min(signed, actual_assignment)
        if signed and actual_assignment else signed
    )
    registered = _puc_date(review.fecha_registro_capital)
    if not reference_date or not registered:
        return "Historial SOP con fechas insuficientes", (
            "Falta fecha de firma o fecha oficial del movimiento de capital.",
        )
    if registered > reference_date:
        return "Actualización posterior a la fecha de referencia", (
            "La actualización documentada ocurrió después de la fecha "
            "aplicable; no permite aprobar retroactivamente con ese capital.",
        )
    if not review.fuente or not review.referencia:
        return "Historial SOP sin referencia verificable", (
            "Faltan fuente y soporte identificable del historial.",
        )
    return "Capital histórico complementario documentado", (
        "Importe oficial histórico aplicado a la comparación; revisar "
        "autenticidad y alcance del soporte ante SOP.",
    )

def evaluate_capital(
    record: ContractRecord, sources: CapitalSources,
    review: PucReview | None = None,
) -> CapitalResult:
    """Compara 30 % del monto contractual TOTAL, sin convertir a base sin IVA.

    Se usa el importe contractual tal como fue extraído/confirmado (sin
    sumar IVA supuesto). El 30 % y la vigencia PUC se examinan masivamente
    con fecha de firma como referencia de asignación; la comprobación
    histórica del capital se preserva como etapa complementaria.
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
    # Nunca tomar la emisión del dictamen como fecha primaria: para el
    # examen masivo el usuario ha definido la FIRMA CONTRACTUAL.
    contract_signature = norm.get("fecha_firma_contrato", "")
    reference = (
        AssignmentEvidence(
            fecha=contract_signature,
            fuente="Firma del contrato (referencia operativa de asignación)",
            monto="",
        ) if _puc_date(contract_signature) else None
    )
    if review and (review.obra_id != record.obra_id
                   or review.contrato_documento_id != record.documento_id
                   or review.contrato_cache_key != record.cache_key
                   or puc is None or review.puc_documento_id != puc.documento_id
                   or review.puc_cache_key != puc.cache_key):
        notes.append("Revisión histórica de otra versión documental ignorada.")
        review = None
    notes.append(
        "Primera revisión masiva: fecha de firma usada como fecha "
        "operativa de asignación; movimientos de capital a confirmar "
        "posteriormente con SOP, cuando proceda."
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

    # Motor único de vigencia anual, exactamente igual a la prueba AD-03:
    # firma dentro del periodo PUC, inicio inferido un año antes del
    # vencimiento cuando no se expresa. Import local evita dependencia
    # circular en la carga inicial de los módulos.
    from services.puc_validity import evaluate_puc_validity
    validity = evaluate_puc_validity(record, sources, review)
    notes.extend(validity.notes)
    historical, hist_notes = _historical(puc, contract_signature, review)
    notes.extend(hist_notes)
    verified_historical = historical == "Capital histórico complementario documentado"
    historical_capital = (
        parse_amount(review.capital_historico)
        if verified_historical and review else None
    )
    compare_capital = historical_capital if historical_capital is not None else puc.capital

    # La fecha y el monto del dictamen se conservan como dato de cotejo;
    # una diferencia no invalida por sí sola el cálculo masivo sobre contrato.
    issuance = sources.assignments.get(record.obra_id)
    if issuance and issuance.monto and base is not None:
        assigned = parse_amount(issuance.monto)
        if assigned is not None and abs(assigned - base) > CENT:
            notes.append(
                "El dictamen refiere un importe diferente al contrato; "
                "se calculó el 30 % sobre el contrato y se recomienda cotejo posterior."
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
    elif validity.state == "Fuera del periodo PUC en fecha de firma":
        state = "PUC fuera de vigencia en fecha de firma"
    elif validity.state != "Vigente en fecha de firma":
        state = (
            "Requiere revisión de vigencia PUC"
            if validity.state.startswith("Requiere revisión")
            else "Pendiente de vigencia PUC"
        )
    elif not verified_historical and (not puc.capital_evidence or puc.capital_page is None):
        state = "Requiere revisión de evidencia del capital"
        notes.append(
            "El capital contable carece de página o cita literal en la extracción PUC."
        )
    elif historical == "Actualización posterior a la fecha de referencia":
        state = "Requiere revisión de actualización posterior"
    elif verified_historical:
        state = (
            "Cubre el 30% (historial SOP)"
            if difference is not None and difference >= 0
            else "Capital inferior al 30% (historial SOP)"
        )
    else:
        state = (
            "Cubre el 30% (revisión inicial)"
            if difference is not None and difference >= 0
            else "Capital inferior al 30% (revisión inicial)"
        )
    return CapitalResult(
        state, comparison, historical, base, required, compare_capital,
        difference, coverage, puc, reference, tuple(notes),
        puc.capital, verified_historical, review,
        validity.state, validity.period_from, validity.period_to,
    )
