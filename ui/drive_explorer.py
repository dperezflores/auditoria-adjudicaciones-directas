"""Explorador protegido de Drive con sincronización persistente bajo demanda."""
from __future__ import annotations

import threading

import pandas as pd
import streamlit as st

from services.drive_service import create_drive_client, is_configured, scan_drive
from services.sheets_service import (
    create_sheets_client,
    storage_configured,
    sync_to_sheets,
)


@st.cache_resource
def _local_writer_lock() -> threading.Lock:
    """Serializa escrituras entre sesiones dentro de un SOLO proceso Streamlit."""
    return threading.Lock()


def render_drive_explorer(authenticated: bool) -> None:
    st.subheader("Google Drive · Explorador piloto")
    st.caption("Inventario de carpetas y metadatos PDF. Sin descargar archivos ni usar IA.")

    if not authenticated:
        st.warning("El explorador real requiere autenticación de Google activa.")
        return

    try:
        drive_ready = is_configured(st.secrets)
        storage_ready = storage_configured(st.secrets)
    except FileNotFoundError:
        drive_ready = storage_ready = False

    if not drive_ready:
        st.info("La conexión central a Google Drive todavía no se ha configurado.")
        return

    refresh = st.button("Actualizar Google Drive", type="primary", key="drive_refresh")
    if refresh:
        st.session_state.pop("sync_summary", None)
        st.session_state.pop("persistence_error", None)

    if refresh or "drive_inventory" not in st.session_state:
        try:
            with st.spinner("Consultando carpetas de Drive..."):
                service = create_drive_client(st.secrets["gcp_service_account"])
                inventory = scan_drive(service, st.secrets["drive"]["root_folder_id"])
                st.session_state.drive_inventory = inventory
                st.session_state.pop("drive_error", None)
            # Solamente el botón realiza escrituras. Abrir la pestaña
            # por primera vez consulta Drive sin alterar la hoja maestra.
            if refresh and storage_ready:
                try:
                    with _local_writer_lock():
                        sheets = create_sheets_client(st.secrets["gcp_service_account"])
                        result = sync_to_sheets(
                            sheets, st.secrets["storage"]["spreadsheet_id"], inventory
                        )
                    st.session_state.sync_summary = result
                except Exception:
                    # Si falla la base, conservar el inventario leído, pero
                    # avisar explícitamente que NO se guardó correctamente.
                    st.session_state.persistence_error = (
                        "Se pudo consultar Drive, pero no se confirmó el guardado "
                        "en Google Sheets. Verifica el ID de la hoja, los permisos "
                        "de Editor de la cuenta de servicio y los encabezados."
                    )
        except Exception:
            st.session_state.pop("drive_inventory", None)
            st.session_state.drive_error = (
                "No fue posible consultar Drive. Revisa que la cuenta de servicio "
                "tenga permiso Lector en la carpeta piloto y que los secretos "
                "de Streamlit estén correctos."
            )

    if st.session_state.get("drive_error"):
        st.error(st.session_state.drive_error)
        return

    if not storage_ready:
        st.warning(
            "Inventario no persistente: falta agregar [storage] spreadsheet_id "
            "a los secretos privados de Streamlit. Los PDF pueden visualizarse, "
            "pero todavía no se registran en la base maestra."
        )
    if st.session_state.get("persistence_error"):
        st.error(st.session_state.persistence_error)

    summary = st.session_state.get("sync_summary")
    if summary:
        st.success(
            "Sincronización guardada en Google Sheets. "
            f"Obras nuevas: {summary.new_works}; "
            f"PDF nuevos: {summary.new_pdfs}; "
            f"PDF modificados: {summary.modified_pdfs}; "
            f"PDF retirados: {summary.removed_pdfs}."
        )
        st.caption(
            f"Registro de sincronización: {summary.sync_id}. "
            "Los documentos existentes se actualizan por ID; no se duplican."
        )

    inventory = st.session_state.get("drive_inventory")
    if not inventory:
        st.info("Presiona Actualizar Google Drive para consultar el repositorio.")
        return

    a, b, c = st.columns(3)
    a.metric("Obras detectadas", len(inventory.works))
    b.metric("PDF encontrados", inventory.pdf_total)
    c.metric("Pendientes de extracción", inventory.pdf_total)
    st.caption(f"Carpeta: {inventory.root_name} · Última consulta UTC: {inventory.synced_at}")

    if not inventory.works:
        st.info("No se encontraron subcarpetas de obra en la carpeta seleccionada.")
        return

    st.dataframe(
        pd.DataFrame([
            {
                "Obra": work.name,
                "ID carpeta": work.id,
                "PDF": len(work.pdfs),
                "Estado": "Pendiente de análisis" if work.pdfs else "Sin PDF",
            }
            for work in inventory.works
        ]),
        hide_index=True,
        use_container_width=True,
    )
    work_ids = [work.id for work in inventory.works]
    work_names = {work.id: work.name for work in inventory.works}
    selected = st.selectbox("Expediente", work_ids, format_func=work_names.get, key="drive_work")
    work = next(record for record in inventory.works if record.id == selected)
    if not work.pdfs:
        st.info("El expediente todavía no contiene documentos PDF.")
        return

    st.dataframe(
        pd.DataFrame([
            {
                "Documento": doc.name,
                "ID archivo": doc.id,
                "Última modificación": doc.modified_time,
                "Huella MD5": doc.md5_checksum,
                "Estado": "Pendiente de análisis",
            }
            for doc in work.pdfs
        ]),
        hide_index=True,
        use_container_width=True,
    )
    st.caption(
        "La sincronización conserva metadatos. Gemini, caché de extracciones y "
        "pruebas de adjudicación directa se incorporarán en etapas posteriores."
    )
