"""Clasificación segura de errores de solicitudes Gemini.

Nunca usar el mensaje completo del proveedor para UI o Google Sheets:
puede incluir detalles del request. Exponer solo HTTP y status estándar.
"""
from __future__ import annotations

import re


def safe_code(value: object) -> int | None:
    try:
        code = int(value)  # el SDK suele devolver un entero
    except (TypeError, ValueError):
        return None
    return code if 100 <= code <= 599 else None


def safe_status(value: object) -> str:
    if isinstance(value, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,49}", value):
        return value
    return "NO_STATUS"


class GeminiRequestError(Exception):
    """Error sanitized: solo HTTP code/status, nunca mensajes ni claves."""

    def __init__(self, code: object, status: object = None):
        self.http_code = safe_code(code)
        self.status = safe_status(status)
        self.public_code = f"HTTP_{self.http_code or 'UNKNOWN'}_{self.status}"
        super().__init__(self.public_code)

    @property
    def explanation(self) -> str:
        code = self.http_code
        if code == 400 and self.status == "FAILED_PRECONDITION":
            return "Google rechazó un requisito previo; comprueba la habilitación de facturación o del servicio."
        if code == 400:
            return "Google rechazó los parámetros de la solicitud; revisaremos esquema y configuración."
        if code == 401:
            return "Google rechazó la autenticación de la clave API."
        if code == 402:
            return "Google informa un problema de crédito o facturación."
        if code == 403:
            return "Google denegó el permiso para generar con este modelo."
        if code == 404:
            return "El modelo no está disponible en ese endpoint para la clave utilizada."
        if code == 429:
            return "Se alcanzó una cuota o límite de solicitudes. No repitas automáticamente."
        if code in (500, 502, 503, 504):
            return "Error temporal del proveedor. Comprueba estado y facturación antes de reintentar."
        return "No se pudo completar la solicitud. Revisa las condiciones y registro del proveedor."
