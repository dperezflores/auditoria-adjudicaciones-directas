"""Persistencia orden de adjudicación directa-v1 con caché, reserva y bloqueo de reintentos inciertos.

La respuesta completa con evidencias queda en Extracciones; DatosOrdenAD
conserva los valores literales, obligaciones y supervisores en JSON.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any, Callable

from services.document_classifier import code_from_filename
from services.drive_service import DocumentRecord, PDF_MIME
from services.extraction_cache import CacheKey, crear_clave_cache
from services.extraction_store import (
    COMPLETE, IN_PROGRESS, UNCERTAIN, ExtractionStateError,
    _batch_write, _find_unique, _sheet_rows, _write_regions,
)
from services.gemini_errors import GeminiRequestError
from services.gemini_service import DEFAULT_MODEL
from services.orden_gemini import OrdenGeminiResult, extract_orden_ad
from services.orden_prompt import ORDEN_PROMPT_VERSION
from services.orden_schema import ORDEN_HEADERS, ORDEN_SCHEMA_VERSION, OrdenAdV1

TABLE = "DatosOrdenAD"


@dataclass(frozen=True)
class OrdenOutcome:
    extraction: OrdenAdV1
    cache: CacheKey
    cached: bool
    input_tokens: int | None
    output_tokens: int | None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_orden(sheets: Any, spreadsheet_id: str) -> list[list[str]]:
    response = sheets.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range="'DatosOrdenAD'!A1:AF",
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    rows = response.get("values") or []
    if not rows or tuple(str(v) for v in rows[0]) != ORDEN_HEADERS:
        raise ExtractionStateError(
            "La pestaña DatosOrdenAD falta o no tiene los encabezados esperados."
        )
    result = []
    for raw in rows[1:]:
        values = [str(v) if v is not None else "" for v in raw[:len(ORDEN_HEADERS)]]
        values += [""] * (len(ORDEN_HEADERS) - len(values))
        if any(values):
            result.append(values)
    return result


def _flat(
    cache_key: str, obra_id: str, doc_id: str,
    parsed: OrdenAdV1, now: str,
) -> list[str]:
    def serial(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return [
        cache_key, obra_id, doc_id,
        *parsed.flat_values(),
        serial([x.model_dump(mode="json") for x in parsed.personal_designado]),
        serial([x.model_dump(mode="json") for x in parsed.instrucciones]),
        serial([x.model_dump(mode="json") for x in parsed.fundamentos]),
        serial([x.model_dump(mode="json") for x in parsed.documentos_referidos]),
        serial(parsed.firma_aparente.model_dump(mode="json")),
        serial(parsed.observaciones),
        now,
    ]


def _mark_document(doc_row: int, cache_key: str, model: str) -> list[dict[str, Any]]:
    return [
        {"range": f"'Documentos'!I{doc_row}", "values": [["Analizado"]]},
        {"range": f"'Documentos'!M{doc_row}:O{doc_row}", "values": [[
            f"{model}:{ORDEN_PROMPT_VERSION}", cache_key, "",
        ]]},
    ]


def extract_or_reuse_orden(
    sheets: Any, spreadsheet_id: str, pdf: bytes,
    doc: DocumentRecord, obra_id: str, api_key: str,
    *, model: str = DEFAULT_MODEL,
    invoke: Callable[..., OrdenGeminiResult] = extract_orden_ad,
) -> OrdenOutcome:
    """Analizar ORDEN_AD.pdf a demanda y nunca reiterar automáticamente si hay incertidumbre."""
    if code_from_filename(doc.name, doc.mime_type) != "ORDEN_AD" or doc.mime_type != PDF_MIME:
        raise ExtractionStateError("Solo se admite el archivo ORDEN_AD.pdf para el extractor orden de adjudicación directa-v1.")
    cache = crear_clave_cache(
        pdf,
        modelo=model, version_prompt=ORDEN_PROMPT_VERSION,
        version_esquema=ORDEN_SCHEMA_VERSION, tipo_documento="ORDEN_AD",
    )
    tables = _sheet_rows(sheets, spreadsheet_id)
    orden_rows = _read_orden(sheets, spreadsheet_id)
    registered = _find_unique(tables["Documentos"], 0, doc.id)
    if not registered:
        raise ExtractionStateError("El orden de adjudicación directa no está registrado; actualiza Google Drive.")
    doc_row, document = registered
    if (
        document[1] != obra_id or document[11] != "SI"
        or document[3] != "ORDEN_AD" or document[4] != PDF_MIME
        or document[5] != doc.md5_checksum or not doc.md5_checksum
    ):
        raise ExtractionStateError(
            "No coincide el tipo, la huella o la obra del archivo. Actualiza Drive."
        )
    previous = _find_unique(tables["Extracciones"], 0, cache.clave)
    flat_existing = _find_unique(orden_rows, 0, cache.clave)
    if flat_existing and flat_existing[1][1:3] != [obra_id, doc.id]:
        raise ExtractionStateError("La ficha orden de adjudicación directa está asociada a otro documento u obra.")
    now = _now()

    if previous:
        _, old = previous
        if (
            old[2] != doc.id or old[3] != obra_id
            or old[4] != cache.contenido_sha256
            or old[5:8] != [model, ORDEN_PROMPT_VERSION, ORDEN_SCHEMA_VERSION]
        ):
            raise ExtractionStateError("La clave de caché orden de adjudicación directa corresponde a otro origen.")
        if old[1] == COMPLETE and old[10]:
            try:
                parsed = OrdenAdV1.model_validate_json(old[10])
            except Exception as exc:
                raise ExtractionStateError(
                    "La respuesta orden de adjudicación directa ya guardada no cumple el esquema v1."
                ) from exc
            writes = _mark_document(doc_row, cache.clave, model)
            if not flat_existing:
                writes.append({
                    "range": f"'DatosOrdenAD'!A{len(orden_rows) + 2}:AF{len(orden_rows) + 2}",
                    "values": [_flat(cache.clave, obra_id, doc.id, parsed, now)],
                })
            _write_regions(sheets, spreadsheet_id, writes)
            return OrdenOutcome(
                parsed, cache, True,
                int(old[11]) if old[11] else None,
                int(old[12]) if old[12] else None,
            )
        raise ExtractionStateError(
            "Existe una solicitud orden de adjudicación directa sin resultado confirmado. "
            "Se bloqueó el reintento automático para evitar duplicar consumo."
        )

    idx = len(tables["Extracciones"]) + 2
    reservation = [
        cache.clave, IN_PROGRESS, doc.id, obra_id, cache.contenido_sha256,
        model, ORDEN_PROMPT_VERSION, ORDEN_SCHEMA_VERSION,
        now, now, "", "", "", "",
    ]
    _batch_write(sheets, spreadsheet_id, [("Extracciones", idx, reservation)])
    phase = "GENERATE"
    try:
        answer = invoke(pdf, api_key, model=model)
        if not isinstance(answer, OrdenGeminiResult) or not isinstance(
            answer.extraction, OrdenAdV1
        ):
            raise ValueError("Gemini no devolvió una extracción orden de adjudicación directa-v1 válida.")
        result = answer.extraction
        payload = result.model_dump_json(exclude_none=False)
        if len(payload) > 48000:
            raise ValueError(
                "Las evidencias del orden de adjudicación directa exceden el límite seguro de Google Sheets."
            )
        flat = _flat(cache.clave, obra_id, doc.id, result, now)
        if len(flat) != len(ORDEN_HEADERS):
            raise ValueError("La ficha del orden no coincide con el esquema.")
        if any(len(value) > 44000 for value in flat[25:31]):
            raise ValueError("La evidencia del orden excede el límite de una celda.")
        complete = [
            cache.clave, COMPLETE, doc.id, obra_id, cache.contenido_sha256,
            model, ORDEN_PROMPT_VERSION, ORDEN_SCHEMA_VERSION,
            now, _now(), payload,
            str(answer.input_tokens or ""), str(answer.output_tokens or ""), "",
        ]
        target = flat_existing[0] if flat_existing else len(orden_rows) + 2
        writes = [
            {"range": f"'Extracciones'!A{idx}:N{idx}", "values": [complete]},
            {"range": f"'DatosOrdenAD'!A{target}:AF{target}", "values": [flat]},
            *_mark_document(doc_row, cache.clave, model),
        ]
        phase = "SAVE"
        _write_regions(sheets, spreadsheet_id, writes)
        return OrdenOutcome(result, cache, False, answer.input_tokens, answer.output_tokens)
    except Exception as exc:
        if phase == "SAVE":
            raise ExtractionStateError(
                "Gemini respondió, pero Sheets no confirmó el guardado. "
                "Consulta Extracciones y DatosOrdenAD antes de intentar de nuevo."
            ) from None
        reservation[1] = UNCERTAIN
        reservation[9] = _now()
        reservation[13] = (
            exc.public_code if isinstance(exc, GeminiRequestError)
            else type(exc).__name__[:80]
        )
        try:
            _batch_write(sheets, spreadsheet_id, [("Extracciones", idx, reservation)])
        except Exception:
            pass
        raise ExtractionStateError(
            "La extracción del orden de adjudicación directa no se confirmó. Quedó registrada para "
            "revisión y no se volverá a llamar automáticamente a Gemini."
        ) from None
