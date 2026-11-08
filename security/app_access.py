"""Acceso a AuditorIA mediante Google OIDC (Streamlit st.login).

Este módulo controla quién puede utilizar la app, no concede permisos para
leer Drive. Una conexión central a Drive tendrá sus propias credenciales.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

REQUIRED_AUTH_FIELDS = (
    "redirect_uri",
    "cookie_secret",
    "client_id",
    "client_secret",
    "server_metadata_url",
)


def configuration_status(settings: Mapping[str, Any]) -> str:
    """Devuelve 'demo', 'incomplete' o 'enabled'.

    Sin [auth], solo se mantiene la demo con datos ficticios.
    Si aparece [auth] pero está incompleto, se bloquea el acceso.
    """
    auth = settings.get("auth")
    if auth is None:
        return "demo"
    if not isinstance(auth, Mapping):
        return "incomplete"
    for field in REQUIRED_AUTH_FIELDS:
        value = auth.get(field)
        if not isinstance(value, str) or not value.strip():
            return "incomplete"

    access = settings.get("access")
    if not isinstance(access, Mapping):
        return "incomplete"
    emails = access.get("allowed_emails")
    if not isinstance(emails, (list, tuple)) or not emails:
        return "incomplete"
    if any(not isinstance(email, str) or "@" not in email or not email.strip()
           for email in emails):
        return "incomplete"
    return "enabled"


def is_authorized_identity(identity: Mapping[str, Any],
                           allowed_emails: list[str] | tuple[str, ...]) -> bool:
    """Autorizar únicamente identidades Google con correo verificado."""
    if identity.get("email_verified") is not True:
        return False
    email = identity.get("email")
    if not isinstance(email, str):
        return False
    normalized = email.strip().casefold()
    return normalized in {
        item.strip().casefold() for item in allowed_emails if isinstance(item, str)
    }


def require_access() -> bool:
    """Impide cargar vistas privadas sin usuario autorizado.

    Devuelve False solamente en modo demo, que nunca debe manejar expedientes
    reales. Devuelve True cuando se autenticó a un usuario permitido.
    """
    import streamlit as st

    try:
        status = configuration_status(st.secrets)
    except FileNotFoundError:
        status = "demo"

    if status == "demo":
        return False
    if status == "incomplete":
        st.error(
            "La autenticación está parcialmente configurada. "
            "Corrige [auth] y [access] en los secretos privados de Streamlit."
        )
        st.stop()

    if not st.user.is_logged_in:
        st.title("Acceso a AuditorIA")
        st.info("Esta aplicación requiere iniciar sesión con una cuenta autorizada.")
        st.button("Iniciar sesión con Google", on_click=st.login, type="primary")
        st.stop()

    if not is_authorized_identity(st.user, st.secrets["access"]["allowed_emails"]):
        st.error("Tu cuenta de Google no está autorizada para usar AuditorIA.")
        st.button("Cerrar sesión", on_click=st.logout)
        st.stop()

    return True
