"""Consulta simple de resultados guardados, sin cotejo manual obligatorio."""
from __future__ import annotations

from datetime import datetime, timezone
import pandas as pd
import streamlit as st

from services.analysis_catalog import file_states, folder_states, load_status_tables
from services.drive_service import create_drive_client, scan_drive
from services.sheets_service import create_sheets_client
from ui.expedientes import _summarize_saved


def render_results() -> None:
    st.title("Resultados documentales")
    st.caption(
        "Análisis de Gemini conservados en Google Sheets. "
        "Un resultado de IA no constituye un dictamen ni un hallazgo confirmado."
    )
    if st.button("Actualizar resultados", type="primary", key="result_refresh"):
        try:
            with st.spinner("Leyendo los expedientes y sus registros..."):
                drive = create_drive_client(st.secrets["gcp_service_account"])
                inventory = scan_drive(drive, st.secrets["drive"]["root_folder_id"])
                sheets = create_sheets_client(st.secrets["gcp_service_account"])
                tables = load_status_tables(
                    sheets, st.secrets["storage"]["spreadsheet_id"]
                )
                st.session_state["res_snapshot"] = (inventory, tables)
                st.session_state["res_updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            st.session_state.pop("res_error", None)
        except Exception:
            st.session_state["res_error"] = (
                "No fue posible consultar resultados. Comprueba Drive y Sheets."
            )
    if st.session_state.get("res_error"):
        st.error(st.session_state["res_error"])
        return
    if not st.session_state.get("res_snapshot"):
        st.info("Presiona Actualizar resultados para consultar la información guardada.")
        return
    inventory, tables = st.session_state["res_snapshot"]
    states = file_states(inventory, tables)
    folders = folder_states(inventory, states)

    one, two, three = st.columns(3)
    one.metric("Obras", len(inventory.works))
    two.metric("Archivos analizados", sum(s.label == "Analizado" for s in states.values()))
    three.metric("Archivos pendientes", sum(s.label != "Analizado" for s in states.values()))

    st.dataframe(pd.DataFrame([
        {"Expediente": w.name, "PDF": len(w.pdfs),
         "Analizados": folders[w.id].complete, "Estado": folders[w.id].label}
        for w in inventory.works
    ]), hide_index=True, use_container_width=True)
    if not inventory.works:
        return
    works = {w.id: w for w in inventory.works}
    chosen = st.selectbox(
        "Expediente", list(works), format_func=lambda wid: works[wid].name,
        key="res_work",
    )
    work = works[chosen]
    if not work.pdfs:
        st.info("Sin PDF en este expediente.")
        return
    docs = {f.id: f for f in work.pdfs}
    doc_id = st.selectbox(
        "Documento", list(docs), format_func=lambda fid: docs[fid].name,
        key=f"res_doc_{chosen}",
    )
    doc = docs[doc_id]
    state = states[doc_id]
    st.markdown(f"**Estado de IA:** {state.label}")
    st.caption(state.detail)
    st.link_button(
        "Ver documento en Google Drive",
        f"https://drive.google.com/file/d/{doc.id}/view",
    )
    _summarize_saved(doc, tables, state)
