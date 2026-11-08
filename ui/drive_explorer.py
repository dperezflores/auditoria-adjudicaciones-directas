"""Explorador protegido de Drive con sincronización persistente bajo demanda."""
from __future__ import annotations

import threading

import pandas as pd
import streamlit as st

from services.drive_service import (
    create_drive_client, download_verified_pdf, is_configured, scan_drive,
)
from services.sheets_service import (
    create_sheets_client,
    storage_configured,
    sync_to_sheets,
)
from services.extraction_store import ExtractionStateError, extract_or_reuse
from services.gemini_service import DEFAULT_MODEL


@st.cache_resource
def _local_writer_lock() -> threading.Lock:
    """Serializa escrituras entre sesiones dentro de un SOLO proceso Streamlit."""
    return threading.Lock()


def render_drive_explorer(authenticated: bool) -> None:
    st.subheader("Google Drive · Explorador piloto")
    st.caption("La actualización solo consulta metadatos. Descargar y analizar PDF exige confirmación explícita.")

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
    st.divider()
    st.markdown("#### Extracción de datos del contrato con Gemini")
    st.caption(
        "Etapa piloto: exclusivamente el contrato simulado. "
        "La API solo se invoca al confirmar el análisis."
    )
    if not storage_ready:
        st.warning("Primero configura la hoja maestra de Google Sheets.")
        return

    document_ids = [d.id for d in work.pdfs]
    names = {d.id: d.name for d in work.pdfs}
    selected_pdf = st.selectbox(
        "PDF que deseas analizar",
        document_ids, format_func=names.get, key=f"analysis_doc_{work.id}",
    )
    document = next(d for d in work.pdfs if d.id == selected_pdf)

    # Restricción explícita durante las pruebas: ningún expediente real
    # u otro PDF de Drive se enviará a Gemini en esta fase.
    allowed_demo_id = "1zGZjRXxLtaNmmMW-0kGOU9W6m7Wr1YA2"
    is_demo_document = (
        document.id == allowed_demo_id
        and document.name.startswith("Contrato_SIMULADO_")
    )
    gemini_conf = st.secrets.get("gemini", {})
    api_key = gemini_conf.get("api_key", "")
    model = gemini_conf.get("model", DEFAULT_MODEL)
    if not isinstance(model, str) or not model.strip():
        st.error("Configura un modelo válido para Gemini.")
        return
    st.caption(f"Modelo configurado: {model}")
    if not api_key:
        st.warning("Falta [gemini] api_key en Streamlit Secrets.")
    if not is_demo_document:
        st.info("Solo está habilitado el contrato completamente ficticio del piloto.")
    confirmation = st.checkbox(
        "Confirmo que este documento es ficticio y autorizo una solicitud "
        "a Gemini, que podría generar consumo o cargos.",
        key="gemini_approval",
    )
    retry = st.checkbox(
        "Autorizar reintento explícito si existe una solicitud incompleta "
        "(podría generar un cargo adicional).",
        key="gemini_retry",
    )
    execute = st.button(
        "Analizar contrato con IA (o reutilizar caché)",
        key="gemini_contract_run",
        disabled=not (api_key and is_demo_document and confirmation),
        type="primary",
    )
    if execute:
        st.session_state.pop("extraction_display", None)
        try:
            with st.spinner("Comprobando PDF, caché y extracción..."):
                with _local_writer_lock():
                    client = create_drive_client(st.secrets["gcp_service_account"])
                    pdf_bytes = download_verified_pdf(client, document, work.id)
                    sheets_client = create_sheets_client(st.secrets["gcp_service_account"])
                    outcome = extract_or_reuse(
                        sheets_client, st.secrets["storage"]["spreadsheet_id"],
                        pdf_bytes, document, work.id, api_key,
                        model=model, allow_retry=retry,
                    )
            st.session_state.extraction_display = {
                "document_id": document.id,
                "md5": document.md5_checksum,
                "result": outcome,
            }
        except ExtractionStateError as exc:
            st.error(str(exc))
        except Exception:
            st.error(
                "No fue posible completar la lectura del PDF. "
                "Comprueba que siga en Drive, con los mismos metadatos, "
                "y consulta el estado de la hoja Extracciones."
            )

    display = st.session_state.get("extraction_display")
    if display and display["document_id"] == document.id and display["md5"] == document.md5_checksum:
        outcome = display["result"]
        if outcome.cached:
            st.success("Resultado recuperado de Google Sheets: sin una nueva llamada a Gemini.")
        else:
            st.success("Resultado de Gemini guardado en Google Sheets.")
        st.caption(
            f"Clave de caché: {outcome.cache.clave[:16]}… "
            f"· Entradas: {outcome.input_tokens if outcome.input_tokens is not None else 'N/D'} "
            f"tokens · Salidas: {outcome.output_tokens if outcome.output_tokens is not None else 'N/D'} tokens"
        )
        fields = [
            ("Número de contrato", "numero_contrato"),
            ("Nombre de la obra", "nombre_obra"),
            ("Contratista", "contratista"),
            ("Fecha de firma", "fecha_firma"),
            ("Fecha de inicio", "fecha_inicio"),
            ("Fecha de término", "fecha_termino"),
            ("Monto con IVA", "monto_con_iva"),
            ("Anticipo", "porcentaje_anticipo"),
        ]
        st.dataframe(
            pd.DataFrame([
                {
                    "Dato": label,
                    "Valor extraído": getattr(outcome.extraction, key).valor or "No localizado",
                    "Página": getattr(outcome.extraction, key).pagina,
                    "Evidencia": getattr(outcome.extraction, key).evidencia or "Sin evidencia",
                    "Revisar": (
                        "Sí" if (
                            getattr(outcome.extraction, key).requiere_revision
                            or getattr(outcome.extraction, key).valor is None
                        ) else "Cotejar"
                    ),
                }
                for label, key in fields
            ]),
            hide_index=True, use_container_width=True,
        )
        if outcome.extraction.observaciones:
            st.write("**Advertencias de la extracción:**")
            for note in outcome.extraction.observaciones:
                st.write(note)
        st.warning(
            "La extracción es preliminar. La página y el fragmento de evidencia "
            "proceden de la IA y deben cotejarse visualmente con el PDF; "
            "no constituyen pruebas de auditoría verificadas."
        )
