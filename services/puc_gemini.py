"""Una única solicitud Gemini para PUC, tras pulsación explícita del auditor."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.gemini_errors import GeminiRequestError
from services.gemini_service import DEFAULT_MODEL
from services.puc_prompt import PROMPT_PUC
from services.puc_schema import PUC_RESPONSE_SCHEMA, PucExtractionV1, parse_puc


@dataclass(frozen=True)
class PucGeminiResult:
    extraction: PucExtractionV1
    input_tokens: int | None
    output_tokens: int | None


def extract_puc(pdf_bytes: bytes, api_key: str, *, model: str = DEFAULT_MODEL) -> PucGeminiResult:
    if not isinstance(pdf_bytes, bytes) or not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("El documento seleccionado no es un PDF.")
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError("Falta clave de Gemini.")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("No se configuró el modelo Gemini.")
    from google import genai
    from google.genai import types, errors as genai_errors

    client = genai.Client(api_key=api_key)
    try:
        try:
            response = client.models.generate_content(
                model=model.strip(),
                contents=[
                    types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                    PROMPT_PUC,
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_json_schema=PUC_RESPONSE_SCHEMA,
                    temperature=0,
                ),
            )
        except genai_errors.APIError as exc:
            raise GeminiRequestError(exc.code, exc.status) from None

        parsed: Any = getattr(response, "parsed", None)
        if parsed is None:
            parsed = getattr(response, "text", None)
        extraction = parse_puc(parsed)

        usage = getattr(response, "usage_metadata", None)
        return PucGeminiResult(
            extraction=extraction,
            input_tokens=getattr(usage, "prompt_token_count", None),
            output_tokens=getattr(usage, "candidates_token_count", None),
        )
    finally:
        client.close()
