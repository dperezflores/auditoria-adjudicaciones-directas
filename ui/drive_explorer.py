"""Pestaña Drive, separada de la demostración y protegida por login."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from services.drive_service import (
    create_drive_client,
    is_configured,
    scan_drive,
)


def render_drive_explorer(authenticated: bool) -> None:
    st.subheader("Google Drive · Explorador piloto")
    st.caption("Consulta de carpetas y metadatos PDF. Sin descargar archivos ni usar IA.")

    if not authenticated:
        st.warning("El explorador real requiere autenticación de Google activa.")
        return

    try:
        ready = is_configured(st.secrets)
    except FileNotFoundError:
        ready = False

    if not ready:
        st.info(
            "La conexión central a Drive aún no se ha configurado. "
            "Prepararemos una cuenta de servicio de solo lectura y sus secretos de Streamlit."
        )
        return

    refresh = st.button("Actualizar Google Drive", type="primary", key="drive_refresh")
    if refresh or "drive_inventory" not in st.session_state:
        try:
            with st.spinner("Consultando carpetas de Drive..."):
                service = create_drive_client(st.secrets["gcp_service_account"])
                st.session_state.drive_inventory = scan_drive(
                    service, st.secrets["drive"]["root_folder_id"]
                )
                st.session_state.pop("drive_error", None)
        except Exception:
            # No revelar respuestas internas que pudieran contener datos privados.
            st.session_state.pop("drive_inventory", None)
            st.session_state.drive_error = (
                "No fue posible consultar Drive. Revisa que la cuenta de servicio "
                "tenga permiso Lector en la carpeta piloto y que los secretos "
                "de Streamlit estén correctos."
            )

    if st.session_state.get("drive_error"):
        st.error(st.session_state.drive_error)
        return

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
        "Esta etapa solo identifica los documentos. El análisis con Gemini y "
        "el registro persistente se habilitarán en fases posteriores."
    )
