"""Datos y selección estable para el gráfico de déficit de capital CC-01.

Este módulo no utiliza Streamlit, Plotly ni servicios externos; construye
una barra por contrato, incluso si un contratista tiene varias obras.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import json
from typing import Any, Iterable, Sequence

from services.capital_contable import CapitalResult
from services.contract_normalization import normalized_values
from services.contract_portfolio import ContractRecord


@dataclass(frozen=True)
class CapitalDeficit:
    record_key: str
    portfolio_index: int
    carpeta: str
    contrato: str
    contratista: str
    faltante: Decimal
    minimo: Decimal
    capital: Decimal
    cobertura: Decimal | None
    resultado: str
    vigencia: str


def contract_selection_key(record: ContractRecord) -> str:
    """Identidad exacta: no agrupar por nombre/RFC del contratista."""
    return json.dumps(
        [record.obra_id, record.documento_id, record.cache_key],
        ensure_ascii=False, separators=(",", ":"),
    )


def undercapitalized_contracts(
    results: Sequence[tuple[ContractRecord, CapitalResult]],
) -> tuple[CapitalDeficit, ...]:
    """Candidatos con déficit aritmético; su vigencia puede exigir cotejo.

    Solo se incluyen contratos cuyo CAPITAL registrado/comparable
    efectivamente resulta menor al 30 %. No se incluyen capitales sin
    importe comparable ni se cuentan como incumplimientos automáticos.
    """
    candidates: list[CapitalDeficit] = []
    for i, (record, result) in enumerate(results):
        if (
            result.comparison != "Capital inferior al 30%"
            or result.difference is None
            or result.difference >= 0
            or result.requirement is None
            or result.capital is None
        ):
            continue
        values, _ = normalized_values(record)
        candidates.append(CapitalDeficit(
            record_key=contract_selection_key(record),
            portfolio_index=i,
            carpeta=record.nombre_carpeta,
            contrato=values.get("numero_contrato") or record.documento,
            contratista=values.get("contratista") or "Sin identificar",
            faltante=-result.difference,
            minimo=result.requirement,
            capital=result.capital,
            cobertura=result.coverage,
            resultado=result.state,
            vigencia=result.vigencia_puc or "Pendiente",
        ))
    return tuple(sorted(
        candidates,
        key=lambda item: (-item.faltante, item.record_key),
    ))


def selected_deficit_record(
    event: Any, available_keys: Iterable[str],
) -> str | None:
    """Recuperar la clave única de la barra seleccionada en Plotly.

    Los puntos Plotly incluyen `customdata`. No se depende del nombre
    del contratista, ni del índice tras ordenar o filtrar el gráfico.
    """
    if not isinstance(event, dict):
        try:
            event = dict(event)
        except (TypeError, ValueError):
            return None
    selection = event.get("selection") or {}
    points = selection.get("points") or []
    valid = set(available_keys)
    for point in reversed(points):
        if not isinstance(point, dict):
            continue
        data = point.get("customdata") or []
        if isinstance(data, (list, tuple)) and data:
            key = data[0]
            if isinstance(key, str) and key in valid:
                return key
    return None
