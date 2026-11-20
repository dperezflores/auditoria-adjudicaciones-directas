"""Planificador sin IA para seleccionar CONTRATO/PUC de múltiples obras.

Nunca descarga PDFs, escribe en Sheets ni invoca Gemini. El inventario
y el estado provienen de la sincronización previamente autorizada.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from services.analysis_catalog import FileStatus
from services.document_classifier import code_from_filename
from services.drive_service import (
    DriveInventory, DocumentRecord, WorkRecord, PDF_MIME, MAX_PDF_BYTES,
)


BULK_CODES = ("CONTRATO", "PUC")
BULK_SCHEMAS = {"CONTRATO": "contrato-v2", "PUC": "puc-v1"}


@dataclass(frozen=True)
class BulkItem:
    work: WorkRecord
    document: DocumentRecord
    code: str


@dataclass(frozen=True)
class BulkDecision:
    folder: str
    code: str
    document: str
    status: str
    detail: str


@dataclass(frozen=True)
class BulkPlan:
    pending: tuple[BulkItem, ...]
    decisions: tuple[BulkDecision, ...]
    folders: int

    @property
    def ready(self) -> int:
        return len(self.pending)

    def count(self, status: str) -> int:
        return sum(item.status == status for item in self.decisions)


def plan_bulk_analysis(
    inventory: DriveInventory,
    tables: Mapping[str, Sequence[Mapping[str, str]]],
    states: Mapping[str, FileStatus],
    folder_ids: Sequence[str],
    codes: Sequence[str],
) -> BulkPlan:
    """Un PDF canónico por tipo/obra. Análisis no confirmados quedan bloqueados.

    Las extracciones COMPLETADAS para el esquema vigente no se cobran otra vez,
    incluso si proceden de una versión previa de prompt. Para reextraer un
    contrato con nuevo prompt usar la acción individual de actualización.
    """
    selected = set(folder_ids)
    wanted = tuple(dict.fromkeys(codes))
    if not wanted or any(code not in BULK_CODES for code in wanted):
        raise ValueError("El lote solo permite CONTRATO y/o PUC.")
    existing = {work.id for work in inventory.works}
    if not selected or not selected.issubset(existing):
        raise ValueError("Selecciona al menos una obra del inventario autorizado.")

    registered = {row["documento_id"]: row for row in tables["Documentos"]}
    extracted = {row["cache_key"]: row for row in tables["Extracciones"]}
    unresolved = {
        (row["obra_id"], row["documento_id"], row["version_esquema"])
        for row in tables["Extracciones"]
        if row["estado"] in ("EN_PROCESO", "REQUIERE_REVISION")
    }
    pending: list[BulkItem] = []
    decisions: list[BulkDecision] = []
    for work in inventory.works:
        if work.id not in selected:
            continue
        for code in wanted:
            matches = [
                doc for doc in work.pdfs
                if code_from_filename(doc.name, doc.mime_type) == code
            ]
            if not matches:
                decisions.append(BulkDecision(
                    work.name, code, "—", "No encontrado",
                    f"No existe {code}.pdf con nombre canónico en esta carpeta.",
                ))
                continue
            if len(matches) > 1:
                decisions.append(BulkDecision(
                    work.name, code, " / ".join(
                        (doc.relative_path + "/" if doc.relative_path else "") + doc.name
                        for doc in matches[:3]
                    ), "Ambiguo",
                    "Se encontraron varios documentos del mismo tipo. "
                    "Selecciona el documento correcto individualmente.",
                ))
                continue
            doc = matches[0]
            detail = (doc.relative_path + "/" if doc.relative_path else "") + doc.name
            status = states.get(doc.id)
            row = registered.get(doc.id)
            schema = BULK_SCHEMAS[code]
            reason = ""
            decision = ""
            if doc.mime_type != PDF_MIME or not (0 < doc.size_bytes <= MAX_PDF_BYTES):
                decision, reason = "Bloqueado", "PDF vacío, tamaño desconocido o mayor a 50 MB."
            elif not doc.md5_checksum:
                decision, reason = "Bloqueado", "Falta la huella MD5 de Drive."
            elif not row or (
                row.get("documento_id") != doc.id
                or row.get("obra_id") != work.id
                or row.get("activo") != "SI"
                or row.get("md5_checksum") != doc.md5_checksum
                or row.get("tipo_documental") != code
            ):
                decision, reason = "Desactualizado", (
                    "El registro de Sheets no coincide con Drive; actualiza Google Drive."
                )
            elif (work.id, doc.id, schema) in unresolved:
                decision, reason = "Bloqueado", (
                    "Existe un intento no confirmado; no reintentar automáticamente."
                )
            elif status is None or status.label in (
                "Sin registrar", "Desactualizado", "Parcial", "Revisar error",
            ):
                decision, reason = "Bloqueado", (
                    "El archivo requiere sincronización o revisión de su estado."
                )
            else:
                saved = extracted.get(row.get("resultado_id", ""))
                if saved and (
                    saved.get("version_esquema") == schema
                    and saved.get("estado") == "COMPLETADO"
                    and bool(saved.get("resultado_json"))
                    and saved.get("documento_id") == doc.id
                    and saved.get("obra_id") == work.id
                ):
                    decision, reason = "Ya analizado", (
                        "Extracción especializada existente: se omite sin consumir Gemini."
                    )
                else:
                    decision, reason = "Pendiente", "Listo para análisis bajo solicitud expresa."
                    pending.append(BulkItem(work, doc, code))
            decisions.append(BulkDecision(
                work.name, code, detail, decision, reason,
            ))
    return BulkPlan(tuple(pending), tuple(decisions), len(selected))
