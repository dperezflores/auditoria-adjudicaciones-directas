"""Elegibilidad para actualizar contratos guardados con un prompt posterior.

La actualización es voluntaria, conserva íntegra la extracción anterior y
reutiliza el mismo motor/cerrojo de escritura. Este módulo no llama Gemini.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from services.contract_prompt import PROMPT_VERSION
from services.contract_v2 import CONTRACT_SCHEMA_V2
from services.document_classifier import code_from_filename
from services.drive_service import DocumentRecord, MAX_PDF_BYTES, PDF_MIME


def eligible_contract_upgrade(
    doc: DocumentRecord,
    obra_id: str,
    registered: Mapping[str, str] | None,
    saved: Mapping[str, str] | None,
    attempts: Sequence[Mapping[str, str]],
) -> tuple[bool, str]:
    """No reanalizar versiones actuales ni intentos no confirmados."""
    if code_from_filename(doc.name, doc.mime_type) != "CONTRATO":
        return False, "Esta acción solo está disponible para CONTRATO.pdf."
    if doc.mime_type != PDF_MIME or not (0 < doc.size_bytes <= MAX_PDF_BYTES):
        return False, "El PDF no tiene tamaño válido para la extracción."
    if not registered or (
        registered.get("documento_id") != doc.id
        or registered.get("obra_id") != obra_id
        or registered.get("activo") != "SI"
        or registered.get("md5_checksum") != doc.md5_checksum
        or registered.get("tipo_documental") != "CONTRATO"
        or registered.get("estado_procesamiento") == "Modificado desde el último análisis"
    ):
        return False, "El inventario de Drive no coincide con el registro activo."
    if not saved or not (
        saved.get("cache_key") == registered.get("resultado_id")
        and saved.get("version_esquema") == CONTRACT_SCHEMA_V2
        and saved.get("documento_id") == doc.id
        and saved.get("obra_id") == obra_id
        and saved.get("estado") == "COMPLETADO"
        and saved.get("resultado_json")
    ):
        return False, "No existe extracción de contrato v2 confirmada para actualizar."
    if saved.get("version_prompt") == PROMPT_VERSION:
        return False, "El contrato ya tiene la versión actual del extractor."
    if any(
        entry.get("documento_id") == doc.id
        and entry.get("obra_id") == obra_id
        and entry.get("version_esquema") == CONTRACT_SCHEMA_V2
        and entry.get("estado") in ("EN_PROCESO", "REQUIERE_REVISION")
        for entry in attempts
    ):
        return False, "Existe un intento no confirmado; revisar antes de gastar IA."
    return True, f"Extracción actual: {saved.get('version_prompt')}; nueva: {PROMPT_VERSION}."
