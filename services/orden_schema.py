"""ORDEN_AD-v1: extracción documental literal de una orden de adjudicación.

Conserva plazos, personal designado, fundamentos y documentos citados.
No infiere cumplimiento ni sustituye la notificación o el contrato.
"""
from __future__ import annotations
import json
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from services.contract_v2 import LiteralEvidence

ORDEN_SCHEMA_VERSION = "orden-ad-v1"
ORDEN_FIELDS = (
    "numero_orden",
    "fecha_emision",
    "contratista",
    "representante_legal",
    "nombre_obra",
    "localidad",
    "tipo_adjudicacion",
    "monto_adjudicado",
    "dependencia_emisora",
    "area_emisora",
    "fundamento_adjudicacion",
    "numero_contrato_referido",
    "fecha_contrato_referido",
    "direccion_supervision",
    "supervisor_principal",
    "telefono_supervisor",
    "autoridad_firmante",
    "cargo_firmante",
    "codigo_formato",
    "revision_formato",
    "fecha_revision_formato",
    "fuente_financiamiento",
)
ORDEN_LABELS = (
    ("numero_orden", "Número o consecutivo de la orden"),
    ("fecha_emision", "Fecha de emisión de la orden"),
    ("contratista", "Contratista o razón social"),
    ("representante_legal", "Representante legal del contratista"),
    ("nombre_obra", "Nombre de la obra o servicio"),
    ("localidad", "Localidad de la obra"),
    ("tipo_adjudicacion", "Tipo de adjudicación indicado"),
    ("monto_adjudicado", "Monto adjudicado"),
    ("dependencia_emisora", "Dependencia emisora"),
    ("area_emisora", "Área administrativa emisora"),
    ("fundamento_adjudicacion", "Fundamento citado de la adjudicación"),
    ("numero_contrato_referido", "Número de contrato referido"),
    ("fecha_contrato_referido", "Fecha de contrato referida"),
    ("direccion_supervision", "Dirección a cargo de supervisión"),
    ("supervisor_principal", "Nombre del supervisor principal"),
    ("telefono_supervisor", "Teléfono de contacto del supervisor"),
    ("autoridad_firmante", "Autoridad o persona firmante"),
    ("cargo_firmante", "Cargo de la persona firmante"),
    ("codigo_formato", "Código del formato"),
    ("revision_formato", "Revisión del formato"),
    ("fecha_revision_formato", "Fecha de revisión del formato"),
    ("fuente_financiamiento", "Fuente de financiamiento"),
)
ORDEN_HEADERS = (
    "cache_key", "obra_id", "documento_id",
    *ORDEN_FIELDS,
    "personal_designado_json", "instrucciones_json", "fundamentos_json",
    "documentos_referidos_json", "firma_aparente_json",
    "observaciones_json", "extraido_utc",
)


class PersonalDesignadoOrden(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombre: str = Field(min_length=1, max_length=800)
    funcion: str | None = Field(default=None, max_length=700)
    direccion: str | None = Field(default=None, max_length=850)
    telefono: str | None = Field(default=None, max_length=450)
    pagina: int | None = Field(default=None, ge=1)
    evidencia: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def valid(self):
        if not self.nombre.strip():
            raise ValueError("El nombre debe estar respaldado en la orden.")
        return self


class InstruccionOrden(BaseModel):
    model_config = ConfigDict(extra="forbid")
    obligacion: str = Field(min_length=1, max_length=2500)
    plazo_literal: str | None = Field(default=None, max_length=900)
    evento_inicio_plazo: str | None = Field(default=None, max_length=1300)
    condicion: str | None = Field(default=None, max_length=1500)
    consecuencia_literal: str | None = Field(default=None, max_length=1500)
    destinatario: str | None = Field(default=None, max_length=850)
    pagina: int | None = Field(default=None, ge=1)
    evidencia: str | None = Field(default=None, max_length=2500)


class FundamentoOrden(BaseModel):
    model_config = ConfigDict(extra="forbid")
    norma: str | None = Field(default=None, max_length=1500)
    articulos: str | None = Field(default=None, max_length=1200)
    pagina: int | None = Field(default=None, ge=1)
    evidencia: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def identified(self):
        if not self.norma and not self.articulos:
            raise ValueError("Cada fundamento debe citar norma o artículos.")
        return self


class DocumentoReferidoOrden(BaseModel):
    model_config = ConfigDict(extra="forbid")
    documento: str = Field(min_length=1, max_length=1200)
    finalidad: str | None = Field(default=None, max_length=1400)
    pagina: int | None = Field(default=None, ge=1)
    evidencia: str | None = Field(default=None, max_length=2100)


class FirmaAparenteOrden(BaseModel):
    model_config = ConfigDict(extra="forbid")
    presencia: Literal["visible", "no_visible", "indeterminada"]
    pagina: int | None = Field(default=None, ge=1)
    nota_visual: str | None = Field(default=None, max_length=850)


class OrdenAdV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    numero_orden: LiteralEvidence
    fecha_emision: LiteralEvidence
    contratista: LiteralEvidence
    representante_legal: LiteralEvidence
    nombre_obra: LiteralEvidence
    localidad: LiteralEvidence
    tipo_adjudicacion: LiteralEvidence
    monto_adjudicado: LiteralEvidence
    dependencia_emisora: LiteralEvidence
    area_emisora: LiteralEvidence
    fundamento_adjudicacion: LiteralEvidence
    numero_contrato_referido: LiteralEvidence
    fecha_contrato_referido: LiteralEvidence
    direccion_supervision: LiteralEvidence
    supervisor_principal: LiteralEvidence
    telefono_supervisor: LiteralEvidence
    autoridad_firmante: LiteralEvidence
    cargo_firmante: LiteralEvidence
    codigo_formato: LiteralEvidence
    revision_formato: LiteralEvidence
    fecha_revision_formato: LiteralEvidence
    fuente_financiamiento: LiteralEvidence

    personal_designado: list[PersonalDesignadoOrden] = Field(default_factory=list, max_length=50)
    instrucciones: list[InstruccionOrden] = Field(default_factory=list, max_length=60)
    fundamentos: list[FundamentoOrden] = Field(default_factory=list, max_length=50)
    documentos_referidos: list[DocumentoReferidoOrden] = Field(default_factory=list, max_length=55)
    firma_aparente: FirmaAparenteOrden
    observaciones: list[str] = Field(default_factory=list, max_length=40)

    def flat_values(self) -> list[str]:
        return [(getattr(self, f).valor or "") for f in ORDEN_FIELDS]


def _nullable() -> dict[str, Any]:
    return {"type": ["string", "null"]}


def _items(props: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": {
        "type": "object", "properties": props, "required": list(props),
    }}


ORDEN_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "campos": _items({
            "campo": {"type": "string"},
            "valor": _nullable(), "pagina": {"type": ["integer", "null"]},
            "evidencia": _nullable(),
        }),
        "personal_designado": _items({
            "nombre": {"type": "string"},
            "funcion": _nullable(),
            "direccion": _nullable(), "telefono": _nullable(),
            "pagina": {"type": ["integer", "null"]}, "evidencia": _nullable(),
        }),
        "instrucciones": _items({
            "obligacion": {"type": "string"}, "plazo_literal": _nullable(),
            "evento_inicio_plazo": _nullable(), "condicion": _nullable(),
            "consecuencia_literal": _nullable(), "destinatario": _nullable(),
            "pagina": {"type": ["integer", "null"]}, "evidencia": _nullable(),
        }),
        "fundamentos": _items({
            "norma": _nullable(), "articulos": _nullable(),
            "pagina": {"type": ["integer", "null"]}, "evidencia": _nullable(),
        }),
        "documentos_referidos": _items({
            "documento": {"type": "string"}, "finalidad": _nullable(),
            "pagina": {"type": ["integer", "null"]}, "evidencia": _nullable(),
        }),
        "firma_aparente": {
            "type": "object",
            "properties": {
                "presencia": {"type": "string", "enum": [
                    "visible", "no_visible", "indeterminada",
                ]},
                "pagina": {"type": ["integer", "null"]},
                "nota_visual": _nullable(),
            },
            "required": ["presencia", "pagina", "nota_visual"],
        },
        "observaciones": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "campos", "personal_designado", "instrucciones", "fundamentos",
        "documentos_referidos", "firma_aparente", "observaciones",
    ],
}


def parse_orden(payload: dict[str, Any] | str) -> OrdenAdV1:
    if isinstance(payload, str):
        try:
            raw = json.loads(payload)
        except (ValueError, TypeError) as exc:
            raise ValueError("La orden no contiene JSON válido.") from exc
    else:
        raw = payload
    if not isinstance(raw, dict) or set(raw) != set(ORDEN_RESPONSE_SCHEMA["required"]):
        raise ValueError("Respuesta de orden con estructura inesperada.")
    data = raw["campos"]
    if not isinstance(data, list) or len(data) > len(ORDEN_FIELDS):
        raise ValueError("Lista de campos de la orden incorrecta.")
    for name, max_size in (
        ("personal_designado", 50), ("instrucciones", 60),
        ("fundamentos", 50), ("documentos_referidos", 55),
        ("observaciones", 40),
    ):
        if not isinstance(raw[name], list) or len(raw[name]) > max_size:
            raise ValueError(f"Lista {name} no válida.")
    if any(not isinstance(x, str) for x in raw["observaciones"]):
        raise ValueError("Las observaciones deben contener texto.")
    observed: dict[str, LiteralEvidence] = {}
    for item in data:
        if not isinstance(item, dict) or set(item) != {"campo", "valor", "pagina", "evidencia"}:
            raise ValueError("Campo de orden con propiedades inesperadas.")
        name = item["campo"]
        if not isinstance(name, str) or name not in ORDEN_FIELDS or name in observed:
            raise ValueError("Campo de orden duplicado o desconocido.")
        observed[name] = LiteralEvidence.model_validate({
            "valor": item["valor"], "pagina": item["pagina"],
            "evidencia": item["evidencia"],
        })
    missing = [key for key in ORDEN_FIELDS if key not in observed]
    observed.update({key: LiteralEvidence(valor=None) for key in missing})
    result = OrdenAdV1.model_validate({
        **observed,
        "personal_designado": raw["personal_designado"],
        "instrucciones": raw["instrucciones"],
        "fundamentos": raw["fundamentos"],
        "documentos_referidos": raw["documentos_referidos"],
        "firma_aparente": raw["firma_aparente"],
        "observaciones": raw["observaciones"] + [
            f"No devuelto por el modelo: {key}" for key in missing
        ],
    })
    if not any(
        getattr(result, name).valor
        for name in ("numero_orden", "nombre_obra", "contratista")
    ):
        raise ValueError("No se identificó ningún dato básico de la orden.")
    return result
