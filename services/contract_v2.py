"""Contrato v2: transcripción literal y trazabilidad, sin normalizar el PDF.

La clasificación de ámbito legal es DERIVADA de textos citados; no equivale
a una determinación jurídica ni selecciona por sí misma límites de adjudicación.
No se modifica el esquema v1 ni las extracciones antiguas.
"""
from __future__ import annotations

from typing import Any
import json
import re
import unicodedata

from pydantic import BaseModel, ConfigDict, Field, field_validator


CONTRACT_SCHEMA_V2 = "contrato-v2"

CONTRACT_V2_FIELDS = (
    "numero_contrato",
    "obra_servicio",
    "tipo_contrato",
    "contratista",
    "registro_puc",
    "rfc",
    "representante_legal",
    "representante_tecnico",
    "modalidad_adjudicacion",
    "monto_contrato",
    "fecha_inicio_contractual",
    "fecha_termino_contractual",
    "fecha_firma_contrato",
    "anticipo",
    "fuente_financiamiento",
    "legislacion_citada",
)

FIELD_LABELS_V2 = (
    ("numero_contrato", "Número de contrato"),
    ("obra_servicio", "Obra o servicio"),
    ("tipo_contrato", "Tipo de contrato"),
    ("contratista", "Contratista (nombre o razón social)"),
    ("registro_puc", "Número de registro PUC"),
    ("rfc", "RFC"),
    ("representante_legal", "Representante legal"),
    ("representante_tecnico", "Representante técnico"),
    ("modalidad_adjudicacion", "Modalidad de adjudicación"),
    ("monto_contrato", "Monto del contrato"),
    ("fecha_inicio_contractual", "Fecha de inicio contractual"),
    ("fecha_termino_contractual", "Fecha de término contractual"),
    ("fecha_firma_contrato", "Fecha de firma del contrato"),
    ("anticipo", "Anticipo"),
    ("fuente_financiamiento", "Fuente de financiamiento"),
    ("legislacion_citada", "Legislación citada en el contrato"),
)

CONTRACT_V2_HEADERS = (
    "cache_key", "obra_id", "documento_id",
    *CONTRACT_V2_FIELDS,
    "personas_json", "ambito_normativo_preliminar",
    "observaciones_json", "extraido_utc",
)


class LiteralEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    valor: str | None
    pagina: int | None = Field(default=None, ge=1)
    evidencia: str | None = None

    @field_validator("valor", "evidencia", mode="before")
    @classmethod
    def blank_to_none_without_changing_literal(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def needs_review(self) -> bool:
        return self.valor is None or self.pagina is None or not self.evidencia


class ContractParticipant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombre: str = Field(min_length=1, max_length=600)
    cargo_o_caracter: str | None = Field(default=None, max_length=600)
    representacion: str | None = Field(default=None, max_length=600)
    pagina: int | None = Field(default=None, ge=1)
    evidencia: str | None = Field(default=None, max_length=1200)

    @field_validator("nombre")
    @classmethod
    def non_blank_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("El nombre de una persona no puede estar vacío.")
        return v


class ContractExtractionV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    numero_contrato: LiteralEvidence
    obra_servicio: LiteralEvidence
    tipo_contrato: LiteralEvidence
    contratista: LiteralEvidence
    registro_puc: LiteralEvidence
    rfc: LiteralEvidence
    representante_legal: LiteralEvidence
    representante_tecnico: LiteralEvidence
    modalidad_adjudicacion: LiteralEvidence
    monto_contrato: LiteralEvidence
    fecha_inicio_contractual: LiteralEvidence
    fecha_termino_contractual: LiteralEvidence
    fecha_firma_contrato: LiteralEvidence
    anticipo: LiteralEvidence
    fuente_financiamiento: LiteralEvidence
    legislacion_citada: LiteralEvidence

    personas_participantes: list[ContractParticipant] = Field(default_factory=list, max_length=50)
    observaciones: list[str] = Field(default_factory=list, max_length=40)

    def fields_to_review(self) -> list[str]:
        return [
            name for name in CONTRACT_V2_FIELDS
            if getattr(self, name).needs_review
        ]

    def flat_values(self) -> list[str]:
        return [(getattr(self, name).valor or "") for name in CONTRACT_V2_FIELDS]


# La salida enviada al SDK evita definiciones JSON anidadas complejas.
# Las validaciones estrictas (tipo/duplicados/páginas) se aplican en Python.
GEMINI_RESPONSE_SCHEMA_V2: dict[str, Any] = {
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
        "personas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "nombre": {"type": "string"},
                    "cargo_o_caracter": {"type": ["string", "null"]},
                    "representacion": {"type": ["string", "null"]},
                    "pagina": {"type": ["integer", "null"]},
                    "evidencia": {"type": ["string", "null"]},
                },
                "required": [
                    "nombre", "cargo_o_caracter", "representacion", "pagina", "evidencia"
                ],
            },
        },
        "observaciones": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["campos", "personas", "observaciones"],
}


def parse_contract_v2(payload: dict[str, Any] | str) -> ContractExtractionV2:
    if isinstance(payload, str):
        try:
            data = json.loads(payload)
        except (TypeError, ValueError) as exc:
            raise ValueError("Gemini no entregó un JSON legible.") from exc
    else:
        data = payload
    if not isinstance(data, dict) or set(data) != {"campos", "personas", "observaciones"}:
        raise ValueError("La estructura de contrato v2 es incompatible.")
    fields = data["campos"]
    persons = data["personas"]
    observations = data["observaciones"]
    if not isinstance(fields, list) or len(fields) > len(CONTRACT_V2_FIELDS):
        raise ValueError("Cantidad de campos del contrato inesperada.")
    if not isinstance(persons, list) or len(persons) > 50:
        raise ValueError("Listado de personas inválido.")
    if not isinstance(observations, list) or len(observations) > 40:
        raise ValueError("Observaciones inválidas.")
    if any(not isinstance(v, str) for v in observations):
        raise ValueError("Observación no textual.")
    seen: dict[str, LiteralEvidence] = {}
    for item in fields:
        if not isinstance(item, dict) or set(item) != {
            "campo", "valor", "pagina", "evidencia"
        }:
            raise ValueError("Elemento de extracción inválido.")
        name = item["campo"]
        if not isinstance(name, str) or name not in CONTRACT_V2_FIELDS:
            raise ValueError("Campo no autorizado en respuesta de Gemini.")
        if name in seen:
            raise ValueError("Campo duplicado en la extracción.")
        seen[name] = LiteralEvidence.model_validate({
            "valor": item["valor"], "pagina": item["pagina"],
            "evidencia": item["evidencia"],
        })
    missing = [name for name in CONTRACT_V2_FIELDS if name not in seen]
    for name in missing:
        seen[name] = LiteralEvidence(valor=None)
    return ContractExtractionV2.model_validate({
        **seen,
        "personas_participantes": persons,
        "observaciones": observations + [
            f"Campo omitido por el modelo: {name}" for name in missing
        ],
    })


def classify_cited_regime(literal: str | None) -> str:
    """Sólo clasifica denominaciones legales explícitas, no procedencia de fondos.

    Una ley estatal aplicable a municipios NO se convierte automáticamente
    en legislación exclusivamente 'municipal'. El régimen efectivo y los
    umbrales deben cotejarse con documentación adicional.
    """
    if not literal:
        return "No determinado"
    s = unicodedata.normalize("NFKD", literal.casefold())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = " ".join(s.split())
    found: list[str] = []
    if "ley de obras publicas y servicios relacionados con las mismas" in s:
        found.append("Federal")
    if (
        "ley de obra publica" in s and "guanajuato" in s and
        ("estado" in s or "municipios" in s)
    ):
        found.append("Estatal")
    if re.search(
        r"reglamento.{0,110}(obra publica|construccion).{0,110}(municipio|municipal|leon)",
        s,
    ):
        found.append("Municipal")
    if not found:
        return "No determinado"
    if len(found) > 1:
        return " + ".join(found) + " (por verificar)"
    return found[0] + " (citado; por verificar)"
