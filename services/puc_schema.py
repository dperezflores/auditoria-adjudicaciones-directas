"""PUC-v1: transcripción literal y evidencia del Padrón Único de Contratistas.

Los campos NO se infieren ni normalizan: las comparaciones y fechas derivadas
se prepararán en una fase posterior. No es una prueba de cumplimiento.
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from services.contract_v2 import LiteralEvidence

PUC_SCHEMA_VERSION = "puc-v1"

PUC_FIELDS = (
    "contratista",
    "rfc",
    "numero_registro_puc",
    "estado_registro",
    "fecha_validacion",
    "fecha_impresion",
    "vigencia_desde",
    "vigencia_hasta",
    "representacion_legal",
    "capital_contable",
    "ejercicio_financiero",
    "total_activo",
    "representante_tecnico",
    "profesion_representante_tecnico",
    "cedula_profesional",
    "resultado_evaluacion",
    "domicilio_fiscal",
    "registro_patronal",
)

PUC_LABELS = (
    ("contratista", "Contratista o razón social"),
    ("rfc", "RFC"),
    ("numero_registro_puc", "Número de registro PUC"),
    ("estado_registro", "Estado del registro"),
    ("fecha_validacion", "Fecha de validación"),
    ("fecha_impresion", "Fecha de impresión"),
    ("vigencia_desde", "Inicio de vigencia"),
    ("vigencia_hasta", "Vigencia hasta"),
    ("representacion_legal", "Representación legal"),
    ("capital_contable", "Capital contable"),
    ("ejercicio_financiero", "Ejercicio financiero de referencia"),
    ("total_activo", "Total activo"),
    ("representante_tecnico", "Representante técnico"),
    ("profesion_representante_tecnico", "Profesión del representante técnico"),
    ("cedula_profesional", "Cédula profesional"),
    ("resultado_evaluacion", "Resultado de evaluación"),
    ("domicilio_fiscal", "Domicilio fiscal"),
    ("registro_patronal", "Registro patronal"),
)

PUC_HEADERS = (
    "cache_key", "obra_id", "documento_id",
    *PUC_FIELDS,
    "especialidades_json", "observaciones_json", "extraido_utc",
)


class PucSpecialty(BaseModel):
    model_config = ConfigDict(extra="forbid")
    categoria: str | None = Field(default=None, max_length=1000)
    actividad: str | None = Field(default=None, max_length=1500)
    tipo_marcado: str | None = Field(default=None, max_length=250)
    aportada_por: str | None = Field(default=None, max_length=650)
    pagina: int | None = Field(default=None, ge=1)
    evidencia: str | None = Field(default=None, max_length=1800)

    @model_validator(mode="after")
    def nonempty_specialty(self):
        if not self.categoria and not self.actividad:
            raise ValueError("La especialidad debe contener categoría o actividad.")
        return self


class PucExtractionV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contratista: LiteralEvidence
    rfc: LiteralEvidence
    numero_registro_puc: LiteralEvidence
    estado_registro: LiteralEvidence
    fecha_validacion: LiteralEvidence
    fecha_impresion: LiteralEvidence
    vigencia_desde: LiteralEvidence
    vigencia_hasta: LiteralEvidence
    representacion_legal: LiteralEvidence
    capital_contable: LiteralEvidence
    ejercicio_financiero: LiteralEvidence
    total_activo: LiteralEvidence
    representante_tecnico: LiteralEvidence
    profesion_representante_tecnico: LiteralEvidence
    cedula_profesional: LiteralEvidence
    resultado_evaluacion: LiteralEvidence
    domicilio_fiscal: LiteralEvidence
    registro_patronal: LiteralEvidence

    especialidades: list[PucSpecialty] = Field(default_factory=list, max_length=120)
    observaciones: list[str] = Field(default_factory=list, max_length=45)

    def flat_values(self) -> list[str]:
        return [(getattr(self, name).valor or "") for name in PUC_FIELDS]

    def fields_to_review(self) -> list[str]:
        # Se enumeran faltantes sin inferir que son omisiones de la autoridad.
        return [name for name in PUC_FIELDS if getattr(self, name).needs_review]


PUC_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "campos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "campo": {"type": "string"},
                    "valor": {"type": ["string", "null"]},
                    "pagina": {"type": ["integer", "null"]},
                    "evidencia": {"type": ["string", "null"]},
                },
                "required": ["campo", "valor", "pagina", "evidencia"],
            },
        },
        "especialidades": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "categoria": {"type": ["string", "null"]},
                    "actividad": {"type": ["string", "null"]},
                    "tipo_marcado": {"type": ["string", "null"]},
                    "aportada_por": {"type": ["string", "null"]},
                    "pagina": {"type": ["integer", "null"]},
                    "evidencia": {"type": ["string", "null"]},
                },
                "required": [
                    "categoria", "actividad", "tipo_marcado",
                    "aportada_por", "pagina", "evidencia",
                ],
            },
        },
        "observaciones": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["campos", "especialidades", "observaciones"],
}


def parse_puc(payload: dict[str, Any] | str) -> PucExtractionV1:
    if isinstance(payload, str):
        try:
            data = json.loads(payload)
        except (TypeError, ValueError) as exc:
            raise ValueError("Gemini no entregó un JSON de PUC legible.") from exc
    else:
        data = payload
    if not isinstance(data, dict) or set(data) != {
        "campos", "especialidades", "observaciones"
    }:
        raise ValueError("Estructura de respuesta PUC incompatible.")
    items = data["campos"]
    specials = data["especialidades"]
    comments = data["observaciones"]
    if (
        not isinstance(items, list) or len(items) > len(PUC_FIELDS)
        or not isinstance(specials, list) or len(specials) > 120
        or not isinstance(comments, list) or len(comments) > 45
        or any(not isinstance(x, str) for x in comments)
    ):
        raise ValueError("Tamaño o tipo de contenido del PUC no permitido.")
    fields: dict[str, LiteralEvidence] = {}
    for item in items:
        if not isinstance(item, dict) or set(item) != {
            "campo", "valor", "pagina", "evidencia"
        }:
            raise ValueError("Campo PUC con estructura incorrecta.")
        name = item["campo"]
        if not isinstance(name, str) or name not in PUC_FIELDS or name in fields:
            raise ValueError("Campo PUC desconocido o repetido.")
        fields[name] = LiteralEvidence.model_validate({
            "valor": item["valor"],
            "pagina": item["pagina"],
            "evidencia": item["evidencia"],
        })
    missing = [name for name in PUC_FIELDS if name not in fields]
    fields.update({name: LiteralEvidence(valor=None) for name in missing})
    result = PucExtractionV1.model_validate({
        **fields,
        "especialidades": specials,
        "observaciones": comments + [
            f"No devuelto por el modelo: {name}" for name in missing
        ],
    })
    if not any(getattr(result, field).valor for field in (
        "contratista", "rfc", "numero_registro_puc"
    )):
        raise ValueError("El PUC no contiene ningún identificador extraído; revisar solicitud.")
    return result
