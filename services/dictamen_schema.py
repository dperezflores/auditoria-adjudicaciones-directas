"""DICTAMEN_AD-v1. Extracción textual literal, citas jurídicas y motivación.

No determina legalidad del procedimiento, solvencia ni correspondencia de
especialidad. Cada dato se vincula a la página y al fragmento documental.
"""
from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from services.contract_v2 import LiteralEvidence

DICTAMEN_SCHEMA_VERSION = "dictamen-ad-v1"
DICTAMEN_FIELDS = ("numero_dictamen", "fecha_emision", "dependencia_emisora", "unidad_administrativa", "contratista", "representante_contratista", "registro_puc", "nombre_obra", "localidad", "modalidad_adjudicacion", "monto_asignado", "fecha_probable_inicio", "plazo_ejecucion", "autoridad_firmante", "cargo_autoridad", "codigo_formato", "revision_formato", "fecha_revision_formato", "fuente_financiamiento",)
DICTAMEN_LABELS = (
    ("numero_dictamen", "Número de dictamen"),
    ("fecha_emision", "Fecha de emisión del dictamen"),
    ("dependencia_emisora", "Dependencia emisora"),
    ("unidad_administrativa", "Unidad administrativa"),
    ("contratista", "Contratista (nombre o razón social)"),
    ("representante_contratista", "Representante del contratista"),
    ("registro_puc", "Número de registro PUC"),
    ("nombre_obra", "Nombre de la obra"),
    ("localidad", "Localidad"),
    ("modalidad_adjudicacion", "Modalidad de adjudicación"),
    ("monto_asignado", "Monto asignado"),
    ("fecha_probable_inicio", "Fecha probable de inicio"),
    ("plazo_ejecucion", "Plazo de ejecución"),
    ("autoridad_firmante", "Autoridad que autoriza"),
    ("cargo_autoridad", "Cargo de la autoridad"),
    ("codigo_formato", "Código del formato"),
    ("revision_formato", "Revisión del formato"),
    ("fecha_revision_formato", "Fecha de revisión del formato"),
    ("fuente_financiamiento", "Fuente de financiamiento (si se indica)"),
)
DICTAMEN_HEADERS = (
    "cache_key", "obra_id", "documento_id",
    *DICTAMEN_FIELDS,
    "fundamentos_json", "motivaciones_json", "soportes_json",
    "firma_aparente_json", "observaciones_json", "extraido_utc",
)


class FundamentoJuridico(BaseModel):
    model_config = ConfigDict(extra="forbid")
    norma: str | None = Field(default=None, max_length=1200)
    articulos: str | None = Field(default=None, max_length=1200)
    texto_citado: str | None = Field(default=None, max_length=2000)
    pagina: int | None = Field(default=None, ge=1)
    evidencia: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def identified(self):
        if not self.norma and not self.articulos:
            raise ValueError("Cada fundamento requiere norma o artículo explícito.")
        return self


class MotivoAdjudicacion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tema: Literal[
        "experiencia", "especialidad", "vigencia_puc",
        "mejores_condiciones", "justificacion_adjudicacion",
        "seleccion_contratista", "capacidad_respuesta", "otro",
    ]
    afirmacion: str = Field(min_length=1, max_length=2300)
    soporte_mencionado: str | None = Field(default=None, max_length=850)
    pagina: int | None = Field(default=None, ge=1)
    evidencia: str | None = Field(default=None, max_length=2300)

    @model_validator(mode="after")
    def nonempty(self):
        if not self.afirmacion.strip():
            raise ValueError("La afirmación documental debe tener texto.")
        return self


class SoporteMencionado(BaseModel):
    model_config = ConfigDict(extra="forbid")
    documento: str = Field(min_length=1, max_length=1100)
    finalidad_citada: str | None = Field(default=None, max_length=1100)
    pagina: int | None = Field(default=None, ge=1)
    evidencia: str | None = Field(default=None, max_length=1600)


class IndicadorFirma(BaseModel):
    """Apreciación visual preliminar, NO valor literal ni autenticación."""
    model_config = ConfigDict(extra="forbid")
    presencia: Literal["visible", "no_visible", "indeterminada"] = "indeterminada"
    pagina: int | None = Field(default=None, ge=1)
    nota_visual: str | None = Field(default=None, max_length=700)


class DictamenAdV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    numero_dictamen: LiteralEvidence
    fecha_emision: LiteralEvidence
    dependencia_emisora: LiteralEvidence
    unidad_administrativa: LiteralEvidence
    contratista: LiteralEvidence
    representante_contratista: LiteralEvidence
    registro_puc: LiteralEvidence
    nombre_obra: LiteralEvidence
    localidad: LiteralEvidence
    modalidad_adjudicacion: LiteralEvidence
    monto_asignado: LiteralEvidence
    fecha_probable_inicio: LiteralEvidence
    plazo_ejecucion: LiteralEvidence
    autoridad_firmante: LiteralEvidence
    cargo_autoridad: LiteralEvidence
    codigo_formato: LiteralEvidence
    revision_formato: LiteralEvidence
    fecha_revision_formato: LiteralEvidence
    fuente_financiamiento: LiteralEvidence

    fundamentos: list[FundamentoJuridico] = Field(default_factory=list, max_length=60)
    motivaciones: list[MotivoAdjudicacion] = Field(default_factory=list, max_length=45)
    soportes: list[SoporteMencionado] = Field(default_factory=list, max_length=45)
    firma_aparente: IndicadorFirma = Field(default_factory=IndicadorFirma)
    observaciones: list[str] = Field(default_factory=list, max_length=35)

    def flat_values(self) -> list[str]:
        return [(getattr(self, field).valor or "") for field in DICTAMEN_FIELDS]


def _nullable_str(max_chars: int) -> dict[str, Any]:
    return {"type": ["string", "null"]}


def _array_of(props: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": props,
            "required": list(props),
        },
    }


DICTAMEN_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "campos": _array_of({
            "campo": {"type": "string"},
            "valor": _nullable_str(1000),
            "pagina": {"type": ["integer", "null"]},
            "evidencia": _nullable_str(2000),
        }),
        "fundamentos": _array_of({
            "norma": _nullable_str(1200),
            "articulos": _nullable_str(1200),
            "texto_citado": _nullable_str(2000),
            "pagina": {"type": ["integer", "null"]},
            "evidencia": _nullable_str(2000),
        }),
        "motivaciones": _array_of({
            "tema": {"type": "string", "enum": [
                "experiencia", "especialidad", "vigencia_puc",
                "mejores_condiciones", "justificacion_adjudicacion",
                "seleccion_contratista", "capacidad_respuesta", "otro",
            ]},
            "afirmacion": {"type": "string"},
            "soporte_mencionado": _nullable_str(850),
            "pagina": {"type": ["integer", "null"]},
            "evidencia": _nullable_str(2300),
        }),
        "soportes": _array_of({
            "documento": {"type": "string"},
            "finalidad_citada": _nullable_str(1100),
            "pagina": {"type": ["integer", "null"]},
            "evidencia": _nullable_str(1600),
        }),
        "firma_aparente": {
            "type": "object",
            "properties": {
                "presencia": {"type": "string", "enum": ["visible", "no_visible", "indeterminada"]},
                "pagina": {"type": ["integer", "null"]},
                "nota_visual": _nullable_str(700),
            },
            "required": ["presencia", "pagina", "nota_visual"],
        },
        "observaciones": {
            "type": "array", "items": {"type": "string"},
        },
    },
    "required": [
        "campos", "fundamentos", "motivaciones", "soportes",
        "firma_aparente", "observaciones",
    ],
}


def parse_dictamen(payload: dict[str, Any] | str) -> DictamenAdV1:
    if isinstance(payload, str):
        try:
            raw = json.loads(payload)
        except (ValueError, TypeError) as exc:
            raise ValueError("La respuesta del dictamen no es JSON válido.") from exc
    else:
        raw = payload
    if not isinstance(raw, dict) or set(raw) != set(DICTAMEN_RESPONSE_SCHEMA["required"]):
        raise ValueError("Respuesta del dictamen con propiedades inesperadas.")
    items = raw["campos"]
    if not isinstance(items, list) or len(items) > len(DICTAMEN_FIELDS):
        raise ValueError("Cantidad de campos del dictamen incorrecta.")
    for key, maximum in (("fundamentos",60),("motivaciones",45),
                          ("soportes",45),("observaciones",35)):
        if not isinstance(raw[key], list) or len(raw[key]) > maximum:
            raise ValueError(f"Lista {key} con tipo o tamaño no permitido.")
    if any(not isinstance(x, str) for x in raw["observaciones"]):
        raise ValueError("Las observaciones deben ser cadenas.")

    validated: dict[str, LiteralEvidence] = {}
    for item in items:
        if not isinstance(item, dict) or set(item) != {"campo","valor","pagina","evidencia"}:
            raise ValueError("Campo documental del dictamen no válido.")
        name = item["campo"]
        if not isinstance(name, str) or name not in DICTAMEN_FIELDS or name in validated:
            raise ValueError("Campo del dictamen desconocido o duplicado.")
        validated[name] = LiteralEvidence.model_validate({
            "valor": item["valor"], "pagina": item["pagina"],
            "evidencia": item["evidencia"],
        })
    missing = [key for key in DICTAMEN_FIELDS if key not in validated]
    validated.update({key: LiteralEvidence(valor=None) for key in missing})
    report = DictamenAdV1.model_validate({
        **validated,
        "fundamentos": raw["fundamentos"],
        "motivaciones": raw["motivaciones"],
        "soportes": raw["soportes"],
        "firma_aparente": raw["firma_aparente"],
        "observaciones": raw["observaciones"] + [
            f"No devuelto por el modelo: {field}" for field in missing
        ],
    })
    if not any(
        getattr(report, name).valor
        for name in ("numero_dictamen", "contratista", "nombre_obra")
    ):
        raise ValueError("No se identificó un dictamen; faltan datos básicos.")
    return report
