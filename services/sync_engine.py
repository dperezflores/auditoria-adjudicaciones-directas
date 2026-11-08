"""Detección pura e idempotente de cambios entre Drive y la base maestra.

Sin API, sin IA y sin E/S. Criterio: el ID de Drive identifica el documento;
la huella MD5 (o tamaño/fecha si falta) identifica cambio de contenido.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Sequence
from uuid import uuid4

from services.drive_service import DriveInventory, PDF_MIME, XLSX_MIME
from services.document_classifier import code_from_filename

HEADERS = {
    "Obras": (
        "obra_id", "nombre_carpeta", "estado_expediente", "total_pdf",
        "pdf_pendientes", "pdf_modificados", "ultima_vista_utc", "activo", "revision",
    ),
    "Documentos": (
        "documento_id", "obra_id", "nombre_archivo", "tipo_documental",
        "mime_type", "md5_checksum", "fecha_modificacion_drive", "tamano_bytes",
        "estado_procesamiento", "primera_deteccion_utc", "ultima_deteccion_utc",
        "activo", "version_extractor", "resultado_id", "ultimo_error", "revision",
    ),
    "Sincronizaciones": (
        "sync_id", "inicio_utc", "fin_utc", "obras_detectadas", "pdf_detectados",
        "obras_nuevas", "pdf_nuevos", "pdf_modificados", "pdf_retirados",
        "resultado", "observaciones",
    ),
    "Historial": (
        "evento_id", "sync_id", "fecha_utc", "entidad", "entidad_id", "obra_id",
        "tipo_cambio", "anterior", "nuevo", "detalle",
    ),
}

PENDING = "Pendiente"
MODIFIED = "Modificado desde el último análisis"
PROCESSED = ("Analizado", "Requiere validación", "Error de procesamiento")


class SchemaMismatch(ValueError):
    """La hoja no coincide con el contrato de datos del piloto."""


@dataclass(frozen=True)
class CellUpdate:
    sheet: str
    row_number: int
    values: tuple[str, ...]


@dataclass(frozen=True)
class SyncPlan:
    updates: tuple[CellUpdate, ...]
    sync_id: str
    new_works: int
    new_pdfs: int
    modified_pdfs: int
    removed_pdfs: int
    events: int
    total_works: int
    total_pdfs: int


def _normalize_table(tab: str, rows: Sequence[Sequence[object]]) -> tuple[list[dict[str, str]], int]:
    expected = HEADERS[tab]
    if not rows or tuple(str(x) for x in rows[0][:len(expected)]) != expected:
        raise SchemaMismatch(f"Los encabezados de la pestaña {tab} no corresponden a la versión del piloto.")
    result = []
    key = expected[0]
    seen: set[str] = set()
    for row_number, raw in enumerate(rows[1:], start=2):
        values = [str(v) if v is not None else "" for v in raw[:len(expected)]]
        values += [""] * (len(expected) - len(values))
        if not any(values):
            continue
        item = dict(zip(expected, values))
        if not item[key] or item[key] in seen:
            raise SchemaMismatch(f"ID vacío o duplicado en {tab}; requiere intervención manual.")
        seen.add(item[key])
        item["__row_number"] = str(row_number)
        result.append(item)
    return result, max(1, len(rows))


def _fingerprint_changed(old: dict[str, str], checksum: str, modified: str, size: str) -> bool:
    before_checksum = old["md5_checksum"]
    if before_checksum and checksum:
        return before_checksum != checksum
    # Si no hay checksum, usar metadatos como señal de posible modificación.
    return old["fecha_modificacion_drive"] != modified or old["tamano_bytes"] != size


def build_plan(
    inventory: DriveInventory,
    tables: Mapping[str, Sequence[Sequence[object]]],
    *,
    now: str | None = None,
    sync_id: str | None = None,
) -> SyncPlan:
    """Genera escrituras de filas sin alterar extracciones/validaciones previas."""
    now = now or datetime.now(timezone.utc).isoformat(timespec="seconds")
    sync_id = sync_id or uuid4().hex
    existing = {}
    next_row = {}
    for tab in HEADERS:
        records, last = _normalize_table(tab, tables[tab])
        existing[tab] = {item[HEADERS[tab][0]]: item for item in records}
        next_row[tab] = last + 1

    changes: list[CellUpdate] = []
    events: list[tuple[str, str, str, str, str, str]] = []
    new_works = new_pdfs = modified_pdfs = removed_pdfs = 0

    def persist(tab: str, record: dict[str, str], old: dict[str, str] | None) -> None:
        if old and all(record[k] == old[k] for k in HEADERS[tab]):
            return
        if old is None:
            row_num = next_row[tab]
            next_row[tab] += 1
        else:
            row_num = int(old["__row_number"])
        changes.append(CellUpdate(tab, row_num, tuple(record[k] for k in HEADERS[tab])))

    def event(entity: str, eid: str, obra_id: str, kind: str, before: str, after: str) -> None:
        events.append((entity, eid, obra_id, kind, before, after))

    works = {w.id: w for w in inventory.works}
    # Se registran PDFs y XLSX de catálogo en la misma tabla Documentos,
    # conservando el nombre histórico de las métricas pdf_* para contar
    # únicamente PDFs. Otros formatos permanecen fuera del registro.
    supported = [
        (work.id, doc)
        for work in inventory.works
        for doc in (*work.pdfs, *(f for f in work.other_files if f.mime_type == XLSX_MIME))
    ]
    docs = {doc.id: (obra_id, doc) for obra_id, doc in supported}
    if len(docs) != len(supported) or len(works) != len(inventory.works):
        raise SchemaMismatch("IDs de Drive repetidos en el inventario actual.")

    current_doc_records: dict[str, dict[str, str]] = {}
    for doc_id, (obra_id, doc) in docs.items():
        prior = existing["Documentos"].get(doc_id)
        checksum = doc.md5_checksum
        size = str(doc.size_bytes)
        if not prior:
            if doc.mime_type == PDF_MIME:
                new_pdfs += 1
            status = PENDING
            event("Documento", doc_id, obra_id, "Nuevo", "", doc.name)
        else:
            status = prior["estado_procesamiento"] or PENDING
            changed = _fingerprint_changed(prior, checksum, doc.modified_time, size)
            if changed:
                if doc.mime_type == PDF_MIME:
                    modified_pdfs += 1
                if status in PROCESSED:
                    status = MODIFIED
                event("Documento", doc_id, obra_id, "Contenido modificado",
                      prior["md5_checksum"], checksum)
            if prior["nombre_archivo"] != doc.name:
                event("Documento", doc_id, obra_id, "Renombrado",
                      prior["nombre_archivo"], doc.name)
            if prior["obra_id"] != obra_id:
                event("Documento", doc_id, obra_id, "Trasladado",
                      prior["obra_id"], obra_id)
            if prior["activo"] != "SI":
                event("Documento", doc_id, obra_id, "Reactivado", "NO", "SI")
        revision = int(prior["revision"] or 1) if prior else 1
        if prior and (checksum != prior["md5_checksum"] or doc.name != prior["nombre_archivo"]
                      or doc.modified_time != prior["fecha_modificacion_drive"]
                      or obra_id != prior["obra_id"] or prior["activo"] != "SI"):
            revision += 1
        item = {
            "documento_id": doc_id,
            "obra_id": obra_id,
            "nombre_archivo": doc.name,
            # Política de identificación: confiar en el nombre estándar.
            # Recalcular en cada sincronización (altas, cambios o renombrados).
            # No se leen bytes ni se ejecuta ninguna IA para clasificar.
            "tipo_documental": code_from_filename(doc.name, doc.mime_type) or "",
            "mime_type": doc.mime_type,
            "md5_checksum": checksum,
            "fecha_modificacion_drive": doc.modified_time,
            "tamano_bytes": size,
            "estado_procesamiento": status,
            "primera_deteccion_utc": prior["primera_deteccion_utc"] if prior else now,
            "ultima_deteccion_utc": now,
            "activo": "SI",
            "version_extractor": prior["version_extractor"] if prior else "",
            "resultado_id": prior["resultado_id"] if prior else "",
            "ultimo_error": prior["ultimo_error"] if prior else "",
            "revision": str(revision),
        }
        current_doc_records[doc_id] = item
        persist("Documentos", item, prior)

    for doc_id, prior in existing["Documentos"].items():
        if doc_id not in docs and prior["activo"] == "SI":
            if prior["mime_type"] == PDF_MIME:
                removed_pdfs += 1
            archived = {k: prior[k] for k in HEADERS["Documentos"]}
            archived["activo"] = "NO"
            archived["revision"] = str(int(prior["revision"] or 1) + 1)
            persist("Documentos", archived, prior)
            event("Documento", doc_id, prior["obra_id"], "Retirado", "SI", "NO")

    for obra_id, work in works.items():
        prior = existing["Obras"].get(obra_id)
        doc_records = [current_doc_records[d.id] for d in work.pdfs]
        pending = sum(d["estado_procesamiento"] in (PENDING, MODIFIED) for d in doc_records)
        modified = sum(d["estado_procesamiento"] == MODIFIED for d in doc_records)
        state = "Sin PDF" if not work.pdfs else "Pendiente de análisis" if pending else "Documentos registrados"
        if not prior:
            new_works += 1
            event("Obra", obra_id, obra_id, "Nueva", "", work.name)
        else:
            if prior["nombre_carpeta"] != work.name:
                event("Obra", obra_id, obra_id, "Renombrada", prior["nombre_carpeta"], work.name)
            if prior["activo"] != "SI":
                event("Obra", obra_id, obra_id, "Reactivada", "NO", "SI")
        revision = int(prior["revision"] or 1) if prior else 1
        if prior and (prior["nombre_carpeta"] != work.name or prior["activo"] != "SI"
                      or prior["estado_expediente"] != state
                      or prior["total_pdf"] != str(len(work.pdfs))
                      or prior["pdf_pendientes"] != str(pending)
                      or prior["pdf_modificados"] != str(modified)):
            revision += 1
        item = {
            "obra_id": obra_id,
            "nombre_carpeta": work.name,
            "estado_expediente": state,
            "total_pdf": str(len(work.pdfs)),
            "pdf_pendientes": str(pending),
            "pdf_modificados": str(modified),
            "ultima_vista_utc": now,
            "activo": "SI",
            "revision": str(revision),
        }
        persist("Obras", item, prior)

    for obra_id, prior in existing["Obras"].items():
        if obra_id not in works and prior["activo"] == "SI":
            archived = {k: prior[k] for k in HEADERS["Obras"]}
            archived["activo"] = "NO"
            archived["revision"] = str(int(prior["revision"] or 1) + 1)
            persist("Obras", archived, prior)
            event("Obra", obra_id, obra_id, "Retirada", "SI", "NO")

    for entity, eid, obra_id, kind, before, after in events:
        row = [
            uuid4().hex, sync_id, now, entity, eid, obra_id,
            kind, before, after, "Cambio detectado por consulta a Drive",
        ]
        changes.append(CellUpdate("Historial", next_row["Historial"], tuple(row)))
        next_row["Historial"] += 1

    sync_row = (
        sync_id, now, now, str(len(works)), str(inventory.pdf_total),
        str(new_works), str(new_pdfs), str(modified_pdfs), str(removed_pdfs),
        "OK", f"{len(events)} cambios documentados",
    )
    changes.append(CellUpdate("Sincronizaciones", next_row["Sincronizaciones"], sync_row))

    return SyncPlan(
        updates=tuple(changes), sync_id=sync_id, new_works=new_works,
        new_pdfs=new_pdfs, modified_pdfs=modified_pdfs, removed_pdfs=removed_pdfs,
        events=len(events), total_works=len(works), total_pdfs=inventory.pdf_total,
    )
