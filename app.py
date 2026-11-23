"""AuditorIA | Análisis de expedientes de adjudicación directa.

Interfaz operativa: fuente única de datos Google Drive / Google Sheets.
La IA nunca se ejecuta al navegar; requiere autorización y acción explícita.
"""
from __future__ import annotations

import streamlit as st

from security.app_access import require_access
from services.drive_service import (
    create_drive_client, is_configured, list_drive_groups,
)
from services.work_groups import (
    ALL_GROUPS, UNGROUPED, group_label, group_options,
)
from services.sheets_service import storage_configured
from ui.expedientes import render_expedientes
from ui.resultados import render_results
from ui.pruebas_adjudicacion import render_award_tests

st.set_page_config(
    page_title="AuditorIA · Expedientes de obra",
    page_icon="📂",
    layout="wide",
    initial_sidebar_state="expanded",
)

allowed = require_access()
if not allowed:
    st.error(
        "El acceso operativo requiere la autenticación con Google "
        "y la lista de usuarios autorizados. No hay demo pública."
    )
    st.stop()

st.markdown("""
<style>
.block-container{max-width:1480px;padding-top:2.0rem;padding-bottom:3rem}
h1,h2,h3{letter-spacing:-.028em}
h1{font-weight:750}
[data-testid="stMetric"]{
  border:1px solid rgba(120,130,150,.22);
  border-radius:13px;
  padding:17px 18px;
  background:rgba(130,140,160,.045);
}
[data-testid="stMetricValue"]{font-weight:700}
[data-testid="stExpander"]{
  border:1px solid rgba(130,140,155,.23);
  border-radius:11px;
}
section[data-testid="stSidebar"]{
  border-right:1px solid rgba(128,128,128,.12);
}
[data-testid="stDataFrame"]{border-radius:9px;overflow:hidden}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("## 📂 AuditorIA")
    st.caption("Gestión documental · Adjudicación directa")
    st.success("Sesión autorizada", icon=":material/verified_user:")
    st.divider()

    page = st.radio(
        "Navegación",
        ["Expedientes", "Resultados", "Pruebas de adjudicación"],
        index=0,
        key="app_section",
    )
    st.markdown("### Grupo de obras")
    ready_drive = is_configured(st.secrets)
    ready_sheets = storage_configured(st.secrets)
    if ready_drive:
        refresh_groups = st.button(
            "Actualizar grupos de Drive", key="work_groups_reload",
            use_container_width=True,
        )
        if refresh_groups or "work_groups_catalog" not in st.session_state:
            try:
                drive_client = create_drive_client(
                    dict(st.secrets["gcp_service_account"])
                )
                st.session_state["work_groups_catalog"] = list_drive_groups(
                    drive_client,
                    st.secrets["drive"]["root_folder_id"],
                    st.secrets["drive"].get("group_folder_ids", ()),
                )
                st.session_state.pop("work_groups_error", None)
                if refresh_groups:
                    st.session_state.pop("ex_inventory", None)
            except Exception:
                st.session_state["work_groups_error"] = (
                    "No fue posible consultar los grupos de Google Drive. "
                    "Los resultados previamente almacenados siguen disponibles."
                )
        if st.session_state.get("work_groups_error"):
            st.warning(st.session_state["work_groups_error"])
        catalog = st.session_state.get("work_groups_catalog")
        if catalog:
            options = group_options(catalog)
            if st.session_state.get("work_group_selection") not in options:
                st.session_state["work_group_selection"] = ALL_GROUPS
            selected_group = st.selectbox(
                "Mostrar obras de",
                options,
                format_func=lambda option: group_label(option, catalog),
                key="work_group_selection",
                help="Afecta Expedientes, Resultados y todas las pruebas. "
                     "Nunca borra ni reanaliza documentos.",
            )
            visible_count = sum(
                1 for _, group_id in catalog.work_to_group.items()
                if selected_group == ALL_GROUPS
                or (selected_group == UNGROUPED and not group_id)
                or selected_group == group_id
            )
            st.caption(f"{visible_count} obra(s) en la vista seleccionada.")
        else:
            st.session_state["work_group_selection"] = ALL_GROUPS
            st.caption("Vista de todas las obras (sin filtro de grupo).")
    else:
        st.session_state["work_group_selection"] = ALL_GROUPS
        st.caption("Configura Google Drive para filtrar por grupos.")

    # El selector global va antes del árbol lateral de carpetas.
    folder_panel = st.container() if page == "Expedientes" else None
    st.divider()
    ready_ai = bool(st.secrets.get("gemini", {}).get("api_key"))
    st.caption("SERVICIOS CONECTADOS")
    st.write(("● Drive" if ready_drive else "○ Drive sin configurar"))
    st.write(("● Google Sheets" if ready_sheets else "○ Google Sheets sin configurar"))
    st.write(("● Gemini" if ready_ai else "○ Gemini sin configurar"))
    st.divider()
    st.caption(
        "Los archivos solo se consultan de la carpeta autorizada en Google Drive. "
        "No compartas claves ni expedientes desde un repositorio público."
    )
    st.button("Cerrar sesión", on_click=st.logout, use_container_width=True)

if page == "Expedientes":
    render_expedientes(allowed, folder_container=folder_panel)
elif page == "Resultados":
    if not ready_sheets:
        st.error("Falta configurar Google Sheets para consultar los contratos.")
    else:
        render_results()
else:
    render_award_tests()

st.divider()
st.caption(
    "AuditorIA · Lectura documental con IA y trazabilidad por expediente. "
    "Los resultados requieren revisión profesional."
)
