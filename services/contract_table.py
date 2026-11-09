"""Tabla de Resultados normalizada; los literales originales siguen en la ficha.

No modifica los archivos, el JSON de extracción ni la base de datos.
"""
from __future__ import annotations

from typing import Any, Sequence

from services.contract_portfolio import ContractRecord
from services.contract_v2 import FIELD_LABELS_V2
from services.contract_display import (
    format_contract_amount, normalize_award_method, normalize_contract_type, short_date,
)


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
        # Los originales siguen disponibles en la ficha y en Evidencias del PDF.
        # Los derivados de esta vista no alteran DatosContratoV2.
        values = (
            {key: source.get(key) or "" for key, _ in FIELD_LABELS_V2}
            if source is not None
            else {
                key: record.values.get(_LEGACY_MAP.get(key, ""), "")
                for key, _ in FIELD_LABELS_V2
            }
        )
        row: dict[str, str] = {}
        for key, label in FIELD_LABELS_V2:
            literal = values[key]
            if key == "monto_contrato":
                row[label] = format_contract_amount(literal, record.currency)
            elif key == "tipo_contrato":
                row[label] = normalize_contract_type(literal)
            elif key == "modalidad_adjudicacion":
                row[label] = normalize_award_method(literal)
            elif key in ("fecha_firma_contrato", "fecha_inicio_contractual",
                         "fecha_termino_contractual"):
                row[label] = short_date(literal)
            else:
                row[label] = literal if literal else "—"
        row["Personas que participan en el contrato"] = participant_cell(
            record.participants
        )
        row["Ámbito normativo preliminar"] = (
            record.normative_scope if source is not None else "No determinado (versión anterior)"
        )
        row["Observaciones de extracción"] = (
            " | ".join(record.observations) if record.observations else "—"
        )
        rows.append(row)
    return rows
