"""Invoca Gemini para ORDEN_AD.pdf, devuelve valores y evidencias."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from services.gemini_errors import GeminiRequestError
from services.gemini_service import DEFAULT_MODEL
from services.orden_prompt import PROMPT_ORDEN_AD
from services.orden_schema import OrdenAdV1, ORDEN_RESPONSE_SCHEMA, parse_orden


@dataclass(frozen=True)
class OrdenGeminiResult:
    extraction: OrdenAdV1
    input_tokens: int | None
    output_tokens: int | None


def extract_orden_ad(
    pdf_bytes: bytes, api_key: str, *, model: str = DEFAULT_MODEL,
) -> OrdenGeminiResult:
    if not isinstance(pdf_bytes, bytes) or not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("No es un archivo PDF válido.")
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError("Falta API key de Gemini.")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Falta un modelo Gemini configurado.")
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
                    PROMPT_ORDEN_AD,
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_json_schema=ORDEN_RESPONSE_SCHEMA,
                    temperature=0,
                ),
            )
        except genai_errors.APIError as exc:
            raise GeminiRequestError(exc.code, exc.status) from None
        parsed: Any = getattr(response, "parsed", None)
        if parsed is None:
            parsed = getattr(response, "text", None)
        extraction = parse_orden(parsed)
        usage = getattr(response, "usage_metadata", None)
        return OrdenGeminiResult(
            extraction=extraction,
            input_tokens=getattr(usage, "prompt_token_count", None),
            output_tokens=getattr(usage, "candidates_token_count", None),
        )
    finally:
        client.close()
