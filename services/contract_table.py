"""Filas del listado contractual: todos los campos literales disponibles.

Contrato v2: 16 valores íntegros y personas participantes en una celda.
Contratos de esquemas anteriores: se usan únicamente los datos conservados
en esa versión, sin inferir los 16 campos nuevos.
"""
from __future__ import annotations

from typing import Any, Sequence

from services.contract_portfolio import ContractRecord
from services.contract_v2 import FIELD_LABELS_V2


_LEGACY_MAP = {
    "numero_contrato": "numero_contrato",
    "obra_servicio": "nombre_obra",
    "contratista": "contratista",
    "monto_contrato": "monto_con_iva",
    "fecha_inicio_contractual": "fecha_inicio",
    "fecha_termino_contractual": "fecha_termino",
    "fecha_firma_contrato": "fecha_firma",
    "anticipo": "porcentaje_anticipo",
}


def participant_cell(people: Sequence[dict[str, Any]]) -> str:
    """Resumir todos los participantes en UNA celda, sin alterar sus textos."""
    entries = []
    for person in people:
        name = person.get("nombre")
        if not isinstance(name, str) or not name:
            continue
        parts = [name]
        role = person.get("cargo_o_caracter")
        if isinstance(role, str) and role:
            parts.append(f"Cargo: {role}")
        represented = person.get("representacion")
        if isinstance(represented, str) and represented:
            parts.append(f"Representa a: {represented}")
        entries.append(" | ".join(parts))
    return "; ".join(entries) if entries else "—"


def contract_table_rows(records: Sequence[ContractRecord]) -> list[dict[str, str]]:
    rows = []
    for record in records:
        source = record.full_values
        # Mostrar la información textual registrada; nunca reescribir cifras,
        # fechas, signos, acentos, mayúsculas o puntuación del origen.
        values = (
            {key: source.get(key) or "" for key, _ in FIELD_LABELS_V2}
            if source is not None
            else {
                key: record.values.get(_LEGACY_MAP.get(key, ""), "")
                for key, _ in FIELD_LABELS_V2
            }
        )
        row = {
            label: values[key] if values[key] else "—"
            for key, label in FIELD_LABELS_V2
        }
        row["Personas que participan en el contrato"] = participant_cell(
            record.participants
        )
        row["Ámbito normativo preliminar"] = (
            record.normative_scope if source is not None else "No determinado (versión anterior)"
        )
        row["Observaciones de extracción"] = (
            " | ".join(record.observations) if record.observations else "—"
        )
        row["Campos extraídos"] = record.coverage
        row["Estado de extracción"] = record.status_label
        rows.append(row)
    return rows
