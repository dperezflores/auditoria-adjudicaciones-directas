"""AuditorIA · Adjudicaciones Directas.
Primer despliegue seguro: solo datos ficticios. Sin credenciales ni llamadas externas.
"""
from __future__ import annotations
from datetime import datetime, timezone
import pandas as pd
import streamlit as st

from security.app_access import require_access
from ui.drive_explorer import render_drive_explorer

st.set_page_config(page_title="AuditorIA | Adjudicaciones directas", page_icon="📋", layout="wide")

# La demostración sigue abierta sin secretos; cualquier [auth] incompleto bloquea.
access_granted = require_access()

st.markdown("""
<style>
.block-container {padding-top:1.6rem;max-width:1400px}
[data-testid="stMetric"] {border:1px solid rgba(125,125,125,.2);border-radius:12px;padding:14px}
h1 {letter-spacing:-.04em}
</style>
""", unsafe_allow_html=True)

if "obras_demo" not in st.session_state:
    st.session_state.obras_demo = [
        {"id":"demo-001","obra":"Obra 001 - Pavimentación urbana","documentos":["Contrato.pdf","PUC.pdf"],"contratista":"Constructora Ejemplo, S.A. de C.V."},
        {"id":"demo-002","obra":"Obra 002 - Rehabilitación de parque","documentos":["Dictamen.pdf"],"contratista":"Empresa Ficticia Dos"},
        {"id":"demo-003","obra":"Obra 003 - Urbanización","documentos":[],"contratista":"Sin identificar"},
    ]
if "demo_counter" not in st.session_state:
    st.session_state.demo_counter = 0

with st.sidebar:
    st.title("AuditorIA")
    st.caption("Piloto · Adjudicaciones directas")
    if access_granted:
        st.caption("Acceso verificado con Google")
        st.button("Cerrar sesión", on_click=st.logout)
    else:
        st.caption("Demo pública sin autenticación ni documentos reales")
    st.divider()
    st.success("Entorno de demostración")
    st.write("No conectado a Google Drive")
    st.write("Gemini: inactivo")
    st.write("Persistencia: solo esta sesión")
    st.divider()
    st.caption("Próximo paso: configurar OAuth, Drive y registro persistente. Los expedientes reales no deben cargarse en esta versión.")

st.title("AuditorIA")
st.caption("Revisión de adjudicaciones directas de obra pública")
st.warning("**MODO DEMOSTRACIÓN.** Obras y documentos ficticios. Ningún archivo real se consulta, almacena ni envía a IA.")

tab1, tab2, tab3, tab4 = st.tabs(["Explorador demo", "Pruebas de auditoría", "Dashboard general", "Google Drive (piloto)"])

with tab1:
    st.subheader("Explorador documental")
    st.caption("El siguiente explorador simula la experiencia final. La conexión real a Drive se incorporará en el siguiente paso.")
    left, right = st.columns([1, 4])
    with left:
        if st.button("Simular PDF nuevo", type="primary", use_container_width=True):
            st.session_state.demo_counter += 1
            st.session_state.obras_demo[0]["documentos"].append(
                f"Documento_prueba_{st.session_state.demo_counter}.pdf"
            )
            st.rerun()
    with right:
        if st.button("Restablecer demostración"):
            for k in ("obras_demo", "demo_counter"):
                st.session_state.pop(k, None)
            st.rerun()

    obras = st.session_state.obras_demo
    tot_docs = sum(len(o["documentos"]) for o in obras)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Obras detectadas", len(obras))
    c2.metric("Documentos PDF", tot_docs)
    c3.metric("Pendientes de IA", tot_docs)
    c4.metric("Procesados", 0)

    filtro = st.text_input("Buscar obra", placeholder="Nombre o identificador")
    visible = [o for o in obras if filtro.casefold() in (o["obra"] + " " + o["id"]).casefold()]
    tabla = [{"Obra":o["obra"],"ID de obra":o["id"],"PDF":len(o["documentos"]),
              "Estado":"Pendiente de análisis" if o["documentos"] else "Sin documentos"}
             for o in visible]
    if tabla:
        st.dataframe(pd.DataFrame(tabla), hide_index=True, use_container_width=True)
    else:
        st.info("No se encontraron obras.")

    seleccionado = st.selectbox("Selecciona una obra", [o["id"] for o in obras],
                              format_func=lambda oid: next(o["obra"] for o in obras if o["id"] == oid))
    obra = next(o for o in obras if o["id"] == seleccionado)
    st.markdown("#### Expediente seleccionado")
    st.write(f"**{obra['obra']}** · {len(obra['documentos'])} documentos ficticios")
    if obra["documentos"]:
        st.dataframe(pd.DataFrame([{"Documento":d,"Tipo":"Sin clasificar","Estado":"Pendiente"}
                                 for d in obra["documentos"]]), hide_index=True, use_container_width=True)
    else:
        st.info("Esta obra no tiene documentos.")
    st.button("Analizar con IA", disabled=True, help="Se habilitará después de integrar Gemini.")

with tab2:
    st.subheader("Pruebas de adjudicación directa")
    st.info("El motor de auditoría se desarrollará después de la conexión documental y la extracción con Gemini.")
    pruebas = [
        ("AD-01", "Capital contable"),
        ("AD-02", "Especialidad del contratista"),
        ("AD-03", "Vigencia del PUC"),
        ("AD-04", "Responsable técnico"),
        ("AD-05", "Secuencia dictamen, notificación y contrato"),
    ]
    st.dataframe(pd.DataFrame([{"Clave":k,"Prueba":n,"Estado":"No implementada"}
                               for k,n in pruebas]), hide_index=True, use_container_width=True)

with tab3:
    st.subheader("Dashboard general")
    st.caption("Indicadores de la demostración, no resultados de auditoría.")
    df = pd.DataFrame([{"Obra":o["obra"],"Documentos":len(o["documentos"])} for o in obras])
    st.bar_chart(df.set_index("Obra")["Documentos"])
    st.dataframe(df, hide_index=True, use_container_width=True)
    st.download_button("Exportar muestra ficticia (CSV)", data=df.to_csv(index=False).encode("utf-8-sig"),
                       file_name="auditoria_demo.csv", mime="text/csv")

with tab4:
    render_drive_explorer(access_granted)

st.caption("AuditorIA · Primera entrega técnica · Conector Drive opcional, solo entorno autorizado")
