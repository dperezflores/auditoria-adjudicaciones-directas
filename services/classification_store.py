"""Guardar solo clasificaciones CONFIRMADAS por lectura del archivo.

No genera extracciones ni llama a Gemini. Validar IDs, MIME y huella
antes de actualizar la columna D de Documentos en Google Sheets.
"""
from __future__ import annotations

from typing import Any

from services.document_classifier import Classification, DOCUMENT_CODES
from services.drive_service import DocumentRecord
from services.sync_engine import HEADERS


class ClassificationStoreError(ValueError):
    pass


def save_confirmed_type(
    sheets: Any, spreadsheet_id: str, doc: DocumentRecord, obra_id: str,
    classification: Classification,
) -> None:
    if not classification.confirmed or classification.code not in DOCUMENT_CODES:
        raise ClassificationStoreError(
            "Solo se pueden guardar códigos confirmados por contenido."
        )
    service = sheets.spreadsheets().values()
    response = service.get(
        spreadsheetId=spreadsheet_id,
        range="'Documentos'!A1:P",
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    rows = response.get("values") or []
    headers = HEADERS["Documentos"]
    if not rows or tuple(str(x) for x in rows[0][:len(headers)]) != headers:
        raise ClassificationStoreError("Los encabezados de Documentos no coinciden.")
    matches = []
    for index, cells in enumerate(rows[1:], start=2):
        cells = list(cells[:len(headers)]) + [""] * max(0, len(headers)-len(cells))
        if str(cells[0]) == doc.id:
            matches.append((index, cells))
    if len(matches) != 1:
        raise ClassificationStoreError("El archivo no está registrado una sola vez.")
    row, cells = matches[0]
    if (
        str(cells[1]) != obra_id or str(cells[4]) != doc.mime_type
        or str(cells[5]) != doc.md5_checksum or str(cells[11]) != "SI"
    ):
        raise ClassificationStoreError(
            "La versión del archivo o su obra cambiaron. Actualiza Drive."
        )
    service.update(
        spreadsheetId=spreadsheet_id,
        range=f"'Documentos'!D{row}",
        valueInputOption="RAW",
        body={"values": [[classification.code]]},
    ).execute()
