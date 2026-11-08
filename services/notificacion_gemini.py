"""Invocación de Gemini exclusivamente para NOTIFICACION_AD.pdf."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.gemini_errors import GeminiRequestError
from services.gemini_service import DEFAULT_MODEL
from services.notificacion_prompt import PROMPT_NOTIFICACION_AD
from services.notificacion_schema import (
    NotificacionAdV1, NOTIFICACION_RESPONSE_SCHEMA, parse_notificacion,
)


@dataclass(frozen=True)
class NotificacionGeminiResult:
    extraction: NotificacionAdV1
    input_tokens: int | None
    output_tokens: int | None


def extract_notificacion_ad(
    pdf_bytes: bytes, api_key: str, *, model: str = DEFAULT_MODEL,
) -> NotificacionGeminiResult:
    if not isinstance(pdf_bytes, bytes) or not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("El archivo seleccionado no es PDF.")
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError("Falta configurar clave de Gemini.")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("No hay modelo Gemini configurado.")
    from google import genai
    from google.genai import types, errors as genai_errors

    client = genai.Client(api_key=api_key)
    try:
        try:
            response = client.models.generate_content(
                model=model.strip(),
                contents=[
                    types.Part.from_bytes(
                        data=pdf_bytes, mime_type="application/pdf"
                    ),
                    PROMPT_NOTIFICACION_AD,
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_json_schema=NOTIFICACION_RESPONSE_SCHEMA,
                    temperature=0,
                ),
            )
        except genai_errors.APIError as exc:
            raise GeminiRequestError(exc.code, exc.status) from None
        parsed: Any = getattr(response, "parsed", None)
        if parsed is None:
            parsed = getattr(response, "text", None)
        extraction = parse_notificacion(parsed)
        usage = getattr(response, "usage_metadata", None)
        return NotificacionGeminiResult(
            extraction=extraction,
            input_tokens=getattr(usage, "prompt_token_count", None),
            output_tokens=getattr(usage, "candidates_token_count", None),
        )
    finally:
        client.close()
