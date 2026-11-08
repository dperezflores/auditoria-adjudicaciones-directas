"""Estado de análisis por archivo y carpeta, calculado exclusivamente desde Sheets.

No considera validada una extracción: solo identifica si Gemini entregó y
se guardó un resultado para la versión documental vigente.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence
import unicodedata

from services.drive_service import DriveInventory, DocumentRecord, WorkRecord
from services.document_classifier import code_from_filename
from services.sync_engine import HEADERS
from services.extraction_store import EXTRACTION_HEADERS, CONTRACT_HEADERS

@dataclass(frozen=True)
class FileStatus:
    document_id: str
    label: str
    detail: str
    kind: str
    cache_key: str = ""

@dataclass(frozen=True)
class FolderStatus:
    folder_id: str
    label: str
    complete: int
    partial: int
    pending: int
    total: int


def _rows(values: Sequence[Sequence[Any]], headers: tuple[str, ...]) -> list[dict[str, str]]:
    if not values or tuple(str(c) for c in values[0][:len(headers)]) != headers:
        raise ValueError("Encabezados de la hoja maestra incompatibles.")
    result = []
    seen = set()
    for v in values[1:]:
        row = [str(x) if x is not None else "" for x in v[:len(headers)]]
        row += [""] * (len(headers) - len(row))
        if not any(row):
            continue
        item = dict(zip(headers, row))
        key = item[headers[0]]
        if not key:
            raise ValueError("Identificador vacío en el registro.")
        if headers != CONTRACT_HEADERS and key in seen:
            raise ValueError("Identificador duplicado en el registro.")
        seen.add(key)
        result.append(item)
    return result


def load_status_tables(client: Any, sheet_id: str) -> dict[str, list[dict[str, str]]]:
    mapping = {
        "Documentos": HEADERS["Documentos"],
        "Extracciones": EXTRACTION_HEADERS,
        "DatosContrato": CONTRACT_HEADERS,
    }
    ranges = [
        f"'{name}'!A1:{chr(64 + len(headers))}"
        for name, headers in mapping.items()
    ]
    response = client.spreadsheets().values().batchGet(
        spreadsheetId=sheet_id, ranges=ranges,
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    data = response.get("valueRanges") or []
    if len(data) != len(ranges):
        raise ValueError("No se pudieron consultar todas las pestañas del registro.")
    return {
        name: _rows(data[i].get("values") or [], headers)
        for i, (name, headers) in enumerate(mapping.items())
    }


def suggest_kind(name: str) -> str:
    """Elección orientativa editable en la interfaz; no determina cumplimiento."""
    raw = unicodedata.normalize("NFKD", name).casefold()
    name_plain = "".join(c for c in raw if not unicodedata.combining(c))
    if "convenio" in name_plain:
        return "documental"
    if "contrato" in name_plain:
        return "contrato"
    # Convenciones frecuentes de expedientes municipales: CNT_DIR_CNT.pdf,
    # CONTR_DIR.pdf, etc. No confundir con PUC o dictámenes.
    import re
    stem = name_plain.rsplit(".", 1)[0]
    if re.match(r"^(?:cnt|contr)[_ -](?:dir|ad|obra|contr|cnt)(?:[_ -]|$)", stem):
        return "contrato"
    return "documental"


def file_states(
    inventory: DriveInventory,
    tables: Mapping[str, Sequence[Mapping[str, str]]],
) -> dict[str, FileStatus]:
    documents = {r["documento_id"]: r for r in tables["Documentos"]}
    analyses = {r["cache_key"]: r for r in tables["Extracciones"]}
    partial_keys = {
        (r["cache_key"], r["documento_id"])
        for r in tables["DatosContrato"]
        if any(str(r.get(k) or "").strip() for k in CONTRACT_HEADERS[3:11])
    }
    states: dict[str, FileStatus] = {}
    for work in inventory.works:
        supported = [
            *work.pdfs,
            *(d for d in work.other_files if code_from_filename(d.name, d.mime_type) == "CATALOGO"),
        ]
        for doc in supported:
            registered = documents.get(doc.id)
            kind = suggest_kind(doc.name)
            if not registered:
                state = FileStatus(doc.id, "Sin registrar", "Actualiza el inventario de Drive.", kind)
            elif (registered["obra_id"] != work.id or registered["activo"] != "SI"
                  or registered["md5_checksum"] != doc.md5_checksum):
                state = FileStatus(doc.id, "Desactualizado", "El registro no coincide con Drive.", kind)
            elif registered["estado_procesamiento"] == "Modificado desde el último análisis":
                state = FileStatus(doc.id, "Desactualizado", "Cambió el contenido del documento.", kind)
            else:
                key = registered["resultado_id"]
                current = analyses.get(key)
                if key and current and current["documento_id"] == doc.id and current["obra_id"] == work.id:
                    if current["estado"] == "COMPLETADO" and current["resultado_json"]:
                        state = FileStatus(doc.id, "Analizado", "Resultado guardado; pendiente de revisión técnica.", kind, key)
                    elif (key, doc.id) in partial_keys:
                        state = FileStatus(doc.id, "Parcial", "Solo existen algunos datos; no repetir automáticamente.", kind, key)
                    else:
                        state = FileStatus(doc.id, "Pendiente", "No existe un resultado completo.", kind, key)
                else:
                    pending_attempts = [
                        a for a in tables["Extracciones"]
                        if a["documento_id"] == doc.id and a["obra_id"] == work.id
                        and a["estado"] in ("EN_PROCESO", "REQUIERE_REVISION")
                    ]
                    if pending_attempts:
                        state = FileStatus(doc.id, "Revisar error", "Existe una solicitud no confirmada.", kind)
                    else:
                        state = FileStatus(doc.id, "Pendiente", "Sin análisis registrado.", kind)
            states[doc.id] = state
    return states


def folder_states(
    inventory: DriveInventory, statuses: Mapping[str, FileStatus]
) -> dict[str, FolderStatus]:
    result = {}
    for work in inventory.works:
        supported = [
            *work.pdfs,
            *(d for d in work.other_files if code_from_filename(d.name, d.mime_type) == "CATALOGO"),
        ]
        total = len(supported)
        done = sum(statuses[d.id].label == "Analizado" for d in supported)
        partial = sum(statuses[d.id].label == "Parcial" for d in supported)
        pending = total - done - partial
        if total == 0:
            label = "Sin PDF"
        elif done == total:
            label = "Analizada"
        elif done or partial:
            label = "Parcial"
        elif any(statuses[d.id].label == "Revisar error" for d in supported):
            label = "Revisar error"
        else:
            label = "Pendiente"
        result[work.id] = FolderStatus(work.id, label, done, partial, pending, total)
    return result
