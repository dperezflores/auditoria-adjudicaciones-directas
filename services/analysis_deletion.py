"""Borrado selectivo de resultados de IA con registro permanente de auditoría.

- NO toca Google Drive, nombres ni huellas de archivos.
- Elimina filas de cache y tablas derivadas del documento exacto.
- Conserva Historial y deja Documento en Pendiente para reanalizar.
- El llamador debe sostener get_writer_lock() y autenticación OIDC.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from services.contract_v2 import CONTRACT_V2_HEADERS
from services.dictamen_schema import DICTAMEN_HEADERS
from services.extraction_store import (
    CONTRACT_HEADERS, DOCUMENT_HEADERS, EXTRACTION_HEADERS, ExtractionStateError,
)
from services.puc_schema import PUC_HEADERS
from services.review_service import REVIEW_HEADERS
from services.sync_engine import HEADERS
from services.drive_service import DocumentRecord

_TABLES = {
    "Documentos": DOCUMENT_HEADERS,
    "Extracciones": EXTRACTION_HEADERS,
    "DatosContrato": CONTRACT_HEADERS,
    "DatosContratoV2": CONTRACT_V2_HEADERS,
    "DatosPUC": PUC_HEADERS,
    "DatosDictamenAD": DICTAMEN_HEADERS,
    "RevisionesContrato": REVIEW_HEADERS,
    "Historial": HEADERS["Historial"],
}
_SOURCE = {
    "Extracciones": (2, 3),
    "DatosContrato": (2, 1),
    "DatosContratoV2": (2, 1),
    "DatosPUC": (2, 1),
    "DatosDictamenAD": (2, 1),
    "RevisionesContrato": (3, 2),
}


@dataclass(frozen=True)
class DeleteOutcome:
    document_id: str
    attempts_deleted: int
    detail_rows_deleted: int
    review_rows_deleted: int
    event_id: str


def _column(n: int) -> str:
    if n <= 0:
        raise ValueError("Número de columnas inválido.")
    out = ""
    while n:
        n, remainder = divmod(n - 1, 26)
        out = chr(65 + remainder) + out
    return out


def _snapshot(client: Any, spreadsheet_id: str):
    ranges = [f"'{name}'!A1:{_column(len(columns))}"
              for name, columns in _TABLES.items()]
    response = client.spreadsheets().values().batchGet(
        spreadsheetId=spreadsheet_id, ranges=ranges,
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    sources = response.get("valueRanges") or []
    if len(sources) != len(ranges):
        raise ExtractionStateError("No se pudieron leer todas las pestañas.")
    tables: dict[str, list[list[str]]] = {}
    for (name, expected), entry in zip(_TABLES.items(), sources):
        data = entry.get("values") or []
        if not data or tuple(str(x) for x in data[0]) != expected:
            raise ExtractionStateError(
                f"Los encabezados de {name} no coinciden; no se eliminó nada."
            )
        records: list[list[str]] = []
        for r in data[1:]:
            padded = [str(x) if x is not None else "" for x in r[:len(expected)]]
            padded.extend([""] * (len(expected) - len(padded)))
            records.append(padded)
        tables[name] = records
    return tables


def delete_analysis(
    client: Any, spreadsheet_id: str,
    doc: DocumentRecord, obra_id: str, *,
    expected_result_id: str, actor_email: str,
) -> DeleteOutcome:
    """Eliminar todos los análisis asociados a un PDF, nunca el PDF físico.

    Un único spreadsheets.batchUpdate realiza las eliminaciones y registra
    el evento en Historial. Si el archivo cambió, falla antes de escribir.
    """
    if not isinstance(actor_email, str) or "@" not in actor_email.strip():
        raise ExtractionStateError("Se requiere un usuario Google autenticado.")
    tables = _snapshot(client, spreadsheet_id)
    found = [(i + 2, row) for i, row in enumerate(tables["Documentos"])
             if row[0] == doc.id]
    if len(found) != 1:
        raise ExtractionStateError("El documento no está registrado de forma única.")
    doc_row_number, registered = found[0]
    if (registered[1] != obra_id or registered[2] != doc.name
            or registered[4] != doc.mime_type or registered[5] != doc.md5_checksum
            or not doc.md5_checksum or registered[11] != "SI"):
        raise ExtractionStateError(
            "El archivo cambió o no pertenece a esta obra. Actualiza Google Drive."
        )
    if (registered[13] or "") != (expected_result_id or ""):
        raise ExtractionStateError(
            "La ficha cambió desde que se mostró. Recarga los estados de análisis."
        )

    to_remove: dict[str, list[tuple[int, list[str]]]] = {}
    for tab, (id_index, obra_index) in _SOURCE.items():
        selected = []
        for i, item in enumerate(tables[tab], start=2):
            if item[id_index] == doc.id:
                # No destruir resultados asociados por error a otra obra.
                if item[obra_index] != obra_id:
                    raise ExtractionStateError(
                        f"Hay registros de {tab} con la misma ID en otra obra."
                    )
                selected.append((i, item))
        to_remove[tab] = selected

    attempts = to_remove["Extracciones"]
    if any(row[1] == "EN_PROCESO" for _, row in attempts):
        raise ExtractionStateError(
            "Existe una extracción en proceso. No puede eliminarse hasta que concluya."
        )
    keys = {r[0] for _, r in attempts}
    if registered[13] and registered[13] not in keys:
        raise ExtractionStateError(
            "El resultado actual está vinculado a una clave no localizada."
        )
    # Evitar borrar accidentalmente una clave compartida entre documentos.
    for tab in ("DatosContrato", "DatosContratoV2", "DatosPUC", "DatosDictamenAD"):
        for row in tables[tab]:
            if row[0] in keys and (row[2], row[1]) != (doc.id, obra_id):
                raise ExtractionStateError("La clave de caché se usa en otro documento.")
    for row in tables["RevisionesContrato"]:
        if row[4] in keys and (row[3], row[2]) != (doc.id, obra_id):
            raise ExtractionStateError("Hay una revisión vinculada a otro documento.")

    total = sum(len(part) for part in to_remove.values())
    if not total and not registered[13] and registered[8] == "Pendiente":
        raise ExtractionStateError("Este documento no tiene análisis que eliminar.")

    sheets = client.spreadsheets()
    meta = sheets.get(
        spreadsheetId=spreadsheet_id,
        fields="sheets(properties(sheetId,title,gridProperties(rowCount,columnCount)))",
    ).execute()
    sheet_ids: dict[str, int] = {}
    for item in meta.get("sheets") or []:
        prop = item.get("properties") or {}
        if prop.get("title") in _TABLES:
            sheet_ids[prop["title"]] = int(prop["sheetId"])
            if int((prop.get("gridProperties") or {}).get("columnCount", 0)) < len(
                _TABLES[prop["title"]]
            ):
                raise ExtractionStateError("La pestaña tiene menos columnas de las esperadas.")
    if set(sheet_ids) != set(_TABLES):
        raise ExtractionStateError("La estructura de Sheets cambió; no se eliminó nada.")

    values = lambda items: [{"userEnteredValue": {"stringValue": str(x)}} for x in items]
    event_id = uuid4().hex
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    removed_keys = sorted(keys)
    audit = [
        event_id, f"borrado_{event_id[:12]}", now, "Documento",
        doc.id, obra_id, "Análisis eliminado",
        (registered[13] or (removed_keys[0] if removed_keys else "")),
        "Pendiente",
        (f"Eliminación solicitada por {actor_email.strip().casefold()}. "
         f"{len(attempts)} intento(s) y {total-len(attempts)} fila(s) auxiliares. "
         "Archivo conservado en Drive."),
    ]
    requests: list[dict[str, Any]] = []
    for tab, records in to_remove.items():
        for row_num, _ in sorted(records, reverse=True):
            requests.append({
                "deleteDimension": {
                    "range": {
                        "sheetId": sheet_ids[tab], "dimension": "ROWS",
                        "startIndex": row_num - 1, "endIndex": row_num,
                    }
                }
            })
    requests.extend([
        {"updateCells": {
            "range": {
                "sheetId": sheet_ids["Documentos"],
                "startRowIndex": doc_row_number - 1,
                "endRowIndex": doc_row_number,
                "startColumnIndex": 8, "endColumnIndex": 9,
            },
            "rows": [{"values": values(["Pendiente"])}],
            "fields": "userEnteredValue",
        }},
        {"repeatCell": {
            "range": {
                "sheetId": sheet_ids["Documentos"],
                "startRowIndex": doc_row_number - 1,
                "endRowIndex": doc_row_number,
                "startColumnIndex": 12, "endColumnIndex": 15,
            },
            "cell": {}, "fields": "userEnteredValue",
        }},
        {"appendCells": {
            "sheetId": sheet_ids["Historial"],
            "rows": [{"values": values(audit)}],
            "fields": "userEnteredValue",
        }},
    ])
    result = sheets.batchUpdate(
        spreadsheetId=spreadsheet_id, body={"requests": requests}
    ).execute()
    if len(result.get("replies") or []) != len(requests):
        raise ExtractionStateError(
            "Sheets no confirmó todas las operaciones; revisa los registros antes de repetir."
        )
    return DeleteOutcome(
        document_id=doc.id,
        attempts_deleted=len(attempts),
        detail_rows_deleted=(
            sum(len(rows) for name, rows in to_remove.items()
                if name not in ("Extracciones", "RevisionesContrato"))
        ),
        review_rows_deleted=len(to_remove["RevisionesContrato"]),
        event_id=event_id,
    )
