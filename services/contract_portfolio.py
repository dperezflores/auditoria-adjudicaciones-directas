"""Portafolio contractual para el dashboard de Resultados.

Una fila representa un contrato extraído (no una carpeta ni un PDF
sin analizar). Datos sólo de Google Sheets; sin llamadas a Drive o Gemini.
Se incluyen exclusivamente documentos activos y la extracción vinculada
a su versión actual; las respuestas históricas no se suman dos veces.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
import re
import unicodedata
from typing import Any, Mapping, Sequence

from services.sync_engine import HEADERS as INVENTORY_HEADERS
from services.extraction_store import EXTRACTION_HEADERS, CONTRACT_HEADERS
from services.document_links import SupportingDocument, build_supporting_documents
from services.contract_v2 import (
    CONTRACT_V2_FIELDS, CONTRACT_V2_HEADERS, ContractExtractionV2,
    classify_cited_regime,
)


class PortfolioError(ValueError):
    """Los registros de la hoja maestra requieren revisión."""


FIELD_LABELS: tuple[tuple[str, str], ...] = (
    ("numero_contrato", "Número de contrato"),
    ("nombre_obra", "Nombre de la obra"),
    ("contratista", "Contratista"),
    ("fecha_firma", "Fecha de firma"),
    ("fecha_inicio", "Inicio de obra"),
    ("fecha_termino", "Término de obra"),
    ("monto_con_iva", "Monto con IVA"),
    ("porcentaje_anticipo", "Anticipo"),
)
DATA_FIELDS = tuple(name for name, _ in FIELD_LABELS)
HEADERS = {
    "Obras": INVENTORY_HEADERS["Obras"],
    "Documentos": INVENTORY_HEADERS["Documentos"],
    "Extracciones": EXTRACTION_HEADERS,
    "DatosContrato": CONTRACT_HEADERS,
    "DatosContratoV2": CONTRACT_V2_HEADERS,
}


@dataclass(frozen=True)
class ContractRecord:
    obra_id: str
    documento_id: str
    cache_key: str
    nombre_carpeta: str
    documento: str
    values: Mapping[str, str]
    evidence: Mapping[str, Mapping[str, Any]]
    observations: tuple[str, ...]
    state: str
    extracted_at: str
    completeness: int
    amount: Decimal | None
    currency: str
    signature_year: str
    source_schema: str = "contrato-v1"
    full_values: Mapping[str, str] | None = None
    participants: tuple[Mapping[str, Any], ...] = ()
    normative_scope: str = "No determinado"

    @property
    def missing_fields(self) -> tuple[str, ...]:
        if self.full_values is not None:
            return tuple(
                name for name in CONTRACT_V2_FIELDS
                if not self.full_values.get(name, "").strip()
            )
        return tuple(name for name in DATA_FIELDS if not self.values.get(name, "").strip())

    @property
    def coverage(self) -> str:
        length = len(CONTRACT_V2_FIELDS) if self.full_values is not None else len(DATA_FIELDS)
        return f"{self.completeness}/{length}"

    @property
    def status_label(self) -> str:
        if self.source_schema == "contrato-v2":
            return (
                "Contrato ampliado · datos incompletos"
                if self.completeness < len(CONTRACT_V2_FIELDS)
                else "Contrato ampliado · pendiente de verificar"
            )
        if self.source_schema == "documento-schema-v1":
            return (
                "Contrato identificado · datos incompletos"
                if self.completeness < len(DATA_FIELDS)
                else "Contrato identificado · extracción general"
            )
        if self.state == "REQUIERE_REVISION":
            return "Recuperación parcial"
        if self.completeness < len(DATA_FIELDS):
            return "Datos incompletos"
        return "Extraído · pendiente de verificar"


@dataclass(frozen=True)
class ContractPortfolio:
    records: tuple[ContractRecord, ...]
    supporting_documents: tuple[SupportingDocument, ...] = ()

    @property
    def works_count(self) -> int:
        return len({record.obra_id for record in self.records})

    @property
    def missing_count(self) -> int:
        return sum(len(record.missing_fields) for record in self.records)

    @property
    def partial_count(self) -> int:
        return sum(record.state == "REQUIERE_REVISION" for record in self.records)


def _map_rows(name: str, values: Sequence[Sequence[Any]]) -> list[dict[str, str]]:
    expected = HEADERS[name]
    if not values or tuple(map(str, values[0][:len(expected)])) != expected:
        raise PortfolioError(f"Encabezados incompatibles en {name}.")
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in values[1:]:
        cells = ["" if v is None else str(v) for v in raw[:len(expected)]]
        cells += [""] * (len(expected) - len(cells))
        if not any(cells):
            continue
        row = dict(zip(expected, cells))
        identifier = row[expected[0]]
        if not identifier:
            raise PortfolioError(f"Identificador vacío en {name}.")
        if name not in ("DatosContrato", "DatosContratoV2") and identifier in seen:
            raise PortfolioError(f"Identificador duplicado en {name}.")
        seen.add(identifier)
        result.append(row)
    return result


def parse_amount(raw: str) -> Decimal | None:
    """Interpretar sólo una cantidad explícita; no inferir valores faltantes."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    # Los contratos mexicanos suelen duplicar el importe en letras:
    # "$2,231,632.00 (DOS MILLONES... PESOS 00/100 M.N.)".
    # "00/100" expresa centavos, NO otro monto. Ignorarlo solamente
    # para el cálculo derivado; la transcripción literal permanece intacta.
    cleaned = re.sub(r"\b\d{1,2}\s*/\s*100\b", " ", raw)
    candidates = re.findall(r"\d[\d.,]*", cleaned)
    candidates = [x.rstrip(".,") for x in candidates if x.rstrip(".,")]
    # Si hay dos cifras diferentes, no elegir arbitrariamente una.
    if len(candidates) != 1:
        return None
    value = candidates[0]
    last_comma, last_dot = value.rfind(","), value.rfind(".")
    if last_comma >= 0 and last_dot >= 0:
        decimal_separator = "," if last_comma > last_dot else "."
    elif last_comma >= 0:
        decimal_separator = "," if len(value) - last_comma - 1 in (1, 2) else ""
    elif last_dot >= 0:
        decimal_separator = "." if len(value) - last_dot - 1 in (1, 2) else ""
    else:
        decimal_separator = ""
    normalized = value
    if decimal_separator == ",":
        normalized = normalized.replace(".", "").replace(",", ".")
    elif decimal_separator == ".":
        normalized = normalized.replace(",", "")
    else:
        normalized = normalized.replace(",", "").replace(".", "")
    try:
        amount = Decimal(normalized)
    except InvalidOperation:
        return None
    return amount if amount >= 0 else None


def currency_group(raw: str) -> str:
    normalized = unicodedata.normalize("NFKD", raw.upper())
    normalized = "".join(x for x in normalized if not unicodedata.combining(x))
    if re.search(r"\b(USD|DOLARES|DOLLARS|DOLAR)\b", normalized):
        return "USD"
    if "€" in normalized or re.search(r"\b(EUR|EUROS)\b", normalized):
        return "EUR"
    if re.search(r"\b(MXN|PESOS|PESO)\b", normalized):
        return "MXN"
    return "Sin divisa indicada"


def signature_year(text: str) -> str:
    years = re.findall(r"(?:19|20)\d{2}", text)
    return years[0] if len(set(years)) == 1 and years else "Sin año"


def _normalize_field(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    return " ".join(
        "".join(c for c in normalized if not unicodedata.combining(c)).split()
    )


def _contract_from_general_json(
    raw_json: str,
) -> tuple[dict[str, str], dict[str, dict[str, Any]], tuple[str, ...]] | None:
    """Adaptar la ficha general de un contrato sin llamadas adicionales a IA.

    Solo admite hechos explícitos, nunca fechas/montos inferidos del nombre
    o la carpeta. Mantiene página y fragmento de evidencia tal como se
    guardaron. Los importes se etiquetan con IVA sólo si es explícito.
    """
    try:
        payload = json.loads(raw_json)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    category = _normalize_field(str(payload.get("tipo_documental") or ""))
    if not re.search(r"\bcontrato\b", category) or "obra" not in category:
        return None
    facts = payload.get("campos")
    if not isinstance(facts, list):
        return None

    aliases = {
        "numero_contrato": (
            "numero de contrato", "numero del contrato", "no de contrato",
            "numero contrato", "folio de contrato",
        ),
        "nombre_obra": (
            "objeto de la obra", "nombre de la obra", "nombre de obra",
            "objeto del contrato", "obra contratada",
        ),
        "contratista": (
            "contratista", "nombre del contratista", "razon social del contratista",
            "nombre o razon social del contratista",
        ),
        "fecha_firma": (
            "fecha de firma del contrato", "fecha de firma",
            "fecha de suscripcion", "fecha del contrato",
        ),
        "fecha_inicio": (
            "fecha de inicio de obra", "fecha de inicio de la obra",
            "fecha de inicio", "inicio de los trabajos",
        ),
        "fecha_termino": (
            "fecha de terminacion de obra", "fecha de termino",
            "fecha de terminacion", "termino de los trabajos",
            "fecha de conclusion",
        ),
        "monto_con_iva": (
            "monto del contrato", "monto de contrato",
            "monto con iva", "importe del contrato", "importe total con iva",
        ),
        "porcentaje_anticipo": (
            "anticipo", "porcentaje de anticipo", "porcentaje del anticipo",
        ),
    }
    normalized_aliases = {
        key: {_normalize_field(label) for label in labels}
        for key, labels in aliases.items()
    }
    values = {field: "" for field in DATA_FIELDS}
    evidence: dict[str, dict[str, Any]] = {}
    summary = _normalize_field(str(payload.get("resumen") or ""))
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        label = _normalize_field(str(fact.get("campo") or ""))
        value = fact.get("valor")
        if not isinstance(value, str) or not value.strip():
            continue
        for field in DATA_FIELDS:
            if label not in normalized_aliases[field] or values[field]:
                continue
            if field == "monto_con_iva":
                # No asumir IVA por tratarse de contrato mexicano.
                # Exigir que se indique para el mismo importe extraído.
                quote = _normalize_field(str(fact.get("evidencia") or ""))
                nearby = (
                    re.search(r"\biva\b", label)
                    or ("iva incluido" in quote and value.casefold() in str(fact.get("evidencia") or "").casefold())
                    or ("iva incluido" in summary and value.casefold() in str(payload.get("resumen") or "").casefold())
                )
                if not nearby:
                    continue
            values[field] = value.strip()
            evidence[field] = {
                "pagina": fact.get("pagina") if isinstance(fact.get("pagina"), int) else None,
                "evidencia": fact.get("evidencia") if isinstance(fact.get("evidencia"), str) else None,
                "valor": value.strip(),
            }
            break

    if not any(values.values()):
        return None
    alerts = payload.get("alertas")
    notes = tuple(str(item) for item in alerts[:12] if isinstance(item, str)) if isinstance(alerts, list) else ()
    return values, evidence, (
        "El contrato fue identificado mediante la extracción documental general; "
        "sus campos se normalizaron sin otra solicitud a Gemini.",
        *notes,
    )


def prepare_contract_portfolio(
    tables: Mapping[str, Sequence[Sequence[Any]]],
) -> ContractPortfolio:
    try:
        parsed = {name: _map_rows(name, tables[name]) for name in HEADERS}
    except KeyError as exc:
        raise PortfolioError("Falta una pestaña de la hoja maestra.") from exc

    works = {
        r["obra_id"]: r for r in parsed["Obras"] if r["activo"] == "SI"
    }
    documents = {
        r["documento_id"]: r for r in parsed["Documentos"]
        if r["activo"] == "SI" and r["obra_id"] in works
    }
    analyses = {r["cache_key"]: r for r in parsed["Extracciones"]}
    records: list[ContractRecord] = []
    seen_current: set[tuple[str, str]] = set()
    for item in parsed["DatosContrato"]:
        document = documents.get(item["documento_id"])
        if document is None or document["obra_id"] != item["obra_id"]:
            continue
        if document["mime_type"] != "application/pdf":
            continue
        if (
            document["resultado_id"] != item["cache_key"]
            or document["estado_procesamiento"] == "Modificado desde el último análisis"
        ):
            continue
        key = (item["documento_id"], item["cache_key"])
        if key in seen_current:
            raise PortfolioError("La versión de un contrato aparece duplicada.")
        seen_current.add(key)
        analysis = analyses.get(item["cache_key"])
        if not analysis or analysis["estado"] not in (
            "COMPLETADO", "REQUIERE_REVISION"
        ):
            continue
        if (
            analysis["documento_id"] != item["documento_id"]
            or analysis["obra_id"] != item["obra_id"]
            or analysis["version_esquema"] != "contrato-v1"
        ):
            continue

        evidence: dict[str, dict[str, Any]] = {}
        observations: tuple[str, ...] = ()
        if analysis["estado"] == "COMPLETADO":
            if not analysis["resultado_json"]:
                continue
            try:
                output = json.loads(analysis["resultado_json"])
                if not isinstance(output, dict):
                    continue
                evidence = {
                    field: output[field]
                    for field in DATA_FIELDS
                    if isinstance(output.get(field), dict)
                }
                observations = tuple(
                    str(entry) for entry in output.get("observaciones", [])
                    if isinstance(entry, str)
                )[:20]
            except (TypeError, ValueError):
                # JSON corrupto no entra al dashboard de resultados operativos.
                continue

        values = {field: item[field].strip() for field in DATA_FIELDS}
        if not any(values.values()):
            continue
        amount = parse_amount(values["monto_con_iva"])
        records.append(ContractRecord(
            obra_id=item["obra_id"],
            documento_id=item["documento_id"],
            cache_key=item["cache_key"],
            nombre_carpeta=works[item["obra_id"]]["nombre_carpeta"],
            documento=document["nombre_archivo"],
            values=values,
            evidence=evidence,
            observations=observations,
            state=analysis["estado"],
            extracted_at=item["extraido_utc"] or analysis["actualizado_utc"],
            completeness=sum(bool(v) for v in values.values()),
            amount=amount,
            currency=currency_group(values["monto_con_iva"]),
            signature_year=signature_year(values["fecha_firma"]),
        ))
    # Nueva plantilla: datos literales y participantes almacenados en v2.
    # La salida estructurada de v1 y fichas generales siguen disponibles.
    current_v2: set[str] = set()
    for row in parsed["DatosContratoV2"]:
        doc_id, obra_id, key = row["documento_id"], row["obra_id"], row["cache_key"]
        document = documents.get(doc_id)
        if (
            not document or document["obra_id"] != obra_id
            or document["resultado_id"] != key
            or document["estado_procesamiento"] == "Modificado desde el último análisis"
            or document["mime_type"] != "application/pdf"
        ):
            continue
        source = analyses.get(key)
        if not source or (
            source["version_esquema"] != "contrato-v2"
            or source["estado"] != "COMPLETADO"
            or not source["resultado_json"]
            or source["documento_id"] != doc_id
            or source["obra_id"] != obra_id
        ):
            continue
        if doc_id in current_v2:
            raise PortfolioError("Un PDF tiene varias filas contractuales v2 vigentes.")
        try:
            result = ContractExtractionV2.model_validate_json(source["resultado_json"])
        except (ValueError, TypeError):
            continue
        raw = {name: row[name] for name in CONTRACT_V2_FIELDS}
        # El JSON completo constituye el registro fuente; mantener idénticos
        # los datos del listado a los valores literales entregados por Gemini.
        if any(raw[name] != (getattr(result, name).valor or "") for name in CONTRACT_V2_FIELDS):
            raise PortfolioError(
                "Los datos del contrato v2 no coinciden con su extracción original."
            )
        # Un PDF de PUC, dictamen o anexo también puede pasar por el
        # extractor fijo de 16 campos. Solo debe incorporarse al dashboard
        # cuando el contenido respalda que hay un contrato identificado.
        # Un RFC aislado o un nombre de empresa no basta.
        if not (
            raw["numero_contrato"]
            or (raw["obra_servicio"] and raw["monto_contrato"])
        ):
            continue
        legacy_view = {
            "numero_contrato": raw["numero_contrato"],
            "nombre_obra": raw["obra_servicio"],
            "contratista": raw["contratista"],
            "fecha_firma": raw["fecha_firma_contrato"],
            "fecha_inicio": raw["fecha_inicio_contractual"],
            "fecha_termino": raw["fecha_termino_contractual"],
            "monto_con_iva": raw["monto_contrato"],
            "porcentaje_anticipo": raw["anticipo"],
        }
        record_evidence = {
            name: getattr(result, name).model_dump(mode="json")
            for name in CONTRACT_V2_FIELDS
        }
        records.append(ContractRecord(
            obra_id=obra_id, documento_id=doc_id, cache_key=key,
            nombre_carpeta=works[obra_id]["nombre_carpeta"],
            documento=document["nombre_archivo"],
            values=legacy_view, evidence=record_evidence,
            observations=tuple(result.observaciones),
            state=source["estado"],
            extracted_at=row["extraido_utc"] or source["actualizado_utc"],
            completeness=sum(bool(v) for v in raw.values()),
            amount=parse_amount(raw["monto_contrato"]),
            currency=currency_group(raw["monto_contrato"]),
            signature_year=signature_year(raw["fecha_firma_contrato"]),
            source_schema="contrato-v2",
            full_values=raw,
            participants=tuple(
                participant.model_dump(mode="json")
                for participant in result.personas_participantes
            ),
            normative_scope=classify_cited_regime(raw["legislacion_citada"]),
        ))
        current_v2.add(doc_id)
    records.sort(
        key=lambda r: (r.signature_year, r.values["numero_contrato"], r.documento_id),
        reverse=True,
    )
    # Si alguna extracción antigua aún sigue activa para el mismo PDF,
    # el resultado v2 prevalece sin mostrar dos contratos.
    if current_v2:
        records = [
            r for r in records
            if r.documento_id not in current_v2 or r.source_schema == "contrato-v2"
        ]
    # Algunos contratos reales tienen nombres abreviados como CNT_DIR_CNT.pdf.
    # El analizador general los reconoce por contenido y guarda en Extracciones,
    # pero no crea una fila en DatosContrato. Incorporar esos resultados sin
    # volver a llamar a Gemini ni modificar Google Sheets.
    current_docs = {record.documento_id for record in records}
    for analysis in parsed["Extracciones"]:
        if (
            analysis["version_esquema"] != "documento-schema-v1"
            or analysis["estado"] != "COMPLETADO"
            or not analysis["resultado_json"]
        ):
            continue
        doc_id, obra_id = analysis["documento_id"], analysis["obra_id"]
        document = documents.get(doc_id)
        if (
            not document or doc_id in current_docs
            or document["obra_id"] != obra_id
            or document["resultado_id"] != analysis["cache_key"]
            or document["estado_procesamiento"] == "Modificado desde el último análisis"
            or document["mime_type"] != "application/pdf"
        ):
            continue
        normalized = _contract_from_general_json(analysis["resultado_json"])
        if normalized is None:
            continue
        values, evidence, observations = normalized
        records.append(ContractRecord(
            obra_id=obra_id,
            documento_id=doc_id,
            cache_key=analysis["cache_key"],
            nombre_carpeta=works[obra_id]["nombre_carpeta"],
            documento=document["nombre_archivo"],
            values=values,
            evidence=evidence,
            observations=observations,
            state=analysis["estado"],
            extracted_at=analysis["actualizado_utc"],
            completeness=sum(bool(v) for v in values.values()),
            amount=parse_amount(values["monto_con_iva"]),
            currency=currency_group(values["monto_con_iva"]),
            signature_year=signature_year(values["fecha_firma"]),
            source_schema="documento-schema-v1",
        ))
        current_docs.add(doc_id)
    records.sort(
        key=lambda r: (r.signature_year, r.values["numero_contrato"], r.documento_id),
        reverse=True,
    )
    return ContractPortfolio(
        tuple(records),
        build_supporting_documents(
            parsed["Obras"], parsed["Documentos"], parsed["Extracciones"]
        ),
    )


def read_contract_portfolio(client: Any, spreadsheet_id: str) -> ContractPortfolio:
    """Una lectura batchGet; jamás consulta Drive ni la API Gemini."""
    ranges = [
        f"'{name}'!A1:{chr(64 + len(headers))}"
        for name, headers in HEADERS.items()
    ]
    response = client.spreadsheets().values().batchGet(
        spreadsheetId=spreadsheet_id,
        ranges=ranges,
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    parts = response.get("valueRanges") or []
    if len(parts) != len(ranges):
        raise PortfolioError("Google Sheets no devolvió todas las tablas.")
    return prepare_contract_portfolio({
        name: parts[i].get("values") or []
        for i, name in enumerate(HEADERS)
    })


def filter_contracts(
    portfolio: ContractPortfolio, *, query: str = "", year: str = "Todos",
    contractor: str = "Todos", status: str = "Todos",
) -> tuple[ContractRecord, ...]:
    normalized_query = unicodedata.normalize("NFKD", query.casefold())
    normalized_query = "".join(
        ch for ch in normalized_query if not unicodedata.combining(ch)
    ).strip()
    chosen: list[ContractRecord] = []
    for record in portfolio.records:
        haystack = " ".join((
            record.nombre_carpeta,
            record.values["nombre_obra"],
            record.values["numero_contrato"],
            record.values["contratista"],
        ))
        haystack = unicodedata.normalize("NFKD", haystack.casefold())
        haystack = "".join(ch for ch in haystack if not unicodedata.combining(ch))
        if normalized_query and normalized_query not in haystack:
            continue
        if year != "Todos" and record.signature_year != year:
            continue
        if contractor != "Todos" and record.values["contratista"] != contractor:
            continue
        if status != "Todos" and record.status_label != status:
            continue
        chosen.append(record)
    return tuple(chosen)


def amount_summary(records: Sequence[ContractRecord]) -> tuple[Decimal | None, str, int]:
    """Jamás suma importes de monedas distintas o no interpretables."""
    amounts = [r for r in records if r.amount is not None]
    currencies = {r.currency for r in amounts}
    unparsed = len(records) - len(amounts)
    # MXN explícito + otro importe con el símbolo $ sin código de
    # moneda: sumar solo PRELIMINARMENTE y advertir la incertidumbre.
    # Nunca equiparar USD, EUR u otras divisas distintas de manera implícita.
    provisional_mxn = (
        currencies == {"MXN", "Sin divisa indicada"}
        and all(
            "$" in record.values.get("monto_con_iva", "")
            for record in amounts if record.currency == "Sin divisa indicada"
        )
    )
    if len(currencies) > 1 and not provisional_mxn:
        return None, "Monedas distintas o no homologables; no se sumaron.", unparsed
    if not amounts:
        return None, "Sin importes numéricos interpretables.", unparsed
    total = sum((r.amount for r in amounts if r.amount is not None), Decimal("0"))
    if provisional_mxn:
        explanation = (
            "Suma provisional: algunos montos citan pesos mexicanos y otros "
            "solo incluyen el símbolo $. Verifica que todos estén en la "
            "misma moneda antes de utilizar el total."
        )
    else:
        group = next(iter(currencies))
        explanation = (
            "Moneda sin identificar; total preliminar de cifras expresadas con $."
            if group == "Sin divisa indicada"
            else f"Importes declarados en {group}, no validados."
        )
    if unparsed:
        explanation += f" {unparsed} contrato(s) sin monto interpretable se excluyeron."
    return total, explanation, unparsed


def money_text(value: Decimal | None, currency: str = "") -> str:
    if value is None:
        return "—"
    if currency == "EUR":
        return f"€{value:,.2f}"
    if currency in ("USD", "MXN"):
        return f"${value:,.2f} {currency}"
    return f"${value:,.2f}"
