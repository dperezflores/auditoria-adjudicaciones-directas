"""Persistencia PUC-v1 con caché, reserva y bloqueo de reintentos inciertos.

La respuesta completa con evidencias queda en Extracciones; DatosPUC
conserva los valores literales y especialidades en JSON para futuros cruces.
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
from services.puc_gemini import PucGeminiResult, extract_puc
from services.puc_prompt import PUC_PROMPT_VERSION
from services.puc_schema import PUC_HEADERS, PUC_SCHEMA_VERSION, PucExtractionV1

TABLE = "DatosPUC"


@dataclass(frozen=True)
class PucOutcome:
    extraction: PucExtractionV1
    cache: CacheKey
    cached: bool
    input_tokens: int | None
    output_tokens: int | None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_puc(sheets: Any, spreadsheet_id: str) -> list[list[str]]:
    response = sheets.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range="'DatosPUC'!A1:X",
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    rows = response.get("values") or []
    if not rows or tuple(str(v) for v in rows[0]) != PUC_HEADERS:
        raise ExtractionStateError(
            "La pestaña DatosPUC falta o no tiene los encabezados esperados."
        )
    result = []
    for raw in rows[1:]:
        values = [str(v) if v is not None else "" for v in raw[:len(PUC_HEADERS)]]
        values += [""] * (len(PUC_HEADERS) - len(values))
        if any(values):
            result.append(values)
    return result


def _flat(cache_key: str, obra_id: str, doc_id: str, parsed: PucExtractionV1, now: str) -> list[str]:
    return [
        cache_key, obra_id, doc_id,
        *parsed.flat_values(),
        json.dumps([e.model_dump(mode="json") for e in parsed.especialidades],
                   ensure_ascii=False, separators=(",", ":")),
        json.dumps(parsed.observaciones, ensure_ascii=False, separators=(",", ":")),
        now,
    ]


def _mark_document(doc_row: int, cache_key: str, model: str) -> list[dict[str, Any]]:
    return [
        {"range": f"'Documentos'!I{doc_row}", "values": [["Analizado"]]},
        {"range": f"'Documentos'!M{doc_row}:O{doc_row}", "values": [[
            f"{model}:{PUC_PROMPT_VERSION}", cache_key, "",
        ]]},
    ]


def extract_or_reuse_puc(
    sheets: Any, spreadsheet_id: str, pdf: bytes,
    doc: DocumentRecord, obra_id: str, api_key: str,
    *, model: str = DEFAULT_MODEL,
    invoke: Callable[..., PucGeminiResult] = extract_puc,
) -> PucOutcome:
    """Analizar PUC.pdf a demanda y nunca reiterar automáticamente si hay incertidumbre."""
    if code_from_filename(doc.name, doc.mime_type) != "PUC" or doc.mime_type != PDF_MIME:
        raise ExtractionStateError("Solo se admite el archivo PUC.pdf para el extractor PUC-v1.")
    cache = crear_clave_cache(
        pdf,
        modelo=model, version_prompt=PUC_PROMPT_VERSION,
        version_esquema=PUC_SCHEMA_VERSION, tipo_documento="PUC",
    )
    tables = _sheet_rows(sheets, spreadsheet_id)
    puc_rows = _read_puc(sheets, spreadsheet_id)
    registered = _find_unique(tables["Documentos"], 0, doc.id)
    if not registered:
        raise ExtractionStateError("El PUC no está registrado; actualiza Google Drive.")
    doc_row, document = registered
    if (
        document[1] != obra_id or document[11] != "SI"
        or document[3] != "PUC" or document[4] != PDF_MIME
        or document[5] != doc.md5_checksum or not doc.md5_checksum
    ):
        raise ExtractionStateError(
            "No coincide el tipo, la huella o la obra del archivo. Actualiza Drive."
        )
    previous = _find_unique(tables["Extracciones"], 0, cache.clave)
    flat_existing = _find_unique(puc_rows, 0, cache.clave)
    if flat_existing and flat_existing[1][1:3] != [obra_id, doc.id]:
        raise ExtractionStateError("La ficha PUC está asociada a otro documento u obra.")
    now = _now()

    if previous:
        _, old = previous
        if (
            old[2] != doc.id or old[3] != obra_id
            or old[4] != cache.contenido_sha256
            or old[5:8] != [model, PUC_PROMPT_VERSION, PUC_SCHEMA_VERSION]
        ):
            raise ExtractionStateError("La clave de caché PUC corresponde a otro origen.")
        if old[1] == COMPLETE and old[10]:
            try:
                parsed = PucExtractionV1.model_validate_json(old[10])
            except Exception as exc:
                raise ExtractionStateError(
                    "La respuesta PUC ya guardada no cumple el esquema v1."
                ) from exc
            writes = _mark_document(doc_row, cache.clave, model)
            if not flat_existing:
                writes.append({
                    "range": f"'DatosPUC'!A{len(puc_rows) + 2}:X{len(puc_rows) + 2}",
                    "values": [_flat(cache.clave, obra_id, doc.id, parsed, now)],
                })
            _write_regions(sheets, spreadsheet_id, writes)
            return PucOutcome(
                parsed, cache, True,
                int(old[11]) if old[11] else None,
                int(old[12]) if old[12] else None,
            )
        raise ExtractionStateError(
            "Existe una solicitud PUC sin resultado confirmado. "
            "Se bloqueó el reintento automático para evitar duplicar consumo."
        )

    idx = len(tables["Extracciones"]) + 2
    reservation = [
        cache.clave, IN_PROGRESS, doc.id, obra_id, cache.contenido_sha256,
        model, PUC_PROMPT_VERSION, PUC_SCHEMA_VERSION,
        now, now, "", "", "", "",
    ]
    _batch_write(sheets, spreadsheet_id, [("Extracciones", idx, reservation)])
    phase = "GENERATE"
    try:
        answer = invoke(pdf, api_key, model=model)
        if not isinstance(answer, PucGeminiResult) or not isinstance(
            answer.extraction, PucExtractionV1
        ):
            raise ValueError("Gemini no devolvió una extracción PUC-v1 válida.")
        result = answer.extraction
        payload = result.model_dump_json(exclude_none=False)
        if len(payload) > 48000:
            raise ValueError(
                "Las evidencias del PUC exceden el límite seguro de Google Sheets."
            )
        flat = _flat(cache.clave, obra_id, doc.id, result, now)
        if len(flat[21]) > 44000 or len(flat[22]) > 44000:
            raise ValueError("La lista de especialidades no cabe en una celda de Sheets.")
        complete = [
            cache.clave, COMPLETE, doc.id, obra_id, cache.contenido_sha256,
            model, PUC_PROMPT_VERSION, PUC_SCHEMA_VERSION,
            now, _now(), payload,
            str(answer.input_tokens or ""), str(answer.output_tokens or ""), "",
        ]
        target = flat_existing[0] if flat_existing else len(puc_rows) + 2
        writes = [
            {"range": f"'Extracciones'!A{idx}:N{idx}", "values": [complete]},
            {"range": f"'DatosPUC'!A{target}:X{target}", "values": [flat]},
            *_mark_document(doc_row, cache.clave, model),
        ]
        phase = "SAVE"
        _write_regions(sheets, spreadsheet_id, writes)
        return PucOutcome(result, cache, False, answer.input_tokens, answer.output_tokens)
    except Exception as exc:
        if phase == "SAVE":
            raise ExtractionStateError(
                "Gemini respondió, pero Sheets no confirmó el guardado. "
                "Consulta Extracciones y DatosPUC antes de intentar de nuevo."
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
            "La extracción del PUC no se confirmó. Quedó registrada para "
            "revisión y no se volverá a llamar automáticamente a Gemini."
        ) from None
