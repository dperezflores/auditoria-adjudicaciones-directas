"""Componentes de presentación para la interfaz de AuditorIA.

Este módulo no descarga expedientes ni invoca servicios: las acciones llegan
como callbacks explícitos de la aplicación que verifica el acceso del usuario.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Callable
from zoneinfo import ZoneInfo

import streamlit as st

from ui.theme import NAVIGATION, state_style


_ICONS = {
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "partial": '<circle cx="12" cy="12" r="9"/><path d="M12 3v18"/>',
    "refresh": '<path d="M21 12a9 9 0 1 1-3-6.7L21 8M21 3v5h-5"/>',
    "warning": '<path d="M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>',
    "question": '<path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3M12 17h.01"/>',
    "minus": '<path d="M5 12h14"/>',
    "cross": '<path d="M6 6l12 12M18 6 6 18"/>',
    "sparkles": '<path d="m12 3 2.1 6.9L21 12l-6.9 2.1L12 21l-2.1-6.9L3 12l6.9-2.1L12 3z"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10H3z"/>',
    "file": '<path d="M7 3h7l5 5v13H7zM14 3v5h5"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    "shield": '<path d="M12 2 4 5v6c0 5 4 8 8 11 4-3 8-6 8-11V5z"/>',
}


def icono(name: str, *, size: int = 16) -> str:
    """SVG estricto: las rutas provienen de una lista cerrada, no de documentos."""
    path = _ICONS.get(name, _ICONS["file"])
    safe_size = max(10, min(int(size), 32))
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{safe_size}" '
        f'height="{safe_size}" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
        f'stroke-linejoin="round" aria-hidden="true">{path}</svg>'
    )


def pildora_estado(estado: str) -> str:
    """Produce HTML escapado que solo usa clases y SVG del sistema visual."""
    style = state_style(estado)
    return (
        f'<span class="aud-pill aud-pill--{style.slug}">'
        f'{icono(style.icon, size=13)}<span>{escape(style.label)}</span></span>'
    )


def sincronizacion_local(iso_utc: str | None, *, now: datetime | None = None) -> str:
    """Presentación local sin inferir sincronizaciones inexistentes.

    La aplicación persiste UTC y únicamente calcula el tiempo transcurrido.
    """
    if not iso_utc:
        return "Sin revisar"
    try:
        parsed = datetime.fromisoformat(iso_utc.strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        local = parsed.astimezone(ZoneInfo("America/Mexico_City"))
        moment = now or datetime.now(ZoneInfo("America/Mexico_City"))
        moment = moment.astimezone(ZoneInfo("America/Mexico_City"))
        seconds = (moment - local).total_seconds()
        if seconds < 0:
            return "Última revisión: " + local.strftime("%d/%m/%Y %H:%M")
        minutes = int(seconds // 60)
        if minutes == 0:
            return "Revisada hace menos de 1 min"
        if minutes < 60:
            return f"Revisada hace {minutes} min"
        if minutes < 1440:
            return f"Revisada hace {minutes // 60} h"
        return "Revisada el " + local.strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError, OverflowError):
        return "Sin revisar"


def _service_status(name: str, ready: bool) -> str:
    visible_name = escape(name)
    return (
        f'<span class="aud-service {"aud-service--ready" if ready else ""}" '
        f'title="{visible_name}: {"conectado" if ready else "sin configurar"}">'
        f'<span class="aud-service-dot"></span>{visible_name}</span>'
    )


def encabezado_app(
    *,
    root_name: str | None,
    synced_at: str | None,
    ready_drive: bool,
    ready_sheets: bool,
    ready_gemini: bool,
    user_email: str,
    on_refresh: Callable[[], None],
) -> str:
    """Devuelve el apartado seleccionado sin consultar Drive automáticamente."""
    with st.container(key="auditoria_header"):
        brand, navigation, user = st.columns([2.0, 5.0, 2.2], gap="medium",
                                             vertical_alignment="center")
        with brand:
            st.markdown(
                '<div class="aud-brand"><span class="aud-brand-mark">A</span>'
                '<div><div class="aud-brand-title">AuditorIA</div>'
                '<div class="aud-brand-subtitle">Adjudicaciones directas</div></div></div>',
                unsafe_allow_html=True,
            )
        with navigation:
            page = st.segmented_control(
                "Navegación", NAVIGATION,
                selection_mode="single", default=NAVIGATION[0],
                required=True, key="app_section", label_visibility="collapsed",
                width="stretch",
            )
        with user:
            st.markdown(
                f'<div class="aud-user" title="{escape(user_email, quote=True)}">'
                f'{icono("user", size=13)} {escape(user_email)}</div>',
                unsafe_allow_html=True,
            )
            st.button(
                "Cerrar sesión", key="ex_logout_header", type="secondary",
                on_click=st.logout, use_container_width=True,
            )
        st.markdown('<div class="aud-header-foot"></div>', unsafe_allow_html=True)
        root, last_sync, refresh = st.columns([4.4, 2.5, 2.1], gap="small",
                                               vertical_alignment="center")
        with root:
            root_label = root_name if root_name else "Carpeta raíz por cargar"
            st.markdown(
                f'<div class="aud-root-line">{icono("folder", size=15)}'
                f'<span class="aud-root" title="{escape(root_label, quote=True)}">'
                f'{escape(root_label)}</span></div>',
                unsafe_allow_html=True,
            )
        with last_sync:
            st.markdown(
                f'<div class="aud-last-sync">{escape(sincronizacion_local(synced_at))}</div>',
                unsafe_allow_html=True,
            )
        with refresh:
            st.button(
                "Actualizar Google Drive", key="ex_refresh_header",
                type="secondary", on_click=on_refresh,
                disabled=not (ready_drive and ready_sheets),
                use_container_width=True,
            )
        st.markdown(
            '<div class="aud-services">'
            + _service_status("Drive", ready_drive)
            + _service_status("Sheets", ready_sheets)
            + _service_status("Gemini", ready_gemini)
            + '</div>',
            unsafe_allow_html=True,
        )
    return page or NAVIGATION[0]


def barra_seleccion(
    *,
    cantidad: int,
    obras: int,
    tamano_mb: float,
    catalogos: int,
    al_limpiar: Callable[[], None],
    al_analizar: Callable[[], None],
    deshabilitado: bool = False,
) -> None:
    """Componente listo para la Pantalla 1 (se conectará en el Paso B).

    No inicia ninguna acción a menos que se pulse expresamente el botón.
    """
    with st.container(key="ex_barra_seleccion"):
        if cantidad <= 0:
            st.caption(
                "Marca obras completas o documentos sueltos para analizarlos con IA. "
                "Los documentos ya analizados se omiten solos."
            )
            return
        summary, clear, run = st.columns([5, 1.7, 2.5],
                                          gap="small", vertical_alignment="center")
        with summary:
            st.markdown(
                f"**{cantidad} documentos seleccionados en {obras} obras**"
            )
            st.caption(
                f"{tamano_mb:.2f} MB en total · "
                f"{catalogos} catálogos se importan sin IA"
            )
        with clear:
            st.button("Limpiar selección", key="ex_limpiar_barra",
                      on_click=al_limpiar, use_container_width=True)
        with run:
            st.button("✦ Analizar con IA", key="ex_analizar_barra",
                      on_click=al_analizar, disabled=deshabilitado,
                      type="primary", use_container_width=True)
