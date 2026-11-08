"""Ficha de lectura documental para PDFs distintos del contrato.

Nunca determina irregularidades legales: identifica el tipo, sintetiza el
contenido y cita datos comprobables para alimentar futuras pruebas de auditoría.
Cada generación se solicita manualmente y se guarda antes de mostrarla.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any, Callable
from pydantic import BaseModel, ConfigDict, Field, field_validator

from services.drive_service import DocumentRecord
from services.extraction_cache import CacheKey, crear_clave_cache
from services.extraction_store import (
    _sheet_rows, _find_unique, _batch_write, _write_regions,
    EXTRACTION_HEADERS, ExtractionStateError,
    COMPLETE, IN_PROGRESS, UNCERTAIN,
)
from services.gemini_service import DEFAULT_MODEL
from services.gemini_errors import GeminiRequestError

GENERAL_PROMPT_VERSION = "documento-prompt-v1"
GENERAL_SCHEMA_VERSION = "documento-schema-v1"
GENERAL_KIND = "ficha_documental"

GENERAL_SCHEMA = {
    "type": "object",
    "properties": {
        "tipo_documental": {"type": "string"},
        "resumen": {"type": "string"},
        "campos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "campo": {"type": "string"},
                    "valor": {"type": "string"},
                    "pagina": {"type": ["integer", "null"]},
                    "evidencia": {"type": ["string", "null"]},
                },
                "required": ["campo", "valor", "pagina", "evidencia"],
            },
        },
        "alertas": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["tipo_documental", "resumen", "campos", "alertas"],
}

GENERAL_PROMPT = """Eres un asistente documental para auditores de obra pública de Guanajuato.
Lee visualmente el PDF adjunto; puede ser un escaneo, PUC, dictamen de
adjudicación directa, invitación, notificación, presupuesto, estimación, oficio,
acta, catálogo, factura u otro documento del expediente.
Devuelve SOLO JSON conforme al esquema con:
tipo_documental: tipo que realmente observas, no dependas del nombre del archivo.
resumen: síntesis objetiva breve, basada únicamente en el PDF.
campos: hasta 15 datos útiles para auditoría con campo, valor literal, número de
página física y fragmento visible de evidencia. Prioriza: identificador,
fecha(s), entidad, contratista, RFC, representante técnico, especialidades,
vigencia de PUC, capital contable, monto, obra, fundamento mencionado,
firmantes y referencias cruzadas, SOLO si efectivamente aparecen.
alertas: hasta 6 ambigüedades o documentos mencionados que convendría
revisar; expresarlas como asuntos POR VERIFICAR y nunca como observaciones
de incumplimiento. Si falta una fecha o un dato, NO inferirlo.
No inventes artículos legales, valores, páginas, citas o hallazgos.
No uses otras fuentes. Los datos son preliminares y requieren revisión.
"""

class Fact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    campo: str = Field(min_length=1, max_length=100)
    valor: str = Field(min_length=1, max_length=6000)
    pagina: int | None = Field(default=None, ge=1)
    evidencia: str | None = Field(default=None, max_length=1000)

class GeneralAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tipo_documental: str = Field(min_length=1, max_length=140)
    resumen: str = Field(min_length=1, max_length=6000)
    campos: list[Fact] = Field(default_factory=list, max_length=15)
    alertas: list[str] = Field(default_factory=list, max_length=6)

    @field_validator("alertas")
    @classmethod
    def limit_alerts(cls, value: list[str]) -> list[str]:
        if any(len(item) > 800 for item in value):
            raise ValueError("Una alerta excede el límite.")
        return value


@dataclass(frozen=True)
class GeneralOutcome:
    cache: CacheKey
    report: GeneralAnalysis
    cached: bool
    input_tokens: int | None
    output_tokens: int | None


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def gemini_document(pdf_bytes: bytes, api_key: str, *, model: str) -> tuple[GeneralAnalysis, int | None, int | None]:
    from google import genai
    from google.genai import types, errors as google_errors

    client = genai.Client(api_key=api_key)
    try:
        try:
            response = client.models.generate_content(
                model=model,
                contents=[
                    types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                    GENERAL_PROMPT,
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_json_schema=GENERAL_SCHEMA,
                ),
            )
        except google_errors.APIError as exc:
            raise GeminiRequestError(exc.code, exc.status) from None
        raw = getattr(response, "parsed", None)
        if raw is None:
            raw = getattr(response, "text", None)
        if isinstance(raw, str):
            report = GeneralAnalysis.model_validate_json(raw)
        else:
            report = GeneralAnalysis.model_validate(raw)
        usage = getattr(response, "usage_metadata", None)
        return (
            report,
            getattr(usage, "prompt_token_count", None),
            getattr(usage, "candidates_token_count", None),
        )
    finally:
        client.close()


def analyze_document(
    sheets: Any, sheet_id: str, pdf_bytes: bytes, document: DocumentRecord,
    obra_id: str, api_key: str, *, model: str = DEFAULT_MODEL,
    invoke: Callable[..., tuple[GeneralAnalysis, int | None, int | None]] = gemini_document,
) -> GeneralOutcome:
    """Idempotencia por clave; ante fallos no reintentar ni sobrescribir datos.

    El llamador serializa la transacción con el bloqueo del proceso Streamlit.
    """
    cache = crear_clave_cache(
        pdf_bytes, modelo=model, version_prompt=GENERAL_PROMPT_VERSION,
        version_esquema=GENERAL_SCHEMA_VERSION, tipo_documento=GENERAL_KIND,
    )
    tables = _sheet_rows(sheets, sheet_id)
    doc_row = _find_unique(tables["Documentos"], 0, document.id)
    if not doc_row:
        raise ExtractionStateError("Primero registra el PDF con Actualizar Drive.")
    number, registered = doc_row
    if (
        registered[1] != obra_id or registered[11] != "SI"
        or registered[5] != document.md5_checksum
    ):
        raise ExtractionStateError("El registro de Drive no coincide con el PDF vigente.")
    previous = _find_unique(tables["Extracciones"], 0, cache.clave)
    if previous:
        index, row = previous
        if row[2] != document.id or row[3] != obra_id:
            raise ExtractionStateError(
                "Existe contenido idéntico asociado a otro PDF. "
                "No se reanalizará automáticamente; revisar el registro."
            )
        if row[1] == COMPLETE and row[10]:
            report = GeneralAnalysis.model_validate_json(row[10])
            return GeneralOutcome(
                cache, report, True,
                int(row[11]) if row[11] else None,
                int(row[12]) if row[12] else None,
            )
        raise ExtractionStateError(
            "Hay una solicitud previa sin resultado confirmado para este PDF. "
            "No se realizará una nueva llamada automática."
        )

    index = len(tables["Extracciones"]) + 2
    created = _utc()
    reservation = [
        cache.clave, IN_PROGRESS, document.id, obra_id, cache.contenido_sha256,
        model, GENERAL_PROMPT_VERSION, GENERAL_SCHEMA_VERSION,
        created, created, "", "", "", "",
    ]
    _batch_write(sheets, sheet_id, [("Extracciones", index, reservation)])
    phase = "MODEL"
    try:
        report, input_tokens, output_tokens = invoke(pdf_bytes, api_key, model=model)
        if not isinstance(report, GeneralAnalysis):
            raise ValueError("Gemini no devolvió una ficha documental válida.")
        payload = report.model_dump_json(exclude_none=False)
        if len(payload) > 40000:
            raise ValueError("La ficha supera el tamaño permitido en Sheets.")
        final = [
            cache.clave, COMPLETE, document.id, obra_id, cache.contenido_sha256,
            model, GENERAL_PROMPT_VERSION, GENERAL_SCHEMA_VERSION,
            created, _utc(), payload, str(input_tokens or ""),
            str(output_tokens or ""), "",
        ]
        phase = "SAVE"
        _write_regions(sheets, sheet_id, [
            {"range": f"'Extracciones'!A{index}:N{index}", "values": [final]},
            {"range": f"'Documentos'!I{number}", "values": [["Analizado"]]},
            {"range": f"'Documentos'!M{number}:O{number}",
             "values": [[f"{model}:{GENERAL_PROMPT_VERSION}", cache.clave, ""]]},
        ])
        return GeneralOutcome(cache, report, False, input_tokens, output_tokens)
    except Exception as exc:
        if phase == "SAVE":
            raise ExtractionStateError(
                "Gemini generó una ficha, pero Sheets no confirmó su guardado. "
                "Revisa Extracciones antes de intentar nuevamente."
            ) from None
        reservation[1] = UNCERTAIN
        reservation[9] = _utc()
        code = exc.public_code if isinstance(exc, GeminiRequestError) else type(exc).__name__[:80]
        reservation[13] = code
        try:
            _batch_write(sheets, sheet_id, [("Extracciones", index, reservation)])
        except Exception:
            pass
        raise ExtractionStateError(
            f"No se confirmó el análisis documental ({code}). "
            "El reintento automático quedó bloqueado."
        ) from None
