"""Almacenamiento de contratos v2 sin tocar el historial v1.

Registra la extracción literal, la lista de firmantes y la clasificación
normativa DERIVADA en DatosContratoV2. Una versión de prompt/esquema nueva
produce clave diferente y evita reemplazar las respuestas originales.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any, Callable

from services.contract_prompt import PROMPT_VERSION
from services.contract_v2 import (
    CONTRACT_SCHEMA_V2, CONTRACT_V2_FIELDS, CONTRACT_V2_HEADERS,
    ContractExtractionV2, classify_cited_regime,
)
from services.drive_service import DocumentRecord
from services.extraction_cache import CacheKey, crear_clave_cache
from services.extraction_store import (
    COMPLETE, IN_PROGRESS, UNCERTAIN, ExtractionStateError,
    _batch_write, _find_unique, _sheet_rows, _write_regions,
)
from services.gemini_errors import GeminiRequestError
from services.gemini_service import DEFAULT_MODEL, GeminiResult, extract_contract

TABLE = "DatosContratoV2"


@dataclass(frozen=True)
class ContractOutcomeV2:
    extraction: ContractExtractionV2
    cache: CacheKey
    cached: bool
    input_tokens: int | None
    output_tokens: int | None


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_v2(client: Any, sheet_id: str) -> list[list[str]]:
    result = client.spreadsheets().values().get(
        spreadsheetId=sheet_id, range="'DatosContratoV2'!A1:W",
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    values = result.get("values") or []
    if not values or tuple(map(str, values[0][:len(CONTRACT_V2_HEADERS)])) != CONTRACT_V2_HEADERS:
        raise ExtractionStateError(
            "Falta la pestaña DatosContratoV2 o sus encabezados no coinciden."
        )
    rows = []
    for item in values[1:]:
        cells = ["" if v is None else str(v) for v in item[:len(CONTRACT_V2_HEADERS)]]
        cells += [""] * (len(CONTRACT_V2_HEADERS) - len(cells))
        rows.append(cells)
    return rows


def _flatten(
    cache_key: str, obra_id: str, document_id: str,
    extraction: ContractExtractionV2, now: str,
) -> list[str]:
    return [
        cache_key, obra_id, document_id,
        *extraction.flat_values(),
        json.dumps(
            [person.model_dump(mode="json") for person in extraction.personas_participantes],
            ensure_ascii=False, separators=(",", ":"),
        ),
        classify_cited_regime(extraction.legislacion_citada.valor),
        json.dumps(extraction.observaciones, ensure_ascii=False),
        now,
    ]


def _mark_document(
    row_number: int, cache_key: str, model: str,
    extraction: ContractExtractionV2,
) -> list[dict[str, Any]]:
    status = "Requiere validación" if extraction.fields_to_review() else "Analizado"
    return [
        {"range": f"'Documentos'!I{row_number}", "values": [[status]]},
        {"range": f"'Documentos'!M{row_number}:O{row_number}",
         "values": [[f"{model}:{PROMPT_VERSION}", cache_key, ""]]},
    ]


def extract_or_reuse_v2(
    sheets: Any, spreadsheet_id: str, pdf_bytes: bytes,
    doc: DocumentRecord, obra_id: str, api_key: str, *,
    model: str = DEFAULT_MODEL,
    invoke: Callable[..., GeminiResult] = extract_contract,
) -> ContractOutcomeV2:
    """Solo genera tras pulsación explícita; nunca reintenta una clave incierta."""
    cache = crear_clave_cache(
        pdf_bytes, modelo=model, version_prompt=PROMPT_VERSION,
        version_esquema=CONTRACT_SCHEMA_V2,
    )
    tables = _sheet_rows(sheets, spreadsheet_id)
    v2_rows = _read_v2(sheets, spreadsheet_id)
    doc_entry = _find_unique(tables["Documentos"], 0, doc.id)
    if not doc_entry:
        raise ExtractionStateError("El PDF no está registrado. Actualiza Drive.")
    doc_row_num, document = doc_entry
    if (
        document[1] != obra_id or document[11] != "SI"
        or document[5] != doc.md5_checksum
    ):
        raise ExtractionStateError("El PDF no coincide con la última versión de Drive.")

    previous = _find_unique(tables["Extracciones"], 0, cache.clave)
    in_flat = _find_unique(v2_rows, 0, cache.clave)
    now = _utc()
    if previous:
        index, old = previous
        if old[2] != doc.id or old[3] != obra_id:
            raise ExtractionStateError("La clave de caché está asociada a otro documento.")
        if old[1] == COMPLETE and old[10]:
            try:
                parsed = ContractExtractionV2.model_validate_json(old[10])
            except Exception as exc:
                raise ExtractionStateError("El resultado guardado no cumple el esquema v2.") from exc
            writes = _mark_document(doc_row_num, cache.clave, model, parsed)
            if not in_flat:
                target = len(v2_rows) + 2
                writes.append({
                    "range": f"'DatosContratoV2'!A{target}:W{target}",
                    "values": [_flatten(cache.clave, obra_id, doc.id, parsed, now)],
                })
            _write_regions(sheets, spreadsheet_id, writes)
            return ContractOutcomeV2(
                parsed, cache, True,
                int(old[11]) if old[11] else None,
                int(old[12]) if old[12] else None,
            )
        raise ExtractionStateError(
            "Ya existe un intento de extracción v2 sin resultado confirmado. "
            "No se repetirá la llamada automáticamente."
        )

    idx = len(tables["Extracciones"]) + 2
    reservation = [
        cache.clave, IN_PROGRESS, doc.id, obra_id, cache.contenido_sha256,
        model, PROMPT_VERSION, CONTRACT_SCHEMA_V2, now, now, "", "", "", "",
    ]
    _batch_write(sheets, spreadsheet_id, [("Extracciones", idx, reservation)])
    phase = "GENERATE"
    try:
        response = invoke(pdf_bytes, api_key, model=model)
        if not isinstance(response, GeminiResult) or not isinstance(
            response.extraction, ContractExtractionV2
        ):
            raise ValueError("Gemini no devolvió una extracción contractual v2.")
        extraction = response.extraction
        payload = extraction.model_dump_json(exclude_none=False)
        if len(payload) > 40000:
            raise ValueError("Los datos estructurados exceden el límite por celda.")
        complete = [
            cache.clave, COMPLETE, doc.id, obra_id, cache.contenido_sha256,
            model, PROMPT_VERSION, CONTRACT_SCHEMA_V2,
            now, _utc(), payload,
            str(response.input_tokens or ""), str(response.output_tokens or ""), "",
        ]
        target = in_flat[0] if in_flat else len(v2_rows) + 2
        writes = [
            {"range": f"'Extracciones'!A{idx}:N{idx}", "values": [complete]},
            {"range": f"'DatosContratoV2'!A{target}:W{target}",
             "values": [_flatten(cache.clave, obra_id, doc.id, extraction, now)]},
            *_mark_document(doc_row_num, cache.clave, model, extraction),
        ]
        phase = "SAVE"
        _write_regions(sheets, spreadsheet_id, writes)
        return ContractOutcomeV2(
            extraction, cache, False, response.input_tokens, response.output_tokens
        )
    except Exception as exc:
        if phase == "SAVE":
            raise ExtractionStateError(
                "Gemini entregó la extracción, pero Sheets no confirmó el guardado. "
                "Revisa Extracciones y DatosContratoV2 antes de repetir."
            ) from None
        reservation[1] = UNCERTAIN
        reservation[9] = _utc()
        code = exc.public_code if isinstance(exc, GeminiRequestError) else type(exc).__name__[:80]
        reservation[13] = code
        try:
            _batch_write(sheets, spreadsheet_id, [("Extracciones", idx, reservation)])
        except Exception:
            pass
        raise ExtractionStateError(
            f"El análisis v2 no fue confirmado ({code}). "
            "Se bloqueó el reintento automático para evitar consumo duplicado."
        ) from None
