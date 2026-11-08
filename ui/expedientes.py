"""Explorador operativo de obras y PDFs: seleccionar 1, varios o toda carpeta.

No hay carga a Gemini al navegar, listar carpetas o consultar resultados.
El análisis solamente inicia con confirmación y pulsación del usuario.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from services.analysis_catalog import (
    FileStatus, file_states, folder_states, load_status_tables,
)
from services.document_classifier import XLSX_MIME, guess_from_name
from services.contract_schema import ExtraccionContrato
from services.contract_v2 import ContractExtractionV2, FIELD_LABELS_V2, classify_cited_regime
from services.extraction_store_v2 import extract_or_reuse_v2
from services.document_analysis import GeneralAnalysis
from services.drive_service import (
    DriveInventory, DocumentRecord, WorkRecord, DriveConnectionError,
    DriveConfigurationError, MAX_PDF_BYTES, create_drive_client,
    download_verified_pdf, is_configured, scan_drive,
)
from services.extraction_store import (
    ExtractionStateError,
)
from services.gemini_service import DEFAULT_MODEL
from services.sheets_service import (
    create_sheets_client, storage_configured, sync_to_sheets,
)
from services.writer_lock import get_writer_lock


MAX_BATCH = 10


def _refresh_inventory() -> None:
    """Refrescar Drive y sincronizar base, sin IA y sin borrar historial."""
    drive = create_drive_client(st.secrets["gcp_service_account"])
    inventory = scan_drive(drive, st.secrets["drive"]["root_folder_id"])
    with get_writer_lock():
        sheets = create_sheets_client(st.secrets["gcp_service_account"])
        sync_to_sheets(sheets, st.secrets["storage"]["spreadsheet_id"], inventory)
    tables = load_status_tables(sheets, st.secrets["storage"]["spreadsheet_id"])
    st.session_state["ex_inventory"] = inventory
    st.session_state["ex_status_tables"] = tables
    st.session_state["ex_synced_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_data() -> bool:
    if st.button("Actualizar Google Drive", key="ex_refresh", type="primary"):
        try:
            with st.spinner("Actualizando carpetas, PDFs y estados desde Google Drive..."):
                _refresh_inventory()
            st.session_state.pop("ex_sync_error", None)
        except Exception:
            st.session_state["ex_sync_error"] = (
                "No se pudo completar la sincronización. Comprueba que la cuenta de "
                "servicio tenga permisos sobre la carpeta y Google Sheets."
            )
    if "ex_inventory" not in st.session_state:
        try:
            with st.spinner("Cargando expedientes autorizados..."):
                _refresh_inventory()
        except Exception:
            st.error(
                "No se pudieron cargar los expedientes. Comprueba la conexión "
                "a Drive y a la hoja maestra."
            )
            return False
    if st.session_state.get("ex_sync_error"):
        st.error(st.session_state["ex_sync_error"])
    return True


def _summarize_saved(
    document: DocumentRecord,
    tables: dict[str, list[dict[str, str]]],
    status: FileStatus,
) -> None:
    """Mostrar una lectura persistente; no llamar a Gemini."""
    rows = tables["Extracciones"]
    old = next((row for row in rows if row["cache_key"] == status.cache_key), None)
    if not old:
        st.info("Todavía no existe un resultado completo guardado para este archivo.")
        return
    if old["estado"] == "COMPLETADO" and old["resultado_json"]:
        if old["version_esquema"] == "documento-schema-v1":
            try:
                report = GeneralAnalysis.model_validate_json(old["resultado_json"])
                st.write(f"**Tipo identificado:** {report.tipo_documental}")
                st.write(f"**Resumen:** {report.resumen}")
                if report.campos:
                    st.dataframe(pd.DataFrame([
                        {"Dato": f.campo, "Valor": f.valor, "Página": f.pagina,
                         "Evidencia": f.evidencia or "Sin evidencia"}
                        for f in report.campos
                    ]), hide_index=True, use_container_width=True)
                if report.alertas:
                    st.write("**Cuestiones por verificar:**")
                    for alert in report.alertas:
                        st.write(f"• {alert}")
            except Exception:
                st.warning("La respuesta guardada no cumple el esquema documental actual.")
        elif old["version_esquema"] == "contrato-v2":
            try:
                result = ContractExtractionV2.model_validate_json(old["resultado_json"])
                st.dataframe(pd.DataFrame([
                    {
                        "Campo": label,
                        "Texto literal": getattr(result, name).valor or "No localizado",
                        "Página": getattr(result, name).pagina,
                        "Evidencia": getattr(result, name).evidencia or "Sin evidencia",
                    }
                    for name, label in FIELD_LABELS_V2
                ]), hide_index=True, use_container_width=True)
                if result.personas_participantes:
                    st.markdown("**Personas que participan en el contrato**")
                    st.dataframe(pd.DataFrame([
                        item.model_dump(mode="json")
                        for item in result.personas_participantes
                    ]), hide_index=True, use_container_width=True)
                st.caption(
                    "Ámbito normativo citado (clasificación preliminar): " +
                    classify_cited_regime(result.legislacion_citada.valor)
                )
            except Exception:
                st.warning("El registro contractual v2 no pudo interpretarse.")
        elif old["version_esquema"] == "contrato-v1":
            try:
                parsed = ExtraccionContrato.model_validate_json(old["resultado_json"])
                rows = []
                for field, item in parsed:
                    if field == "observaciones":
                        continue
                    rows.append({
                        "Dato": field.replace("_", " ").capitalize(),
                        "Valor": item.valor or "No localizado",
                        "Página": item.pagina,
                        "Evidencia": item.evidencia or "Sin evidencia",
                    })
                st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
                if parsed.observaciones:
                    st.caption("Advertencias: " + "; ".join(parsed.observaciones))
            except Exception:
                st.warning("El resultado estructurado no pudo interpretarse.")
        else:
            st.info("Existe un análisis persistente en otra versión de esquema.")
        st.caption("Datos extraídos automáticamente. No equivalen a comprobación ni dictamen.")
        return
    matches = [
        row for row in tables["DatosContrato"]
        if row["cache_key"] == status.cache_key
        and row["documento_id"] == document.id
    ]
    if matches:
        st.warning("Recuperación parcial: los valores carecen de página y evidencia guardadas.")
        cols = ["numero_contrato", "nombre_obra", "contratista", "fecha_firma",
                "fecha_inicio", "fecha_termino", "monto_con_iva", "porcentaje_anticipo"]
        st.dataframe(pd.DataFrame([
            {"Dato": name.replace("_", " ").capitalize(),
             "Valor": matches[0].get(name) or "No localizado",
             "Estado": "Sin evidencia conservada"}
            for name in cols
        ]), hide_index=True, use_container_width=True)


def _analyze(
    obra: WorkRecord, selection: list[DocumentRecord], model: str,
) -> list[dict[str, str]]:
    """Analiza secuencialmente con límite explícito de trabajo por sesión."""
    log = []
    bar = st.progress(0, text="Preparando análisis...")
    total = len(selection)
    for ix, doc in enumerate(selection, 1):
        bar.progress((ix - 1) / total, text=f"Documento {ix}/{total}: {doc.name}")
        stage = "drive"
        try:
            with get_writer_lock():
                drive = create_drive_client(st.secrets["gcp_service_account"])
                pdf = download_verified_pdf(drive, doc, obra.id)
                stage = "sheets"
                sheets = create_sheets_client(st.secrets["gcp_service_account"])
                stage = "analisis"
                result = extract_or_reuse_v2(
                    sheets, st.secrets["storage"]["spreadsheet_id"],
                    pdf, doc, obra.id, st.secrets["gemini"]["api_key"],
                    model=model,
                )
                reused = result.cached
            outcome = "Reutilizado (sin IA)" if reused else "Analizado y guardado"
            log.append({"Documento": doc.name, "Resultado": outcome})
        except (DriveConnectionError, DriveConfigurationError) as exc:
            log.append({
                "Documento": doc.name,
                "Resultado": f"Problema de lectura en Drive: {exc} No se envió a Gemini.",
            })
        except ExtractionStateError as exc:
            log.append({"Documento": doc.name, "Resultado": f"Análisis no confirmado: {str(exc)}"})
        except Exception:
            if stage == "drive":
                reason = (
                    "Error de acceso o descarga de Google Drive. No se envió "
                    "el PDF a Gemini. Verifica el acceso de lectura de la cuenta de servicio."
                )
            elif stage == "sheets":
                reason = (
                    "Error al conectar con Google Sheets. No se envió el PDF "
                    "a Gemini. Verifica los permisos de escritura."
                )
            else:
                reason = (
                    "Fallo durante el procesamiento o guardado. Consulta "
                    "Extracciones antes de volver a intentarlo."
                )
            log.append({"Documento": doc.name, "Resultado": reason})
        bar.progress(ix / total, text=f"Procesados {ix} de {total}")
    # Nuevo inventario de estados, solo lectura: nunca invoca Gemini.
    try:
        sheets = create_sheets_client(st.secrets["gcp_service_account"])
        st.session_state["ex_status_tables"] = load_status_tables(
            sheets, st.secrets["storage"]["spreadsheet_id"],
        )
    except Exception:
        log.append({
            "Documento": "Actualización de estados",
            "Resultado": "Consulta los registros en Sheets antes de repetir análisis.",
        })
    return log


def render_expedientes(authenticated: bool) -> None:
    st.title("Expedientes de obra")
    st.caption(
        "Explorador conectado a Google Drive · Etapa 1: clasificación documental sin IA"
    )
    if not authenticated:
        st.error("Se requiere iniciar sesión con una cuenta autorizada.")
        return
    if not is_configured(st.secrets) or not storage_configured(st.secrets):
        st.error("Falta configurar Drive o Google Sheets en Streamlit Secrets.")
        return
    if not _load_data():
        return

    inventory: DriveInventory = st.session_state["ex_inventory"]
    tables = st.session_state["ex_status_tables"]
    states = file_states(inventory, tables)
    folders = folder_states(inventory, states)
    pdf_total = inventory.pdf_total
    complete = sum(v.label == "Analizado" for v in states.values())
    partial = sum(v.label == "Parcial" for v in states.values())

    st.caption(
        f"Carpeta raíz: {inventory.root_name} · "
        f"Última sincronización: {st.session_state.get('ex_synced_at', 'Sin fecha')} UTC"
    )
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Carpetas", len(inventory.works))
    col2.metric("PDF registrados", pdf_total)
    col3.metric("Analizados con IA", complete)
    col4.metric("Pendientes o parciales", pdf_total - complete)

    if not inventory.works:
        st.info(
            "No hay carpetas de obra en el directorio autorizado. "
            "Compártelas con la cuenta de servicio y actualiza Drive."
        )
        return

    st.markdown("### Carpetas de obra")
    search = st.text_input(
        "Buscar carpeta o PDF",
        placeholder="Nombre de la obra, número de contrato, archivo...",
        key="ex_search",
    ).casefold().strip()
    filter_status = st.selectbox(
        "Filtrar estado", ["Todos", "Analizada", "Parcial", "Pendiente", "Revisar error", "Sin PDF"],
        key="ex_folder_filter",
    )
    visible = [
        work for work in inventory.works
        if (
            not search or search in work.name.casefold()
            or any(search in f.name.casefold() for f in work.pdfs)
        )
        and (filter_status == "Todos" or folders[work.id].label == filter_status)
    ]
    if not visible:
        st.info("No hay expedientes que coincidan con el filtro.")
    for work in visible:
        fs = folders[work.id]
        with st.expander(
            f"📁 {work.name}  ·  {fs.label}  ·  {fs.complete}/{fs.total} PDF analizados",
            expanded=len(visible) == 1,
        ):
            if not work.pdfs:
                st.caption("Esta carpeta no contiene PDF compatibles con el analizador.")
                if work.other_files:
                    st.dataframe(pd.DataFrame([
                        {
                            "Archivo": (doc.relative_path + "/" if doc.relative_path else "") + doc.name,
                            "Formato": doc.mime_type,
                            "Tipo documental": guess_from_name(doc.name, doc.mime_type).label,
                            "Estado": "Excel registrado · sin extractor" if doc.mime_type == XLSX_MIME
                            else "Formato no compatible",
                        }
                        for doc in work.other_files
                    ]), hide_index=True, use_container_width=True)
                continue
            st.dataframe(pd.DataFrame([
                {
                    "Archivo": (doc.relative_path + "/" if doc.relative_path else "") + doc.name,
                    "Tipo documental": guess_from_name(doc.name, doc.mime_type).label,
                    "Estado IA": states[doc.id].label,
                    "Actualizado": doc.modified_time,
                }
                for doc in work.pdfs
            ]), hide_index=True, use_container_width=True)
            if work.other_files:
                st.markdown("**Otros documentos detectados**")
                st.dataframe(pd.DataFrame([
                    {
                        "Archivo": (other.relative_path + "/" if other.relative_path else "") + other.name,
                        "Formato": other.mime_type,
                        "Tipo documental": guess_from_name(other.name, other.mime_type).label,
                        "Estado": (
                            "Excel registrado · extractor pendiente"
                            if other.mime_type == XLSX_MIME
                            else "Formato no compatible"
                        ),
                    }
                    for other in work.other_files
                ]), hide_index=True, use_container_width=True)
            st.caption(
                "El tipo documental se asigna automáticamente a partir del nombre "
                "estándar y la extensión, sin comprobar el contenido. "
                "Si aparece POR_IDENTIFICAR, renombra el archivo y actualiza Drive."
            )

    st.divider()
    st.markdown("### Extracción documental")
    st.info(
        "Etapa 1: los análisis nuevos están pausados mientras incorporamos "
        "los extractores propios de cada documento. Así evitamos que el PUC "
        "o el dictamen vuelvan a procesarse con los 16 campos del contrato."
    )
    ids = [work.id for work in inventory.works]
    label_by_id = {work.id: work.name for work in inventory.works}
    obra_id = st.selectbox(
        "Carpeta a trabajar", ids, format_func=label_by_id.get, key="ex_selected_folder"
    )
    obra = next(work for work in inventory.works if work.id == obra_id)
    if not obra.pdfs:
        st.info("Esta carpeta no contiene PDFs para analizar.")
        return
    doc_ids = [doc.id for doc in obra.pdfs]
    doc_names = {
        doc.id: (doc.relative_path + "/" if doc.relative_path else "") + doc.name
        for doc in obra.pdfs
    }
    mode = st.radio(
        "Alcance del análisis",
        ["Un archivo", "Varios archivos", "Carpeta completa"],
        horizontal=True,
        key="ex_scope",
    )
    if mode == "Un archivo":
        selected = [st.selectbox(
            "Seleccionar documento", doc_ids, format_func=doc_names.get,
            key=f"ex_single_{obra.id}",
        )]
    elif mode == "Varios archivos":
        selected = st.multiselect(
            "Documentos a analizar", doc_ids, format_func=doc_names.get,
            key=f"ex_multi_{obra.id}",
        )
    else:
        selected = doc_ids
        st.caption("Se seleccionarán todos los PDF de la carpeta.")

    chosen = [doc for doc in obra.pdfs if doc.id in selected]
    st.caption(
        f"Seleccionados: {len(chosen)} archivos · "
        f"Límite por ejecución: {MAX_BATCH} · PDF máximo: 50 MB"
    )
    if chosen:
        st.dataframe(pd.DataFrame([
            {
                "Archivo": d.name,
                "Tamaño (MB)": round(d.size_bytes / 1_000_000, 2) if d.size_bytes else None,
                "Estado actual": states[d.id].label,
                "Tipo documental": guess_from_name(d.name, d.mime_type).label,
                "Extractor": "Pendiente de activación por tipo",
                "Compatibilidad": (
                    "Listo" if 0 < d.size_bytes <= MAX_PDF_BYTES
                    else "Sin tamaño" if not d.size_bytes
                    else "Supera 50 MB"
                ),
            }
            for d in chosen
        ]), hide_index=True, use_container_width=True)

    # La aplicación reconoce trabajos anteriores y evita volver a enviarlos.
    # Una ficha "Parcial"/"Revisar error" tampoco se reintenta sin revisión.
    too_large = [doc for doc in chosen if doc.size_bytes > MAX_PDF_BYTES]
    unknown_size = [doc for doc in chosen if doc.size_bytes <= 0]
    if too_large:
        st.warning(
            f"{len(too_large)} PDF excede(n) el límite de 50 MB de Gemini "
            "y no se enviarán a la API. Reduce su tamaño o divide el documento."
        )
    if unknown_size:
        st.warning(
            f"{len(unknown_size)} PDF no informa(n) tamaño en Drive. "
            "Actualiza el inventario antes de analizarlos."
        )
    # La extracción v2 es la única modalidad desde esta interfaz.
    # Un PDF con v1 o ficha general se puede ampliar manualmente una vez,
    # pero un v2 completo se reutiliza y uno incierto nunca se reintenta.
    registered = {r["documento_id"]: r for r in tables["Documentos"]}
    extractions = {r["cache_key"]: r for r in tables["Extracciones"]}
    v2_attempts = {}
    for row in tables["Extracciones"]:
        if row["version_esquema"] == "contrato-v2":
            v2_attempts.setdefault(row["documento_id"], []).append(row)

    def is_current_v2(doc: DocumentRecord) -> bool:
        item = registered.get(doc.id)
        if not item or item["md5_checksum"] != doc.md5_checksum:
            return False
        result = extractions.get(item["resultado_id"])
        return bool(
            result
            and result["version_esquema"] == "contrato-v2"
            and result["estado"] == "COMPLETADO"
            and result["resultado_json"]
            and result["documento_id"] == doc.id
            and result["obra_id"] == obra.id
        )

    blocked_v2 = {
        doc.id for doc in chosen
        if any(
            row["estado"] in ("EN_PROCESO", "REQUIERE_REVISION")
            for row in v2_attempts.get(doc.id, [])
        )
    }
    to_process = []
    old_version_ready = []
    for doc in chosen:
        if not (0 < doc.size_bytes <= MAX_PDF_BYTES):
            continue
        current = states[doc.id].label
        if (
            doc.id in blocked_v2 or is_current_v2(doc)
            or current in ("Sin registrar", "Parcial", "Revisar error")
        ):
            continue
        if current in ("Pendiente", "Analizado", "Desactualizado"):
            to_process.append(doc)
            if current == "Analizado":
                old_version_ready.append(doc)

    if blocked_v2:
        st.warning(
            "Existe una solicitud de contrato v2 sin confirmar para "
            f"{len(blocked_v2)} archivo(s). No se repetirá automáticamente."
        )
    if old_version_ready:
        st.info(
            f"{len(old_version_ready)} documento(s) tienen una extracción anterior. "
            "Al pulsar Analizar se obtendrán los 16 campos con la nueva versión "
            "y se conservará el resultado histórico. Esto puede generar consumo "
            "solo si no existe ya una extracción v2 reutilizable."
        )
    batch = to_process[:MAX_BATCH] if mode == "Carpeta completa" else to_process
    if mode == "Carpeta completa" and len(to_process) > MAX_BATCH:
        st.info(
            f"La carpeta contiene {len(to_process)} PDF por procesar. "
            f"Esta ejecución analizará los primeros {MAX_BATCH}; "
            "podrás repetir para continuar con los siguientes."
        )
    skips = sum(
        0 < d.size_bytes <= MAX_PDF_BYTES and d.id not in {x.id for x in to_process}
        for d in chosen
    )
    if skips:
        st.info(
            f"{skips} archivo(s) ya analizado(s), parcial(es) o con incidencia "
            "serán omitidos para evitar repetir solicitudes y cargos."
        )
    if any(states[d.id].label == "Sin registrar" for d in to_process):
        st.warning("Hay documentos sin registrar: primero presiona Actualizar Google Drive.")

    gemini = st.secrets.get("gemini", {})
    api_key = gemini.get("api_key", "")
    model = gemini.get("model") or DEFAULT_MODEL
    st.caption(f"Modelo disponible para etapas posteriores: {model}")
    # Por seguridad, deshabilitar el extractor único de contratos mientras
    # se implementan los esquemas PUC/DICTAMEN/NOTIFICACION específicos.
    # No se envía ningún PDF a Gemini durante esta etapa.
    disabled = True
    if st.button(
        f"Analizar {len(batch)} documento(s) con IA",
        type="primary", disabled=disabled, key="ex_analyze",
    ):
        st.session_state["ex_last_run"] = _analyze(obra, batch, model)
        st.rerun()

    if st.session_state.get("ex_last_run"):
        st.markdown("#### Resultado de la última ejecución")
        st.dataframe(
            pd.DataFrame(st.session_state["ex_last_run"]),
            hide_index=True, use_container_width=True,
        )

    st.divider()
    st.markdown("### Consultar análisis guardado")
    preview_id = st.selectbox(
        "Documento",
        doc_ids, format_func=doc_names.get, key=f"ex_preview_{obra.id}",
    )
    preview = next(d for d in obra.pdfs if d.id == preview_id)
    current_state = file_states(inventory, st.session_state["ex_status_tables"])[preview.id]
    st.write(f"**Estado:** {current_state.label} · {current_state.detail}")
    _summarize_saved(preview, st.session_state["ex_status_tables"], current_state)
    if re.fullmatch(r"[A-Za-z0-9_-]{10,}", preview.id):
        st.link_button(
            "Ver PDF en Drive",
            f"https://drive.google.com/file/d/{preview.id}/view",
        )
