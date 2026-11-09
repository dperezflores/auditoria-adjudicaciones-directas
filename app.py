"""AuditorIA | Análisis de expedientes de adjudicación directa.

Interfaz operativa: fuente única de datos Google Drive / Google Sheets.
La IA nunca se ejecuta al navegar; requiere autorización y acción explícita.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from security.app_access import require_access
from services.drive_service import is_configured
from services.sheets_service import storage_configured
from ui.components import encabezado_app
from ui.expedientes import _refresh_inventory
from ui.explorer_panel import render_expedientes
from ui.resultados import render_results

st.set_page_config(
    page_title="AuditorIA · Expedientes de obra",
    page_icon="📂",
    layout="wide",
    initial_sidebar_state="collapsed",
)

allowed = require_access()
if not allowed:
    st.error(
        "El acceso operativo requiere la autenticación con Google "
        "y la lista de usuarios autorizados. No hay demo pública."
    )
    st.stop()

# Estilos locales estáticos, una sola inyección por render; sin fuentes de datos externas.
_style_path = Path(__file__).resolve().parent / "ui" / "styles.css"
st.markdown(
    "<style>" + _style_path.read_text(encoding="utf-8") + "</style>",
    unsafe_allow_html=True,
)


def _refresh_from_header() -> None:
    """Acción explícita, con el mismo flujo de sincronización y escritura protegido."""
    try:
        _refresh_inventory()
        st.session_state.pop("ex_sync_error", None)
        st.session_state["ex_header_refresh_success"] = True
    except Exception:
        st.session_state["ex_sync_error"] = (
            "No se pudo completar la sincronización. Comprueba los permisos "
            "de Drive y Google Sheets."
        )
        st.session_state.pop("ex_header_refresh_success", None)


ready_drive = is_configured(st.secrets)
ready_sheets = storage_configured(st.secrets)
ready_ai = bool(st.secrets.get("gemini", {}).get("api_key"))
_inventory = st.session_state.get("ex_inventory")
page = encabezado_app(
    root_name=_inventory.root_name if _inventory else None,
    synced_at=st.session_state.get("ex_synced_at"),
    ready_drive=ready_drive,
    ready_sheets=ready_sheets,
    ready_gemini=ready_ai,
    user_email=str(st.user.email or ""),
    on_refresh=_refresh_from_header,
)
if st.session_state.pop("ex_header_refresh_success", False):
    st.success("Google Drive actualizado y registros sincronizados.")
if st.session_state.get("ex_sync_error") and page != "Expedientes":
    st.error(st.session_state["ex_sync_error"])

if page == "Expedientes":
    render_expedientes(allowed)
elif page == "Resultados":
    if not ready_sheets:
        st.error("Falta configurar Google Sheets para consultar los contratos.")
    else:
        render_results()
else:
    st.title("Pruebas de adjudicación directa")
    st.caption("El motor de pruebas normativas se incorporará a esta vista.")
    st.info(
        "La identificación documental se realiza por nombre y ya está "
        "disponibles los extractores PUC-v1, DICTAMEN_AD-v1, NOTIFICACION_AD-v1 y ORDEN_AD-v1 en Expedientes. "
        "Los demás extractores se activarán por etapas. Las pruebas "
        "de capital contable, especialidad, vigencia "
        "del PUC, responsable técnico y secuencia de fechas requieren reglas "
        "y evidencias específicas que implementaremos posteriormente."
    )
    st.table({
        "Prueba": [
            "Capital contable", "Especialidad del contratista",
            "Vigencia del PUC", "Responsable técnico",
            "Dictamen, notificación y firma del contrato",
        ],
        "Estado": ["Por implementar"] * 5,
    })

st.divider()
st.caption(
    "AuditorIA · Lectura documental con IA y trazabilidad por expediente. "
    "Los resultados requieren revisión profesional."
)
