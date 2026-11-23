"""Filtro global de grupos de obra sin alterar el registro de Sheets.

Las asociaciones se toman de los IDs de Drive. Un cambio de ruta de
carpeta no cambia `obra_id`, `documento_id` ni los resultados de extracción.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Iterable, TypeVar

from services.drive_service import DriveGroupCatalog, DriveInventory


ALL_GROUPS = "__TODAS_LAS_OBRAS__"
UNGROUPED = "__SIN_GRUPO__"
_GROUP_UNKNOWN = object()
T = TypeVar("T")


def catalog_from_inventory(inventory: DriveInventory) -> DriveGroupCatalog:
    return DriveGroupCatalog(
        root_id=inventory.root_id,
        groups=inventory.groups,
        work_to_group={work.id: work.group_id for work in inventory.works},
    )


def group_options(catalog: DriveGroupCatalog) -> tuple[str, ...]:
    return (
        ALL_GROUPS,
        UNGROUPED,
        *(group.id for group in catalog.groups),
    )


def group_label(option: str, catalog: DriveGroupCatalog) -> str:
    if option == ALL_GROUPS:
        return "Todas las obras"
    if option == UNGROUPED:
        return "Sin grupo (carpetas directas)"
    return next(
        (group.name for group in catalog.groups if group.id == option),
        "Grupo no identificado",
    )


def included_work_id(
    work_id: str,
    catalog: DriveGroupCatalog | None,
    selected: str,
) -> bool:
    if selected == ALL_GROUPS:
        return True
    if catalog is None:
        return False
    actual = catalog.work_to_group.get(work_id, _GROUP_UNKNOWN)
    if actual is _GROUP_UNKNOWN:
        return False
    return actual == ("" if selected == UNGROUPED else selected)


def selected_records(
    records: Iterable[T],
    catalog: DriveGroupCatalog | None,
    selected: str,
) -> tuple[T, ...]:
    """Usar solo IDs; nunca inferir membresía por nombres de carpetas."""
    return tuple(
        item for item in records
        if included_work_id(item.obra_id, catalog, selected)
    )


def selected_inventory(
    inventory: DriveInventory,
    catalog: DriveGroupCatalog | None,
    selected: str,
) -> DriveInventory:
    """Solo cambia la vista en memoria, no el inventario de sincronización."""
    if selected == ALL_GROUPS:
        return inventory
    return replace(inventory, works=tuple(
        work for work in inventory.works
        if included_work_id(work.id, catalog, selected)
    ))
