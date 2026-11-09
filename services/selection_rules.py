"""Elegibilidad documental PURA para el explorador de AuditorIA.

Transcripción de la misma ruta de decisión de ui/expedientes.py: no ejecuta
IA, no abre Drive, no escribe a Sheets. Una obra por ejecución, diez archivos
como máximo; los ya analizados y los intentos inciertos se omiten.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from services.analysis_catalog import FileStatus
from services.document_classifier import code_from_filename, XLSX_MIME
from services.drive_service import DocumentRecord, MAX_PDF_BYTES, MAX_XLSX_BYTES


MAX_BATCH = 10


@dataclass(frozen=True)
class DocumentDecision:
    document_id: str
    disposition: str
    explanation: str
    schema: str = ""

    @property
    def selectable(self) -> bool:
        return self.disposition == "eligible"


@dataclass(frozen=True)
class SelectionPlan:
    work_id: str
    decisions: Mapping[str, DocumentDecision]
    eligible: tuple[DocumentRecord, ...]
    batch: tuple[DocumentRecord, ...]
    reused: tuple[DocumentRecord, ...]
    blocked: tuple[DocumentRecord, ...]
    needs_sync: tuple[DocumentRecord, ...]
    ignored: tuple[DocumentRecord, ...]
    not_registered: tuple[DocumentRecord, ...]

    @property
    def eligible_ids(self) -> frozenset[str]:
        return frozenset(item.id for item in self.eligible)

    @property
    def has_next_batch(self) -> bool:
        return len(self.eligible) > len(self.batch)


def plan_work_selection(
    work_id: str,
    documents: Sequence[DocumentRecord],
    registered: Mapping[str, Mapping[str, str]],
    extractions: Mapping[str, Mapping[str, str]],
    states: Mapping[str, FileStatus],
    enabled_extractors: Mapping[str, str],
    *,
    max_batch: int = MAX_BATCH,
    extraction_rows: Sequence[Mapping[str, str]] | None = None,
) -> SelectionPlan:
    """Misma elegibilidad que la UI original, con razones explícitas.

    - Un registro vigente y el código documental deben coincidir con Drive.
    - Los intentos en curso/de revisión del MISMO esquema bloquean análisis.
    - Una extracción completa del mismo esquema se reutiliza.
    - Los documentos fuera de tamaño o sin clasificador no son seleccionables.
    - Un catálogo elegible es XLSX; nunca se manda a Gemini.
    """
    if max_batch <= 0 or max_batch > MAX_BATCH:
        raise ValueError("El límite por ejecución debe estar entre 1 y 10.")

    decisions: dict[str, DocumentDecision] = {}
    bins: dict[str, list[DocumentRecord]] = {
        name: [] for name in (
            "eligible", "reused", "blocked", "needs_sync",
            "ignored", "not_registered",
        )
    }
    all_extractions = (
        tuple(extraction_rows)
        if extraction_rows is not None else tuple(extractions.values())
    )
    for doc in documents:
        if doc.id in decisions:
            raise ValueError("Documento repetido dentro de la obra.")
        code = code_from_filename(doc.name, doc.mime_type)
        schema = enabled_extractors.get(code or "")
        disposition = "ignored"
        reason = "Tipo sin extractor habilitado; renombra el archivo en Drive."
        if not schema:
            pass
        elif doc.mime_type not in ("application/pdf", XLSX_MIME):
            reason = "Formato incompatible con el extractor."
        elif not (0 < doc.size_bytes <= (
            MAX_XLSX_BYTES if doc.mime_type == XLSX_MIME else MAX_PDF_BYTES
        )):
            reason = (
                "Sin tamaño válido o supera 15 MB para XLSX."
                if doc.mime_type == XLSX_MIME else
                "Sin tamaño válido o supera 50 MB para PDF."
            )
        else:
            row = registered.get(doc.id)
            if not row or row.get("obra_id") != work_id or row.get("activo") != "SI":
                disposition = "not_registered"
                reason = "Actualiza Google Drive para registrar este archivo."
            elif row.get("md5_checksum") != doc.md5_checksum or row.get("tipo_documental") != code:
                disposition = "needs_sync"
                reason = "Huella o clasificación desactualizada. Actualiza Google Drive."
            else:
                pending_attempt = any(
                    item.get("documento_id") == doc.id
                    and item.get("obra_id") == work_id
                    and item.get("version_esquema") == schema
                    and item.get("estado") in ("EN_PROCESO", "REQUIERE_REVISION")
                    for item in all_extractions
                )
                if pending_attempt:
                    disposition = "blocked"
                    reason = "Intento no confirmado: requiere revisión antes de cualquier reintento."
                else:
                    saved = extractions.get(row.get("resultado_id", ""))
                    state = states.get(doc.id)
                    if (
                        saved and saved.get("version_esquema") == schema
                        and state and state.label == "Analizado"
                        and saved.get("estado") == "COMPLETADO"
                        and saved.get("resultado_json")
                        and saved.get("documento_id") == doc.id
                        and saved.get("obra_id") == work_id
                    ):
                        disposition = "reused"
                        reason = "Análisis vigente guardado. No consumir Gemini nuevamente."
                    elif state and state.label != "Sin registrar":
                        disposition = "eligible"
                        reason = (
                            "Importación Excel sin IA."
                            if doc.mime_type == XLSX_MIME
                            else "Disponible para análisis de PDF completo con Gemini."
                        )
                    else:
                        disposition = "not_registered"
                        reason = "El documento debe registrarse antes del análisis."

        decisions[doc.id] = DocumentDecision(doc.id, disposition, reason, schema or "")
        bins[disposition].append(doc)

    eligible = tuple(bins["eligible"])
    return SelectionPlan(
        work_id=work_id,
        decisions=decisions,
        eligible=eligible,
        batch=eligible[:max_batch],
        reused=tuple(bins["reused"]),
        blocked=tuple(bins["blocked"]),
        needs_sync=tuple(bins["needs_sync"]),
        ignored=tuple(bins["ignored"]),
        not_registered=tuple(bins["not_registered"]),
    )
