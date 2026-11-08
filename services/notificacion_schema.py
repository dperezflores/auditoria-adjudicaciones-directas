"""NOTIFICACION_AD-v1: extracción de notificación, acuse y plazos literales.

No prueba cumplimiento. No equipara emisión y recepción ni confunde
el registro del contratista con el registro de supervisión externa.
"""
from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from services.contract_v2 import LiteralEvidence

NOTIFICACION_SCHEMA_VERSION = "notificacion-ad-v1"
NOTIFICACION_FIELDS = (
    "numero_notificacion",
    "fecha_emision",
    "fecha_recepcion_acuse",
    "destinatario",
    "contratista",
    "representante_contratista",
    "registro_puc_contratista",
    "nombre_obra",
    "localidad",
    "modalidad_adjudicacion",
    "monto_adjudicado",
    "dependencia_emisora",
    "unidad_administrativa",
    "referencia_dictamen",
    "fecha_dictamen_referido",
    "autoridad_emisora",
    "cargo_autoridad",
    "codigo_formato",
    "revision_formato",
    "fecha_revision_formato",
    "fuente_financiamiento",
)
NOTIFICACION_LABELS = (
    ("numero_notificacion", "Número o folio de la notificación"),
    ("fecha_emision", "Fecha de emisión"),
    ("fecha_recepcion_acuse", "Fecha efectiva de recepción o acuse"),
    ("destinatario", "Persona destinataria de la notificación"),
    ("contratista", "Contratista (nombre o razón social)"),
    ("representante_contratista", "Representante del contratista"),
    ("registro_puc_contratista", "Registro PUC del contratista"),
    ("nombre_obra", "Nombre de la obra"),
    ("localidad", "Localidad de la obra"),
    ("modalidad_adjudicacion", "Modalidad de adjudicación"),
    ("monto_adjudicado", "Monto adjudicado"),
    ("dependencia_emisora", "Dependencia emisora"),
    ("unidad_administrativa", "Unidad administrativa"),
    ("referencia_dictamen", "Referencia o folio del dictamen"),
    ("fecha_dictamen_referido", "Fecha del dictamen referido"),
    ("autoridad_emisora", "Autoridad que emite"),
    ("cargo_autoridad", "Cargo de la autoridad emisora"),
    ("codigo_formato", "Código del formato"),
    ("revision_formato", "Revisión del formato"),
    ("fecha_revision_formato", "Fecha de revisión del formato"),
    ("fuente_financiamiento", "Fuente de financiamiento"),
)
NOTIFICACION_HEADERS = (
    "cache_key", "obra_id", "documento_id",
    *NOTIFICACION_FIELDS,
    "supervisores_json", "obligaciones_json",
    "fundamentos_json", "acuse_aparente_json",
    "observaciones_json", "extraido_utc",
)


class PersonalDesignado(BaseModel):
    model_config = ConfigDict(extra="forbid")
    funcion: Literal["supervision_externa", "coordinacion_interna", "supervision_interna", "otro"]
    nombre: str = Field(min_length=1, max_length=700)
    cargo: str | None = Field(default=None, max_length=600)
    registro_puc: str | None = Field(default=None, max_length=300)
    pagina: int | None = Field(default=None, ge=1)
    evidencia: str | None = Field(default=None, max_length=1800)

    @model_validator(mode="after")
    def valid_name(self):
        if not self.nombre.strip():
            raise ValueError("El personal debe tener un nombre legible.")
        return self


class ObligacionNotificada(BaseModel):
    model_config = ConfigDict(extra="forbid")
    obligacion: str = Field(min_length=1, max_length=2200)
    plazo_literal: str | None = Field(default=None, max_length=800)
    evento_inicio_plazo: str | None = Field(default=None, max_length=1100)
    condicion: str | None = Field(default=None, max_length=1000)
    destinatario: str | None = Field(default=None, max_length=600)
    fundamento_citado: str | None = Field(default=None, max_length=1000)
    pagina: int | None = Field(default=None, ge=1)
    evidencia: str | None = Field(default=None, max_length=2200)


class FundamentoNotificacion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    norma: str | None = Field(default=None, max_length=1200)
    articulos: str | None = Field(default=None, max_length=1200)
    pagina: int | None = Field(default=None, ge=1)
    evidencia: str | None = Field(default=None, max_length=1800)

    @model_validator(mode="after")
    def identified(self):
        if not self.norma and not self.articulos:
            raise ValueError("Fundamento sin norma ni artículos.")
        return self


class AcuseAparente(BaseModel):
    """Descripción visual, nunca prueba automática de fecha de recepción."""
    model_config = ConfigDict(extra="forbid")
    presencia: Literal["visible", "no_visible", "indeterminada"]
    fecha_legible: str | None = Field(default=None, max_length=250)
    pagina: int | None = Field(default=None, ge=1)
    nota_visual: str | None = Field(default=None, max_length=900)


class NotificacionAdV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    numero_notificacion: LiteralEvidence
    fecha_emision: LiteralEvidence
    fecha_recepcion_acuse: LiteralEvidence
    destinatario: LiteralEvidence
    contratista: LiteralEvidence
    representante_contratista: LiteralEvidence
    registro_puc_contratista: LiteralEvidence
    nombre_obra: LiteralEvidence
    localidad: LiteralEvidence
    modalidad_adjudicacion: LiteralEvidence
    monto_adjudicado: LiteralEvidence
    dependencia_emisora: LiteralEvidence
    unidad_administrativa: LiteralEvidence
    referencia_dictamen: LiteralEvidence
    fecha_dictamen_referido: LiteralEvidence
    autoridad_emisora: LiteralEvidence
    cargo_autoridad: LiteralEvidence
    codigo_formato: LiteralEvidence
    revision_formato: LiteralEvidence
    fecha_revision_formato: LiteralEvidence
    fuente_financiamiento: LiteralEvidence

    supervisores: list[PersonalDesignado] = Field(default_factory=list, max_length=60)
    obligaciones: list[ObligacionNotificada] = Field(default_factory=list, max_length=70)
    fundamentos: list[FundamentoNotificacion] = Field(default_factory=list, max_length=60)
    acuse_aparente: AcuseAparente
    observaciones: list[str] = Field(default_factory=list, max_length=40)

    def flat_values(self) -> list[str]:
        return [(getattr(self, field).valor or "") for field in NOTIFICACION_FIELDS]


def _array(props: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": {"type": "object",
            "properties": props, "required": list(props)}}


def _nullable() -> dict[str, Any]:
    return {"type": ["string", "null"]}


NOTIFICACION_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "campos": _array({
            "campo": {"type": "string"},
            "valor": _nullable(),
            "pagina": {"type": ["integer", "null"]},
            "evidencia": _nullable(),
        }),
        "supervisores": _array({
            "funcion": {"type": "string", "enum": [
                "supervision_externa", "coordinacion_interna", "supervision_interna", "otro",
            ]},
            "nombre": {"type": "string"}, "cargo": _nullable(),
            "registro_puc": _nullable(), "pagina": {"type": ["integer", "null"]},
            "evidencia": _nullable(),
        }),
        "obligaciones": _array({
            "obligacion": {"type": "string"},
            "plazo_literal": _nullable(),
            "evento_inicio_plazo": _nullable(),
            "condicion": _nullable(),
            "destinatario": _nullable(),
            "fundamento_citado": _nullable(),
            "pagina": {"type": ["integer", "null"]},
            "evidencia": _nullable(),
        }),
        "fundamentos": _array({
            "norma": _nullable(), "articulos": _nullable(),
            "pagina": {"type": ["integer", "null"]},
            "evidencia": _nullable(),
        }),
        "acuse_aparente": {
            "type": "object",
            "properties": {
                "presencia": {"type": "string", "enum": [
                    "visible", "no_visible", "indeterminada",
                ]},
                "fecha_legible": _nullable(),
                "pagina": {"type": ["integer", "null"]},
                "nota_visual": _nullable(),
            },
            "required": ["presencia", "fecha_legible", "pagina", "nota_visual"],
        },
        "observaciones": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "campos", "supervisores", "obligaciones", "fundamentos",
        "acuse_aparente", "observaciones",
    ],
}


def parse_notificacion(payload: dict[str, Any] | str) -> NotificacionAdV1:
    if isinstance(payload, str):
        try:
            raw = json.loads(payload)
        except (ValueError, TypeError) as exc:
            raise ValueError("La respuesta de notificación no es JSON válido.") from exc
    else:
        raw = payload
    if not isinstance(raw, dict) or set(raw) != set(NOTIFICACION_RESPONSE_SCHEMA["required"]):
        raise ValueError("La respuesta tiene una estructura de notificación incorrecta.")
    data = raw["campos"]
    if not isinstance(data, list) or len(data) > len(NOTIFICACION_FIELDS):
        raise ValueError("Cantidad de campos de notificación incorrecta.")
    for key, limit in (("supervisores", 60), ("obligaciones", 70),
                       ("fundamentos", 60), ("observaciones", 40)):
        if not isinstance(raw[key], list) or len(raw[key]) > limit:
            raise ValueError(f"La lista {key} excede la longitud o tipo permitido.")
    if any(not isinstance(x, str) for x in raw["observaciones"]):
        raise ValueError("Las observaciones requieren texto.")
    values: dict[str, LiteralEvidence] = {}
    for item in data:
        if not isinstance(item, dict) or set(item) != {"campo", "valor", "pagina", "evidencia"}:
            raise ValueError("Campo de notificación con estructura incorrecta.")
        name = item["campo"]
        if not isinstance(name, str) or name not in NOTIFICACION_FIELDS or name in values:
            raise ValueError("Campo de notificación desconocido o repetido.")
        values[name] = LiteralEvidence.model_validate({
            "valor": item["valor"], "pagina": item["pagina"], "evidencia": item["evidencia"],
        })
    missing = [k for k in NOTIFICACION_FIELDS if k not in values]
    values.update({k: LiteralEvidence(valor=None) for k in missing})
    result = NotificacionAdV1.model_validate({
        **values,
        "supervisores": raw["supervisores"],
        "obligaciones": raw["obligaciones"],
        "fundamentos": raw["fundamentos"],
        "acuse_aparente": raw["acuse_aparente"],
        "observaciones": raw["observaciones"] + [
            f"No devuelto por el modelo: {k}" for k in missing
        ],
    })
    if not any(getattr(result, key).valor for key in (
        "numero_notificacion", "contratista", "nombre_obra"
    )):
        raise ValueError("No se localizó ningún identificador de notificación.")
    return result
