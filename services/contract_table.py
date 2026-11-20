"""Presentación normalizada del listado. No modifica la extracción original."""
from __future__ import annotations

from typing import Any, Sequence
from services.contract_portfolio import ContractRecord
from services.contract_v2 import FIELD_LABELS_V2
from services.contract_normalization import normalized_values


def participant_cell(people: Sequence[dict[str, Any]]) -> str:
    entries=[]
    for person in people:
        name=person.get("nombre")
        if not isinstance(name,str) or not name:
            continue
        parts=[name]
        if person.get("cargo_o_caracter"):
            parts.append(f"Cargo: {person['cargo_o_caracter']}")
        if person.get("representacion"):
            parts.append(f"Representa a: {person['representacion']}")
        entries.append(" | ".join(parts))
    return "; ".join(entries) if entries else "—"


def contract_table_rows(records: Sequence[ContractRecord]) -> list[dict[str,str]]:
    result=[]
    for record in records:
        norm, notes = normalized_values(record)
        review=record.verification or {}
        row={"Carpeta":record.nombre_carpeta}
        for key,label in FIELD_LABELS_V2:
            # El dato técnico ya no se extrae; las extracciones anteriores
            # permanecen accesibles por su JSON / Evidencias originales.
            if key == "representante_tecnico":
                continue
            row[label]=norm.get(key) or "—"
        row["IVA del importe"] = norm["iva"]
        row["Personas que participan en el contrato"]=participant_cell(
            record.participants
        )
        row["Ámbito normativo preliminar"] = (
            norm["regimen"] or record.normative_scope
        )
        row["Estado de verificación"] = (
            review.get("estado_revision") or "Sin verificación guardada"
        )
        explanations=list(record.observations)+list(notes)
        if review.get("observaciones"):
            explanations.append(
                "Verificación del auditor: "+review["observaciones"]
            )
        row["Observaciones de extracción"] = " | ".join(explanations) if explanations else "—"
        result.append(row)
    return result
