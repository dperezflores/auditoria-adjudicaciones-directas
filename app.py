"""AuditorIA | Análisis de expedientes de adjudicación directa.

Interfaz operativa: fuente única de datos Google Drive / Google Sheets.
La IA nunca se ejecuta al navegar; requiere autorización y acción explícita.
"""
from __future__ import annotations

import streamlit as st

from security.app_access import require_access
from services.drive_service import is_configured
from services.sheets_service import storage_configured
from ui.expedientes import render_expedientes
from ui.resultados import render_results

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
    st.divider()
    ready_drive = is_configured(st.secrets)
    ready_sheets = storage_configured(st.secrets)
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
    render_expedientes(allowed)
elif page == "Resultados":
    if not (ready_drive and ready_sheets):
        st.error("Falta configurar Drive o Google Sheets.")
    else:
        render_results()
else:
    st.title("Pruebas de adjudicación directa")
    st.caption("El motor de pruebas normativas se incorporará a esta vista.")
    st.info(
        "La extracción de datos y el análisis documental ya están disponibles "
        "en Expedientes. Las pruebas de capital contable, especialidad, vigencia "
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
