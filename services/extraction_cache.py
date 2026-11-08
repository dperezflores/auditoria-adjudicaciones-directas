"""Claves deterministas de reutilización sin acceder a Google ni Gemini."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json


@dataclass(frozen=True)
class CacheKey:
    clave: str
    contenido_sha256: str
    modelo: str
    version_prompt: str
    version_esquema: str
    tipo_documento: str


def crear_clave_cache(
    contenido_pdf: bytes,
    *,
    modelo: str,
    version_prompt: str,
    version_esquema: str,
    tipo_documento: str = "contrato",
) -> CacheKey:
    """Igual PDF + modelo + versiones + tipo => igual clave de análisis.

    El ID y el nombre de Drive se almacenarán aparte: renombrar o mover el
    archivo no debe costar una segunda llamada de IA. Se calcula SHA-256 de
    los bytes reales antes de enviar el PDF, no solo de metadatos de Drive.
    """
    if not isinstance(contenido_pdf, bytes) or not contenido_pdf.startswith(b"%PDF-"):
        raise ValueError("Se requiere un PDF real en bytes.")
    parts = (modelo, version_prompt, version_esquema, tipo_documento)
    if any(not isinstance(x, str) or not x.strip() for x in parts):
        raise ValueError("Modelo, versiones y tipo documental son obligatorios.")
    sha = hashlib.sha256(contenido_pdf).hexdigest()
    firma = json.dumps([sha, *parts], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return CacheKey(
        clave=hashlib.sha256(firma).hexdigest(),
        contenido_sha256=sha,
        modelo=modelo,
        version_prompt=version_prompt,
        version_esquema=version_esquema,
        tipo_documento=tipo_documento,
    )
