"""Estructura trazable para la extracción de contratos de obra pública.

La IA solo entrega propuestas de extracción, no hechos auditados ni dictámenes.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = "contrato-v1"


class DatoConEvidencia(BaseModel):
    """Valor literal observado y ubicación verificable dentro del PDF."""

    model_config = ConfigDict(extra="forbid")

    valor: str | None = Field(description="Texto literal localizado; null si no consta o es ilegible.")
    pagina: int | None = Field(default=None, ge=1, description="Página física del PDF, comenzando en 1.")
    evidencia: str | None = Field(default=None, description="Fragmento breve del documento que respalda el valor.")

    @field_validator("valor", "evidencia", mode="before")
    @classmethod
    def normalizar_vacio(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value

    @property
    def requiere_revision(self) -> bool:
        return self.valor is not None and (self.pagina is None or self.evidencia is None)


class ExtraccionContrato(BaseModel):
    """Campos para el piloto; no se normalizan importes ni fechas sin cotejo."""

    model_config = ConfigDict(extra="forbid")

    numero_contrato: DatoConEvidencia
    nombre_obra: DatoConEvidencia
    contratista: DatoConEvidencia
    fecha_firma: DatoConEvidencia
    fecha_inicio: DatoConEvidencia
    fecha_termino: DatoConEvidencia
    monto_con_iva: DatoConEvidencia
    porcentaje_anticipo: DatoConEvidencia
    observaciones: list[str] = Field(default_factory=list)

    def campos_que_requieren_revision(self) -> list[str]:
        """No presentar un valor como evidencia confirmada sin página y cita."""
        return [
            name for name in type(self).model_fields
            if isinstance(getattr(self, name), DatoConEvidencia)
            and getattr(self, name).requiere_revision
        ]
