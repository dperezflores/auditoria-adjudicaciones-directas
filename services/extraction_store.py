"""Registro persistente de extracciones en las pestañas Extracciones y DatosContrato.

Caché por bytes y versión del modelo/prompt/esquema. Sheets no proporciona
bloqueos distribuidos; el llamador DEBE mantener el cerrojo local durante toda
la transacción de reserva + generación + guardado.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any, Callable
from uuid import uuid4

# Mantener estable la caché histórica v1 cuando se publica v2.
PROMPT_VERSION = "contrato-prompt-v3"
from services.contract_schema import ExtraccionContrato, SCHEMA_VERSION
from services.drive_service import DocumentRecord
from services.extraction_cache import CacheKey, crear_clave_cache
from services.gemini_service import DEFAULT_MODEL, GeminiResult, extract_contract
from services.gemini_errors import GeminiRequestError
from services.gemini_compact_schema import CAMPOS_CONTRATO

EXTRACTION_HEADERS = (
    "cache_key", "estado", "documento_id", "obra_id", "sha256_pdf",
    "modelo", "version_prompt", "version_esquema", "creado_utc",
    "actualizado_utc", "resultado_json", "tokens_entrada", "tokens_salida",
    "ultimo_error",
)
CONTRACT_HEADERS = (
    "cache_key", "obra_id", "documento_id", "numero_contrato",
    "nombre_obra", "contratista", "fecha_firma", "fecha_inicio",
    "fecha_termino", "monto_con_iva", "porcentaje_anticipo",
    "campos_a_revisar", "extraido_utc",
)
DOCUMENT_HEADERS = (
    "documento_id", "obra_id", "nombre_archivo", "tipo_documental",
    "mime_type", "md5_checksum", "fecha_modificacion_drive", "tamano_bytes",
    "estado_procesamiento", "primera_deteccion_utc", "ultima_deteccion_utc",
    "activo", "version_extractor", "resultado_id", "ultimo_error", "revision",
)
COMPLETE = "COMPLETADO"
IN_PROGRESS = "EN_PROCESO"
UNCERTAIN = "REQUIERE_REVISION"


class ExtractionStateError(RuntimeError):
    """No es seguro gastar otra llamada sin revisar el registro."""


@dataclass(frozen=True)
class ExtractionOutcome:
    extraction: ExtraccionContrato
    cache: CacheKey
    cached: bool
    input_tokens: int | None
    output_tokens: int | None
    recovered_partial: bool = False


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sheet_rows(client: Any, spreadsheet_id: str) -> dict[str, list[list[str]]]:
    wanted = [
        ("Extracciones", EXTRACTION_HEADERS),
        ("DatosContrato", CONTRACT_HEADERS),
        ("Documentos", DOCUMENT_HEADERS),
    ]
    response = client.spreadsheets().values().batchGet(
        spreadsheetId=spreadsheet_id,
        ranges=[f"'{name}'!A1:{chr(64 + len(headers))}" for name, headers in wanted],
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    data = response.get("valueRanges") or []
    if len(data) != len(wanted):
        raise ExtractionStateError("No se pudieron leer las hojas de análisis.")
    tables: dict[str, list[list[str]]] = {}
    for (name, headers), result in zip(wanted, data):
        values = result.get("values") or []
        if not values or tuple(str(x) for x in values[0]) != headers:
            raise ExtractionStateError(f"Estructura inesperada en la pestaña {name}.")
        normalized: list[list[str]] = []
        for row in values[1:]:
            padded = [str(x) if x is not None else "" for x in row[:len(headers)]]
            padded += [""] * (len(headers) - len(padded))
            normalized.append(padded)
        tables[name] = normalized
    return tables


def _find_unique(rows: list[list[str]], column: int, value: str) -> tuple[int, list[str]] | None:
    matches = [(i + 2, row) for i, row in enumerate(rows) if row[column] == value]
    if len(matches) > 1:
        raise ExtractionStateError("Se detectaron identificadores duplicados en Sheets.")
    return matches[0] if matches else None


def _confirm_ranges(response: dict[str, Any], count: int) -> None:
    """Comprobar los rangos, no el número de filas físicas.

    Google devuelve una respuesta por rango, mientras totalUpdatedRows
    cuenta filas distintas; varias escrituras a la misma fila no suman.
    """
    results = response.get("responses")
    if not isinstance(results, list) or len(results) != count:
        raise ExtractionStateError(
            "Google Sheets no confirmó la escritura de todos los rangos."
        )
    for item in results:
        if not isinstance(item, dict) or int(item.get("updatedRows") or 0) < 1:
            raise ExtractionStateError(
                "Google Sheets devolvió un rango sin confirmar."
            )


def _batch_write(client: Any, spreadsheet_id: str, writes: list[tuple[str, int, list[str]]]) -> None:
    data = []
    for name, row_num, cells in writes:
        end_letter = chr(64 + len(cells))
        data.append({
            "range": f"'{name}'!A{row_num}:{end_letter}{row_num}",
            "values": [cells],
        })
    if not data:
        return
    result = client.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"valueInputOption": "RAW", "data": data},
    ).execute()
    _confirm_ranges(result, len(data))


def _write_regions(client: Any, spreadsheet_id: str, writes: list[dict[str, Any]]) -> None:
    result = client.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"valueInputOption": "RAW", "data": writes},
    ).execute()
    _confirm_ranges(result, len(writes))


def _needs_review(result: ExtraccionContrato) -> list[str]:
    fields = []
    for name in result.__class__.model_fields:
        datum = getattr(result, name)
        if hasattr(datum, "valor") and (datum.valor is None or datum.requiere_revision):
            fields.append(name)
    return fields


def _flat_result(
    key: str, obra_id: str, doc_id: str, result: ExtraccionContrato, now: str
) -> list[str]:
    fields = (
        "numero_contrato", "nombre_obra", "contratista",
        "fecha_firma", "fecha_inicio", "fecha_termino",
        "monto_con_iva", "porcentaje_anticipo",
    )
    return [
        key, obra_id, doc_id,
        *(getattr(result, name).valor or "" for name in fields),
        ", ".join(_needs_review(result)), now,
    ]


def _mark_document(
    doc_row_num: int, doc_row: list[str], result: ExtraccionContrato,
    cache_key: str, model: str, prompt_version: str,
) -> list[dict[str, Any]]:
    estado = "Requiere validación" if _needs_review(result) else "Analizado"
    return [
        {"range": f"'Documentos'!I{doc_row_num}", "values": [[estado]]},
        {"range": f"'Documentos'!M{doc_row_num}:O{doc_row_num}",
         "values": [[f"{model}:{prompt_version}", cache_key, ""]]},
    ]


def recover_saved_fields(
    sheets: Any,
    spreadsheet_id: str,
    pdf_bytes: bytes,
    doc: DocumentRecord,
    obra_id: str,
    *,
    model: str = DEFAULT_MODEL,
) -> ExtractionOutcome | None:
    """Recupera exclusivamente los valores ya escritos en DatosContrato.

    No modifica Sheets ni llama a Gemini. La página y la evidencia originales
    no sobrevivieron al fallo de confirmación y se dejan siempre en null.
    Solo se permite la misma versión exacta de PDF, modelo, prompt y esquema.
    """
    cache = crear_clave_cache(
        pdf_bytes, modelo=model, version_prompt=PROMPT_VERSION,
        version_esquema=SCHEMA_VERSION,
    )
    tables = _sheet_rows(sheets, spreadsheet_id)
    doc_entry = _find_unique(tables["Documentos"], 0, doc.id)
    if not doc_entry:
        raise ExtractionStateError("El documento no figura en el registro de Drive.")
    _, document_row = doc_entry
    if (
        document_row[1] != obra_id
        or document_row[5] != doc.md5_checksum
        or document_row[11] != "SI"
    ):
        raise ExtractionStateError(
            "El documento cambió o está inactivo. Sincroniza Drive."
        )
    previous = _find_unique(tables["Extracciones"], 0, cache.clave)
    if not previous:
        return None
    _, attempt = previous
    if (
        attempt[1] not in (UNCERTAIN, IN_PROGRESS)
        or attempt[2] != doc.id
        or attempt[3] != obra_id
        or attempt[4] != cache.contenido_sha256
        or attempt[5] != model
        or attempt[6] != PROMPT_VERSION
        or attempt[7] != SCHEMA_VERSION
    ):
        return None

    matches = [
        row for row in tables["DatosContrato"]
        if row[0] == cache.clave and row[1] == obra_id and row[2] == doc.id
    ]
    if len(matches) > 1:
        raise ExtractionStateError("Existen duplicados en DatosContrato.")
    if not matches:
        return None
    record = matches[0]
    if not any(value.strip() for value in record[3:11]):
        return None
    fields = {
        name: {
            "valor": record[index + 3].strip() or None,
            "pagina": None,
            "evidencia": None,
        }
        for index, name in enumerate(CAMPOS_CONTRATO)
    }
    extraction = ExtraccionContrato.model_validate({
        **fields,
        "observaciones": [
            "Recuperación parcial de valores ya guardados en Google Sheets.",
            "Las páginas y las evidencias originales no quedaron almacenadas; "
            "todos los campos requieren cotejo humano con el PDF.",
            "No se realizó una nueva solicitud a Gemini.",
        ],
    })
    return ExtractionOutcome(
        extraction=extraction, cache=cache, cached=True,
        input_tokens=None, output_tokens=None, recovered_partial=True,
    )


def extract_or_reuse(
    sheets: Any,
    spreadsheet_id: str,
    pdf_bytes: bytes,
    doc: DocumentRecord,
    obra_id: str,
    api_key: str,
    *,
    model: str = DEFAULT_MODEL,
    allow_retry: bool = False,
    invoke: Callable[..., GeminiResult] = extract_contract,
) -> ExtractionOutcome:
    """Consulta primero la caché y llama a IA únicamente si es necesaria.

    Se persiste una reserva ANTES de invocar Gemini. Si ocurre un fallo,
    la clave queda bloqueada para impedir un nuevo cargo accidental.
    """
    cache = crear_clave_cache(
        pdf_bytes, modelo=model, version_prompt=PROMPT_VERSION,
        version_esquema=SCHEMA_VERSION,
    )
    tables = _sheet_rows(sheets, spreadsheet_id)
    doc_entry = _find_unique(tables["Documentos"], 0, doc.id)
    if not doc_entry:
        raise ExtractionStateError(
            "El archivo aún no aparece en la hoja Documentos. Sincroniza Drive primero."
        )
    doc_num, doc_row = doc_entry
    if (
        doc_row[1] != obra_id
        or doc_row[11] != "SI"
        or doc_row[5] != doc.md5_checksum
    ):
        raise ExtractionStateError("El registro no coincide con la versión actual de Drive.")

    existing = _find_unique(tables["Extracciones"], 0, cache.clave)
    now = _utc()
    if existing:
        row_num, row = existing
        if row[1] == COMPLETE:
            parsed = ExtraccionContrato.model_validate_json(row[10])
            fields_entry = [
                (i + 2, current)
                for i, current in enumerate(tables["DatosContrato"])
                if current[0] == cache.clave and current[2] == doc.id
            ]
            if len(fields_entry) > 1:
                raise ExtractionStateError("Hay resultados contractuales duplicados.")
            writes = _mark_document(
                doc_num, doc_row, parsed, cache.clave, model, PROMPT_VERSION
            )
            if not fields_entry:
                flattened = _flat_result(cache.clave, obra_id, doc.id, parsed, now)
                writes.append({
                    "range": f"'DatosContrato'!A{len(tables['DatosContrato']) + 2}:M{len(tables['DatosContrato']) + 2}",
                    "values": [flattened],
                })
            _write_regions(sheets, spreadsheet_id, writes)
            return ExtractionOutcome(
                parsed, cache, True,
                int(row[11]) if row[11] else None,
                int(row[12]) if row[12] else None,
            )
        if not allow_retry:
            raise ExtractionStateError(
                "Existe una solicitud sin resultado confirmado para este PDF. "
                "Revisa el registro y utiliza Reintentar explícitamente si procede."
            )
    else:
        row_num = len(tables["Extracciones"]) + 2
        row = [""] * len(EXTRACTION_HEADERS)

    reservation = [
        cache.clave, IN_PROGRESS, doc.id, obra_id, cache.contenido_sha256,
        model, PROMPT_VERSION, SCHEMA_VERSION, row[8] or now,
        now, "", "", "", "",
    ]
    _batch_write(sheets, spreadsheet_id, [("Extracciones", row_num, reservation)])
    phase = "GENERATING"
    try:
        gemini_result = invoke(pdf_bytes, api_key, model=model)
        if not isinstance(gemini_result, GeminiResult):
            raise ValueError("El proveedor no devolvió un resultado válido.")
        parsed = gemini_result.extraction
        json_payload = parsed.model_dump_json(exclude_none=False)
        if len(json_payload) > 40000:
            raise ValueError("La respuesta supera el tamaño admitido por Sheets.")
        completed = [
            cache.clave, COMPLETE, doc.id, obra_id, cache.contenido_sha256,
            model, PROMPT_VERSION, SCHEMA_VERSION, row[8] or now,
            _utc(), json_payload,
            str(gemini_result.input_tokens or ""),
            str(gemini_result.output_tokens or ""), "",
        ]
        existing_flat = [
            (i + 2, r) for i, r in enumerate(tables["DatosContrato"])
            if r[0] == cache.clave and r[2] == doc.id
        ]
        if len(existing_flat) > 1:
            raise ExtractionStateError("Hay resultados contractuales duplicados.")
        flat_row = existing_flat[0][0] if existing_flat else len(tables["DatosContrato"]) + 2
        flat_values = _flat_result(cache.clave, obra_id, doc.id, parsed, now)
        updates = [
            {"range": f"'Extracciones'!A{row_num}:N{row_num}", "values": [completed]},
            {"range": f"'DatosContrato'!A{flat_row}:M{flat_row}", "values": [flat_values]},
            *_mark_document(doc_num, doc_row, parsed, cache.clave, model, PROMPT_VERSION),
        ]
        phase = "PERSISTING"
        _write_regions(sheets, spreadsheet_id, updates)
        return ExtractionOutcome(
            parsed, cache, False, gemini_result.input_tokens, gemini_result.output_tokens
        )
    except Exception as exc:
        if phase == "PERSISTING":
            # El modelo YA devolvió datos. La escritura puede haber llegado
            # a Sheets aunque el cliente no haya confirmado. No sobrescribir
            # el JSON ni otros registros con una reserva vacía.
            raise ExtractionStateError(
                "Gemini devolvió una extracción, pero no se pudo confirmar "
                "su almacenamiento completo. No reintentes Gemini: comprueba "
                "DatosContrato y usa Recuperar datos guardados sin IA."
            ) from None
        # Solo los fallos de generación/validación se registran como
        # intento incierto. No divulgar mensajes del proveedor.
        reservation[1] = UNCERTAIN
        reservation[9] = _utc()
        if isinstance(exc, GeminiRequestError):
            incident_code = exc.public_code
            guidance = exc.explanation
        else:
            incident_code = type(exc).__name__[:80]
            guidance = "Revisa el registro antes de autorizar un nuevo análisis."
        reservation[13] = incident_code
        try:
            _batch_write(sheets, spreadsheet_id, [("Extracciones", row_num, reservation)])
        except Exception:
            pass
        raise ExtractionStateError(
            "No se confirmó el resultado de Gemini. "
            f"Diagnóstico: {incident_code}. {guidance} "
            "El reintento automático sigue bloqueado y la solicitud permanece en el historial."
        ) from None
