"""Diagnóstico no generativo: consulta el modelo, sin enviar PDF ni prompt.

La llamada models.get usa metadatos; NO invoca generate_content.
No expone la API key ni mensajes completos de error del proveedor.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ModelDiagnostic:
    available: bool
    http_code: int | None
    code: str
    description: str


_DESCRIPTIONS = {
    400: "Solicitud de metadatos inválida. Revisa el identificador y las opciones de API.",
    401: "La clave API no fue aceptada; verifica que esté vigente y bien copiada.",
    403: "El proyecto de la clave no tiene autorización para consultar el modelo. Verifica permisos y restricciones de API.",
    404: "El modelo solicitado no está disponible para la clave o la versión de API utilizada.",
    429: "Límite temporal de solicitudes alcanzado; verifica las cuotas de Google.",
}


def inspect_model(
    api_key: str,
    model: str,
    *,
    client_factory: Callable[..., Any] | None = None,
) -> ModelDiagnostic:
    if not isinstance(api_key, str) or not api_key.strip():
        return ModelDiagnostic(False, None, "NO_KEY", "Falta la clave API en Streamlit Secrets.")
    if not isinstance(model, str) or not model.strip():
        return ModelDiagnostic(False, None, "NO_MODEL", "El modelo configurado está vacío.")

    if client_factory is None:
        from google import genai
        client_factory = genai.Client
    client = None
    try:
        client = client_factory(api_key=api_key)
        metadata = client.models.get(model=model.strip())
        if metadata is None:
            return ModelDiagnostic(False, None, "NO_METADATA", "Google no devolvió metadatos.")
        return ModelDiagnostic(
            True, 200, "MODEL_VISIBLE",
            "La clave puede consultar los metadatos del modelo. Esto no garantiza que la solicitud de PDF sea admitida.",
        )
    except Exception as exc:
        raw_code = getattr(exc, "code", None)
        try:
            code = int(raw_code)
        except (ValueError, TypeError):
            code = None
        return ModelDiagnostic(
            False,
            code,
            f"HTTP_{code}" if code else "CONNECTION_ERROR",
            _DESCRIPTIONS.get(
                code,
                "No fue posible consultar metadatos del modelo. "
                "Revisa la configuración y el estado de Google AI Studio.",
            ),
        )
    finally:
        if client is not None:
            close = getattr(client, "close", None)
            if callable(close):
                close()
