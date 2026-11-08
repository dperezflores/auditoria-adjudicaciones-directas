"""Gemini: una solicitud explícita por PDF, con salida Pydantic.

Este módulo NO se ejecuta al abrir Streamlit, listar carpetas ni sincronizar.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.contract_schema import ExtraccionContrato
from services.gemini_errors import GeminiRequestError

DEFAULT_MODEL = "gemini-3.5-flash-lite"


@dataclass(frozen=True)
class GeminiResult:
    extraction: ExtraccionContrato
    input_tokens: int | None
    output_tokens: int | None


def extract_contract(
    pdf_bytes: bytes,
    api_key: str,
    *,
    model: str = DEFAULT_MODEL,
) -> GeminiResult:
    """Invoca Gemini solamente tras la confirmación explícita del auditor."""
    if not isinstance(pdf_bytes, bytes) or not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("El archivo proporcionado no es un PDF.")
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError("Falta la clave de Gemini en Streamlit Secrets.")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("El nombre del modelo Gemini está vacío.")

    from google import genai
    from google.genai import types, errors as genai_errors
    from services.contract_prompt import PROMPT_CONTRATO

    client = genai.Client(api_key=api_key)
    try:
        try:
            response = client.models.generate_content(
                model=model.strip(),
                contents=[
                    types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                    PROMPT_CONTRATO,
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ExtraccionContrato,
                ),
            )
        except genai_errors.APIError as exc:
            # Error seguro: mostrar solo HTTP y status, nunca texto del proveedor.
            raise GeminiRequestError(exc.code, exc.status) from None

        parsed: Any = getattr(response, "parsed", None)
        if isinstance(parsed, ExtraccionContrato):
            extraction = parsed
        elif parsed is not None:
            extraction = ExtraccionContrato.model_validate(parsed)
        else:
            raw_text = getattr(response, "text", None)
            if not isinstance(raw_text, str) or not raw_text.strip():
                raise ValueError("Gemini no devolvió una extracción estructurada.")
            extraction = ExtraccionContrato.model_validate_json(raw_text)

        usage = getattr(response, "usage_metadata", None)
        in_tokens = getattr(usage, "prompt_token_count", None)
        out_tokens = getattr(usage, "candidates_token_count", None)
        return GeminiResult(extraction=extraction, input_tokens=in_tokens, output_tokens=out_tokens)
    finally:
        client.close()
