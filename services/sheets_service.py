"""Conector Google Sheets para el inventario persistente del piloto.

Las escrituras se centralizan desde un único proceso Streamlit; Google Sheets
NO ofrece transacciones ni bloqueos multiinstancia. No usar como backend de
escrituras concurrentes entre varios servidores.
"""
from __future__ import annotations

from typing import Any, Mapping

from services.drive_service import DriveInventory
from services.sync_engine import HEADERS, SyncPlan, build_plan

SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
SHEET_ID_MIN_LENGTH = 20


class InventoryProtectionError(RuntimeError):
    """La nueva clasificación no incluye todos los expedientes ya activos."""


def assert_existing_works_preserved(
    inventory: DriveInventory, snapshot: Mapping[str, list[list[object]]],
) -> None:
    """Bloquea escrituras si mover carpetas dejó obras/documentos fuera del árbol.

    No permite que una ruta o subcarpeta de grupo mal clasificada marque
    registros anteriores como inactivos en la hoja maestra.
    """
    present_works = {work.id for work in inventory.works}
    present_docs = {
        doc.id for work in inventory.works
        for doc in (*work.pdfs, *(
            item for item in work.other_files if item.mime_type.endswith(
                "spreadsheetml.sheet"
            )
        ))
    }
    missing_works = [
        str(row[0]) for row in snapshot.get("Obras", [])[1:]
        if row and len(row) >= 8 and str(row[7]) == "SI"
        and str(row[0]) not in present_works
    ]
    missing_docs = [
        str(row[0]) for row in snapshot.get("Documentos", [])[1:]
        if row and len(row) >= 12 and str(row[11]) == "SI"
        and str(row[0]) not in present_docs
    ]
    if missing_works or missing_docs:
        raise InventoryProtectionError(
            "Sincronización bloqueada para proteger resultados existentes: "
            f"{len(missing_works)} obra(s) y {len(missing_docs)} documento(s) "
            "previamente activos no aparecen bajo las carpetas reconocidas. "
            "Comprueba que moviste las carpetas originales (no copias), "
            "que estén dentro de un directorio GRUPO_ o registrado como tal, "
            "y que Drive permita leer su contenido. "
            "No se realizó ninguna escritura en Google Sheets. "
            "IDs de obra afectados: " + ", ".join(missing_works[:5])
        )


def storage_configured(settings: Mapping[str, Any]) -> bool:
    try:
        storage = settings.get("storage", {})
        account = settings.get("gcp_service_account", {})
        return (
            isinstance(storage.get("spreadsheet_id"), str)
            and len(storage["spreadsheet_id"].strip()) >= SHEET_ID_MIN_LENGTH
            and bool(account.get("client_email") and account.get("private_key"))
        )
    except (AttributeError, TypeError, KeyError):
        return False


def create_sheets_client(account_info: Mapping[str, Any]) -> Any:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    credentials = service_account.Credentials.from_service_account_info(
        dict(account_info), scopes=[SHEETS_SCOPE]
    )
    return build("sheets", "v4", credentials=credentials, cache_discovery=False)


def _last_column(count: int) -> str:
    """A...Z, AA...; los esquemas actuales llegan hasta P."""
    letters = ""
    while count:
        count, digit = divmod(count - 1, 26)
        letters = chr(65 + digit) + letters
    return letters


def read_snapshot(sheets_client: Any, spreadsheet_id: str) -> dict[str, list[list[object]]]:
    ranges = [
        f"'{tab}'!A1:{_last_column(len(columns))}"
        for tab, columns in HEADERS.items()
    ]
    result = sheets_client.spreadsheets().values().batchGet(
        spreadsheetId=spreadsheet_id, ranges=ranges,
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    value_ranges = result.get("valueRanges") or []
    if len(value_ranges) != len(ranges):
        raise RuntimeError("No se pudieron leer todas las pestañas requeridas.")
    return {
        name: value_ranges[i].get("values", [])
        for i, name in enumerate(HEADERS)
    }


def sync_to_sheets(
    sheets_client: Any,
    spreadsheet_id: str,
    inventory: DriveInventory,
    *,
    protect_existing: bool = False,
) -> SyncPlan:
    """Una lectura, una planificación, un batch de escritura por actualización.

    La llamada debe ejecutarse detrás de un cerrojo del mismo proceso para
    reducir duplicados entre sesiones; no sirve como lock distribuido.
    """
    snapshot = read_snapshot(sheets_client, spreadsheet_id)
    if protect_existing:
        assert_existing_works_preserved(inventory, snapshot)
    plan = build_plan(inventory, snapshot)

    data = []
    for item in plan.updates:
        ending = _last_column(len(HEADERS[item.sheet]))
        data.append({
            "range": f"'{item.sheet}'!A{item.row_number}:{ending}{item.row_number}",
            "values": [list(item.values)],
        })
    if not data:
        raise RuntimeError("No se generó el registro obligatorio de sincronización.")

    response = sheets_client.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"valueInputOption": "RAW", "data": data},
    ).execute()
    if int(response.get("totalUpdatedRows", 0)) < len(data):
        raise RuntimeError("La respuesta de Sheets no confirmó todas las filas.")
    return plan
