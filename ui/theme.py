"""Tokens visuales y mapeos de presentación de AuditorIA — Fase 1.

Módulo puro: sin Streamlit, sin consultas a Drive/Sheets y sin reglas nuevas de análisis.
"""
from __future__ import annotations

from dataclasses import dataclass

PALETTE = {
    "fondo": "#F4F5F7",
    "superficie": "#FFFFFF",
    "borde": "#E1E4E8",
    "borde_fuerte": "#D3D8DE",
    "texto": "#18212B",
    "texto_2": "#3A4552",
    "texto_3": "#5B6573",
    "acento": "#1F4FD1",
    "acento_suave": "#E8EEFC",
    "seleccion": "#F3F6FE",
    "oscuro": "#18212B",
}


@dataclass(frozen=True)
class StateStyle:
    label: str
    slug: str
    color: str
    background: str
    icon: str


STATE_STYLES: dict[str, StateStyle] = {
    "Analizado": StateStyle("Analizado", "analizado", "#17603C", "#E3F2EA", "check"),
    "Pendiente": StateStyle("Por analizar", "pendiente", "#8A4B06", "#FDF0DC", "clock"),
    "Parcial": StateStyle("Parcial", "parcial", "#7A5200", "#FFF4D6", "partial"),
    "Desactualizado": StateStyle("Modificado", "desactualizado", "#2142A8", "#E6EDFD", "refresh"),
    "Revisar error": StateStyle("Error", "error", "#A4281B", "#FCE8E6", "warning"),
    "Sin registrar": StateStyle("Sin registrar", "sin-registrar", "#5B6573", "#F1F3F5", "question"),
    "POR_IDENTIFICAR": StateStyle("Sin identificar", "sin-identificar", "#6A3FA0", "#F1EAFB", "question"),
    "Falta": StateStyle("Falta", "falta", "#5B6573", "#F1F3F5", "minus"),
    "No compatible": StateStyle("No compatible", "no-compatible", "#5B6573", "#F1F3F5", "cross"),
    "Nueva": StateStyle("Nueva", "nueva", "#2142A8", "#E6EDFD", "sparkles"),
}
DEFAULT_STATE = StateStyle("", "other", "#5B6573", "#F1F3F5", "question")

NAVIGATION = ("Expedientes", "Resultados", "Pruebas de adjudicación")
EXPECTED_DOCUMENTS = (
    ("CONTRATO", "Contrato"),
    ("PUC", "PUC"),
    ("CATALOGO", "Catálogo"),
    ("DICTAMEN_AD", "Dictamen AD"),
    ("NOTIFICACION_AD", "Notificación AD"),
)
OPTIONAL_DOCUMENT = ("ORDEN_AD", "Orden AD")

# Presentación solamente; las etiquetas literales siguen definidas en los schemas.
FIELD_GROUPS_CONTRATO = {
    "identificacion": "Identificación",
    "partes": "Partes",
    "objeto": "Objeto",
    "montos": "Montos",
    "plazos": "Plazo y firma",
}


def state_style(state: str) -> StateStyle:
    """Nunca ocultar estados nuevos: estilo neutro y texto original."""
    return STATE_STYLES.get(state, StateStyle(state, DEFAULT_STATE.slug,
                                              DEFAULT_STATE.color,
                                              DEFAULT_STATE.background,
                                              DEFAULT_STATE.icon))
