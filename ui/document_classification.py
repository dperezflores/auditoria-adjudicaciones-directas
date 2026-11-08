"""Verificación del tipo documental desde Drive, sin Gemini.

Solo confirma y guarda el código si el contenido realmente presenta señales
del documento. Los PDF escaneados sin texto quedan como pendientes.
"""
from __future__ import annotations

import streamlit as st

from services.classification_store import ClassificationStoreError, save_confirmed_type
from services.document_classifier import XLSX_MIME, guess_from_name, classify_pdf, classify_xlsx
from services.drive_service import (
    DriveConfigurationError, DriveConnectionError, DriveInventory,
    create_drive_client, download_verified_pdf, download_verified_xlsx,
)
from services.analysis_catalog import load_status_tables
from services.sheets_service import create_sheets_client
from services.writer_lock import get_writer_lock


def render_classification(inventory: DriveInventory) -> None:
    st.divider()
    st.markdown("### Identificación documental")
    st.caption(
        "Etapa 1: CONTRATO, PUC, CATALOGO, DICTAMEN_AD, NOTIFICACION_AD y "
        "ORDEN_AD. El nombre solo sugiere el código; verificar el contenido "
        "no llama a Gemini ni realiza pruebas de auditoría."
    )
    choices = {w.id: w for w in inventory.works}
    if not choices:
        return
    work_id = st.selectbox(
        "Obra para identificar documentos",
        list(choices), format_func=lambda key: choices[key].name,
        key="ex_classify_work",
    )
    work = choices[work_id]
    files = [
        *work.pdfs,
        *(file for file in work.other_files if file.mime_type == XLSX_MIME),
    ]
    if not files:
        st.info("No hay PDF ni XLSX admitidos en esta obra.")
        return
    docs = {file.id: file for file in files}
    file_id = st.selectbox(
        "Documento a verificar",
        list(docs),
        format_func=lambda key: docs[key].name,
        key=f"ex_classify_file_{work_id}",
    )
    doc = docs[file_id]
    guess = guess_from_name(doc.name, doc.mime_type)
    rows = st.session_state["ex_status_tables"]["Documentos"]
    registered = next((r for r in rows if r["documento_id"] == doc.id), None)
    stored = registered["tipo_documental"] if registered else ""
    st.write(
        f"**Código registrado:** {stored or 'No confirmado'} · "
        f"**Sugerencia por nombre:** {guess.label}"
    )
    if stored:
        st.success("Código registrado en Google Sheets para esta versión del documento.")
    else:
        st.caption("El nombre por sí solo no confirma la naturaleza del documento.")

    if st.button("Verificar tipo por contenido (sin IA)", key="ex_verify_type"):
        try:
            with st.spinner("Leyendo el archivo desde Drive, sin Gemini..."):
                drive = create_drive_client(st.secrets["gcp_service_account"])
                if doc.mime_type == XLSX_MIME:
                    data = download_verified_xlsx(drive, doc, work.id)
                    report = classify_xlsx(data, doc.name)
                else:
                    data = download_verified_pdf(drive, doc, work.id)
                    report = classify_pdf(data, doc.name)
                if report.confirmed:
                    with get_writer_lock():
                        sheets = create_sheets_client(st.secrets["gcp_service_account"])
                        save_confirmed_type(
                            sheets, st.secrets["storage"]["spreadsheet_id"],
                            doc, work.id, report,
                        )
                        st.session_state["ex_status_tables"] = load_status_tables(
                            sheets, st.secrets["storage"]["spreadsheet_id"],
                        )
            st.session_state["ex_last_type_check"] = (
                doc.id, doc.md5_checksum, report,
            )
        except (DriveConnectionError, DriveConfigurationError, ClassificationStoreError) as exc:
            st.error("La clasificación no se confirmó: " + str(exc))
        except Exception:
            st.error(
                "Falló la verificación o el guardado del código. "
                "Consulta Google Drive y Sheets antes de repetir."
            )

    last = st.session_state.get("ex_last_type_check")
    if last and last[0] == doc.id and last[1] == doc.md5_checksum:
        report = last[2]
        if report.confirmed:
            st.success(f"{report.label} · {report.detail}")
        else:
            st.warning(f"{report.status}: {report.detail}")
    st.caption(
        "Solo se guardan códigos confirmados por contenido legible. "
        "Si un PDF es escaneado o su encabezado es ambiguo, quedará pendiente; "
        "no se adivinará su tipo documental."
    )
