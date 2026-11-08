"""Dashboard del piloto con solo lectura de Sheets y estado de cotejo."""
from __future__ import annotations

from datetime import datetime, timezone
import pandas as pd
import streamlit as st

from services.dashboard_service import DashboardDataError, read_dashboard
from services.sheets_service import create_sheets_client, storage_configured

_LABELS = (
    ("Número de contrato", "numero_contrato"),
    ("Nombre de obra", "nombre_obra"),
    ("Contratista", "contratista"),
    ("Fecha de firma", "fecha_firma"),
    ("Fecha de inicio", "fecha_inicio"),
    ("Fecha de término", "fecha_termino"),
    ("Monto con IVA", "monto_con_iva"),
    ("Porcentaje de anticipo", "porcentaje_anticipo"),
)


def render_live_dashboard(authenticated: bool) -> None:
    """Muestra datos almacenados, no procesa documentos ni llama a Gemini."""
    st.subheader("Seguimiento del piloto · Google Sheets")
    st.caption(
        "Datos del registro persistente; las obras y documentos de este "
        "ensayo son ficticios. Sin solicitudes de IA."
    )
    if not authenticated:
        st.info("Inicia sesión con una cuenta autorizada para ver el registro.")
        return

    if not storage_configured(st.secrets):
        st.info("Falta configurar la hoja maestra en los secretos de Streamlit.")
        return

    if st.button(
        "Actualizar indicadores desde Google Sheets",
        key="dashboard_live_refresh",
        type="primary",
    ):
        st.session_state.pop("dashboard_live_error", None)
        try:
            with st.spinner("Leyendo registros guardados en Google Sheets..."):
                client = create_sheets_client(st.secrets["gcp_service_account"])
                data = read_dashboard(
                    client, st.secrets["storage"]["spreadsheet_id"],
                )
            st.session_state["dashboard_live_snapshot"] = data
            st.session_state["dashboard_live_updated"] = (
                datetime.now(timezone.utc).isoformat(timespec="seconds")
            )
        except DashboardDataError:
            st.session_state.pop("dashboard_live_snapshot", None)
            st.session_state["dashboard_live_error"] = (
                "La estructura de la hoja maestra no es compatible "
                "o contiene registros inconsistentes. No se modificó ningún dato."
            )
        except Exception:
            st.session_state.pop("dashboard_live_snapshot", None)
            st.session_state["dashboard_live_error"] = (
                "No fue posible leer los datos desde Google Sheets. "
                "Revisa los permisos y vuelve a consultar."
            )

    if st.session_state.get("dashboard_live_error"):
        st.error(st.session_state["dashboard_live_error"])
        return

    snapshot = st.session_state.get("dashboard_live_snapshot")
    if snapshot is None:
        st.info("Pulsa Actualizar indicadores para cargar la información registrada.")
        return

    st.caption(
        "Última lectura UTC: "
        + st.session_state.get("dashboard_live_updated", "No disponible")
    )
    a, b, c, d = st.columns(4)
    a.metric("Obras activas", len(snapshot.obras))
    b.metric("PDF activos", snapshot.pdf_activos)
    c.metric("Contratos con datos", snapshot.contratos_con_datos)
    d.metric("Pendientes de cotejo", snapshot.contratos_pendientes_cotejo)

    if not snapshot.obras:
        st.info("No existen obras activas en el registro.")
        return

    st.dataframe(
        pd.DataFrame([
            {
                "Obra (nombre de carpeta)": work.nombre,
                "PDF activos": work.pdf_activos,
                "Contratos con valores": work.contratos_recuperados,
                "Por cotejar": work.pendientes_cotejo,
            }
            for work in snapshot.obras
        ]),
        hide_index=True,
        use_container_width=True,
    )
    st.caption(
        "Un contrato 'con datos' indica extracción almacenada; "
        "NO significa validación documental ni cumplimiento normativo."
    )
    ids = [work.obra_id for work in snapshot.obras]
    titles = {work.obra_id: work.nombre for work in snapshot.obras}
    selected = st.selectbox(
        "Consultar obra registrada",
        ids,
        format_func=titles.get,
        key="dashboard_selected_work",
    )

    selected_contracts = [
        contract for contract in snapshot.contratos
        if contract.obra_id == selected
    ]
    if not selected_contracts:
        st.info("Esta obra todavía no tiene datos de contrato recuperables.")
        return

    for contract in selected_contracts:
        st.markdown(f"**Documento:** {contract.nombre_documento}")
        st.warning(f"**Estado:** {contract.estado}. {contract.detalle}")
        st.dataframe(
            pd.DataFrame([
                {
                    "Campo": label,
                    "Valor registrado": contract.datos.get(key) or "No localizado",
                    "Revisión": "Pendiente de cotejo con PDF",
                }
                for label, key in _LABELS
            ]),
            hide_index=True,
            use_container_width=True,
        )
        st.caption(
            "Las páginas, citas y la aprobación humana todavía no se "
            "encuentran registradas. Los valores no son observaciones de auditoría."
        )
