"""Explorador operativo de obras y PDFs: seleccionar 1, varios o toda carpeta.

No hay carga a Gemini al navegar, listar carpetas o consultar resultados.
El análisis se solicita únicamente al pulsar el botón habilitado del extractor.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from services.analysis_catalog import (
    FileStatus, file_states, folder_states, load_status_tables,
)
from services.document_classifier import XLSX_MIME, guess_from_name, code_from_filename
from services.contract_schema import ExtraccionContrato
from services.contract_v2 import ContractExtractionV2, FIELD_LABELS_V2, classify_cited_regime
from services.puc_schema import PUC_LABELS, PucExtractionV1
from services.puc_store import extract_or_reuse_puc
from services.dictamen_schema import DICTAMEN_LABELS, DictamenAdV1
from services.dictamen_store import extract_or_reuse_dictamen
from services.notificacion_schema import NOTIFICACION_LABELS, NotificacionAdV1
from services.notificacion_store import extract_or_reuse_notificacion
from services.orden_schema import ORDEN_LABELS, OrdenAdV1
from services.orden_store import extract_or_reuse_orden
from services.analysis_deletion import delete_analysis
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
# Solo estos extractores especializados están autorizados actualmente.
ENABLED_EXTRACTORS = {
    "PUC": "puc-v1",
    "DICTAMEN_AD": "dictamen-ad-v1",
    "NOTIFICACION_AD": "notificacion-ad-v1",
    "ORDEN_AD": "orden-ad-v1",
}


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
        elif old["version_esquema"] == "puc-v1":
            try:
                report = PucExtractionV1.model_validate_json(old["resultado_json"])
                st.markdown("#### Datos extraídos del PUC")
                st.dataframe(pd.DataFrame([
                    {
                        "Campo": label,
                        "Texto literal": getattr(report, field).valor or "No localizado",
                        "Página": getattr(report, field).pagina,
                        "Evidencia": getattr(report, field).evidencia or "Sin evidencia",
                    }
                    for field, label in PUC_LABELS
                ]), hide_index=True, use_container_width=True)
                st.markdown("#### Especialidades registradas")
                if report.especialidades:
                    st.dataframe(pd.DataFrame([
                        {
                            "Categoría": item.categoria or "—",
                            "Actividad": item.actividad or "—",
                            "Tipo marcado": item.tipo_marcado or "—",
                            "Aportada por": item.aportada_por or "—",
                            "Página": item.pagina,
                            "Evidencia": item.evidencia or "Sin evidencia",
                        }
                        for item in report.especialidades
                    ]), hide_index=True, use_container_width=True)
                else:
                    st.info("No se identificaron especialidades en la extracción.")
                if report.observaciones:
                    with st.expander("Advertencias documentales de la extracción"):
                        for observation in report.observaciones:
                            st.write("• " + observation)
                st.caption(
                    "Los valores son transcripciones de Gemini, no resultados "
                    "de las pruebas de capital, especialidad o vigencia."
                )
            except Exception:
                st.warning("La extracción PUC guardada no pudo interpretarse.")
        elif old["version_esquema"] == "dictamen-ad-v1":
            try:
                report = DictamenAdV1.model_validate_json(old["resultado_json"])
                st.markdown("#### Datos extraídos del dictamen de adjudicación directa")
                st.dataframe(pd.DataFrame([
                    {
                        "Campo": label,
                        "Texto literal": getattr(report, key).valor or "No localizado",
                        "Página": getattr(report, key).pagina,
                        "Evidencia": getattr(report, key).evidencia or "Sin evidencia",
                    }
                    for key, label in DICTAMEN_LABELS
                ]), hide_index=True, use_container_width=True)
                st.markdown("#### Fundamentos jurídicos citados")
                if report.fundamentos:
                    st.dataframe(pd.DataFrame([
                        {
                            "Norma": x.norma or "—", "Artículos": x.articulos or "—",
                            "Texto citado": x.texto_citado or "—",
                            "Página": x.pagina, "Evidencia": x.evidencia or "—",
                        } for x in report.fundamentos
                    ]), hide_index=True, use_container_width=True)
                else:
                    st.info("No se extrajeron fundamentos jurídicos legibles.")
                st.markdown("#### Motivación y justificación expresadas en el dictamen")
                if report.motivaciones:
                    st.dataframe(pd.DataFrame([
                        {
                            "Tema": x.tema,
                            "Afirmación literal": x.afirmacion,
                            "Soporte mencionado": x.soporte_mencionado or "No mencionado",
                            "Página": x.pagina, "Evidencia": x.evidencia or "—",
                        } for x in report.motivaciones
                    ]), hide_index=True, use_container_width=True)
                else:
                    st.info("No se extrajeron afirmaciones motivacionales.")
                with st.expander("Documentos de soporte citados"):
                    if report.soportes:
                        st.dataframe(pd.DataFrame([
                            {
                                "Documento": x.documento,
                                "Finalidad citada": x.finalidad_citada or "—",
                                "Página": x.pagina,
                                "Evidencia": x.evidencia or "—",
                            } for x in report.soportes
                        ]), hide_index=True, use_container_width=True)
                    else:
                        st.info("No se identificaron soportes documentales expresamente citados.")
                st.caption(
                    "Firma aparente (apreciación visual no autenticada): "
                    f"{report.firma_aparente.presencia}. "
                    f"{report.firma_aparente.nota_visual or ''}"
                )
                if report.observaciones:
                    with st.expander("Advertencias de extracción"):
                        for note in report.observaciones:
                            st.write("• " + note)
                st.caption(
                    "Las afirmaciones y citas fueron extraídas del dictamen. "
                    "No demuestran por sí mismas el cumplimiento del procedimiento."
                )
            except Exception:
                st.warning("El dictamen guardado no pudo interpretarse con el esquema v1.")
        elif old["version_esquema"] == "notificacion-ad-v1":
            try:
                report = NotificacionAdV1.model_validate_json(old["resultado_json"])
                st.markdown("#### Datos extraídos de la notificación de adjudicación")
                st.dataframe(pd.DataFrame([
                    {
                        "Campo": label,
                        "Texto literal": getattr(report, key).valor or "No localizado",
                        "Página": getattr(report, key).pagina,
                        "Evidencia": getattr(report, key).evidencia or "Sin evidencia",
                    }
                    for key, label in NOTIFICACION_LABELS
                ]), hide_index=True, use_container_width=True)

                st.markdown("#### Personal designado en la notificación")
                if report.supervisores:
                    st.dataframe(pd.DataFrame([
                        {
                            "Función": x.funcion,
                            "Nombre": x.nombre,
                            "Cargo": x.cargo or "—",
                            "PUC del supervisor": x.registro_puc or "—",
                            "Página": x.pagina,
                            "Evidencia": x.evidencia or "—",
                        } for x in report.supervisores
                    ]), hide_index=True, use_container_width=True)
                else:
                    st.info("No se identificaron supervisores o coordinadores.")

                st.markdown("#### Obligaciones y plazos comunicados")
                if report.obligaciones:
                    st.dataframe(pd.DataFrame([
                        {
                            "Obligación literal": x.obligacion,
                            "Plazo literal": x.plazo_literal or "No indicado",
                            "Inicio del plazo": x.evento_inicio_plazo or "No indicado",
                            "Condición": x.condicion or "—",
                            "Destinatario": x.destinatario or "—",
                            "Fundamento citado": x.fundamento_citado or "—",
                            "Página": x.pagina, "Evidencia": x.evidencia or "—",
                        } for x in report.obligaciones
                    ]), hide_index=True, use_container_width=True)
                else:
                    st.info("No se extrajeron obligaciones expresas.")

                with st.expander("Fundamentos jurídicos citados"):
                    if report.fundamentos:
                        st.dataframe(pd.DataFrame([
                            {
                                "Norma": x.norma or "—",
                                "Artículos": x.articulos or "—",
                                "Página": x.pagina,
                                "Evidencia": x.evidencia or "—",
                            } for x in report.fundamentos
                        ]), hide_index=True, use_container_width=True)
                    else:
                        st.info("No se extrajeron fundamentos expresos.")
                acuse = report.acuse_aparente
                st.markdown("#### Acuse aparente")
                st.write(
                    f"**Presencia:** {acuse.presencia} · "
                    f"**Fecha de recepción legible:** {acuse.fecha_legible or 'No localizada'}"
                )
                st.caption(acuse.nota_visual or "Sin nota visual adicional")
                if report.observaciones:
                    with st.expander("Advertencias documentales"):
                        for note in report.observaciones:
                            st.write("• " + note)
                st.caption(
                    "La fecha de emisión no sustituye a la de recepción. "
                    "No se calculan fechas límite ni se verifica cumplimiento."
                )
            except Exception:
                st.warning(
                    "La notificación guardada no pudo interpretarse con el esquema v1."
                )
        elif old["version_esquema"] == "orden-ad-v1":
            try:
                report = OrdenAdV1.model_validate_json(old["resultado_json"])
                st.markdown("#### Datos extraídos de la orden de adjudicación")
                st.dataframe(pd.DataFrame([
                    {
                        "Campo": label,
                        "Texto literal": getattr(report, key).valor or "No localizado",
                        "Página": getattr(report, key).pagina,
                        "Evidencia": getattr(report, key).evidencia or "Sin evidencia",
                    }
                    for key, label in ORDEN_LABELS
                ]), hide_index=True, use_container_width=True)

                st.markdown("#### Personal de supervisión y coordinación mencionado")
                if report.personal_designado:
                    st.dataframe(pd.DataFrame([
                        {
                            "Nombre": x.nombre,
                            "Función literal": x.funcion or "—",
                            "Dirección": x.direccion or "—",
                            "Teléfono": x.telefono or "—",
                            "Página": x.pagina,
                            "Evidencia": x.evidencia or "—",
                        } for x in report.personal_designado
                    ]), hide_index=True, use_container_width=True)
                else:
                    st.info("No se identificó personal designado en la orden.")

                st.markdown("#### Instrucciones, condiciones y plazos")
                if report.instrucciones:
                    st.dataframe(pd.DataFrame([
                        {
                            "Instrucción literal": x.obligacion,
                            "Plazo literal": x.plazo_literal or "No indicado",
                            "Inicio del plazo": x.evento_inicio_plazo or "No indicado",
                            "Condición": x.condicion or "—",
                            "Consecuencia": x.consecuencia_literal or "—",
                            "Destinatario": x.destinatario or "—",
                            "Página": x.pagina,
                            "Evidencia": x.evidencia or "—",
                        } for x in report.instrucciones
                    ]), hide_index=True, use_container_width=True)
                else:
                    st.info("No se identificaron instrucciones expresas.")

                with st.expander("Fundamentos jurídicos citados"):
                    if report.fundamentos:
                        st.dataframe(pd.DataFrame([
                            {
                                "Norma": x.norma or "—",
                                "Artículos": x.articulos or "—",
                                "Página": x.pagina, "Evidencia": x.evidencia or "—",
                            } for x in report.fundamentos
                        ]), hide_index=True, use_container_width=True)
                    else:
                        st.info("No se localizaron referencias jurídicas explícitas.")
                with st.expander("Documentos referidos en la orden"):
                    if report.documentos_referidos:
                        st.dataframe(pd.DataFrame([
                            {
                                "Documento": x.documento,
                                "Finalidad indicada": x.finalidad or "—",
                                "Página": x.pagina,
                                "Evidencia": x.evidencia or "—",
                            } for x in report.documentos_referidos
                        ]), hide_index=True, use_container_width=True)
                    else:
                        st.info("No se identificaron documentos referidos.")
                firma = report.firma_aparente
                st.caption(
                    "Firma aparente (no autenticada): "
                    f"{firma.presencia}. {firma.nota_visual or ''}"
                )
                if report.observaciones:
                    with st.expander("Advertencias de extracción"):
                        for note in report.observaciones:
                            st.write("• " + note)
                st.caption(
                    "Esta extracción no determina cumplimiento de plazos, "
                    "formalización del contrato ni legalidad de la adjudicación."
                )
            except Exception:
                st.warning("La orden guardada no pudo interpretarse con el esquema v1.")
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
                # Despacho explícito por código de archivo: nunca reutilizar
                # el prompt del contrato para PUC o DICTAMEN_AD.
                code = code_from_filename(doc.name, doc.mime_type)
                if code == "PUC":
                    result = extract_or_reuse_puc(
                        sheets, st.secrets["storage"]["spreadsheet_id"],
                        pdf, doc, obra.id, st.secrets["gemini"]["api_key"],
                        model=model,
                    )
                elif code == "DICTAMEN_AD":
                    result = extract_or_reuse_dictamen(
                        sheets, st.secrets["storage"]["spreadsheet_id"],
                        pdf, doc, obra.id, st.secrets["gemini"]["api_key"],
                        model=model,
                    )
                elif code == "NOTIFICACION_AD":
                    result = extract_or_reuse_notificacion(
                        sheets, st.secrets["storage"]["spreadsheet_id"],
                        pdf, doc, obra.id, st.secrets["gemini"]["api_key"],
                        model=model,
                    )
                elif code == "ORDEN_AD":
                    result = extract_or_reuse_orden(
                        sheets, st.secrets["storage"]["spreadsheet_id"],
                        pdf, doc, obra.id, st.secrets["gemini"]["api_key"],
                        model=model,
                    )
                else:
                    raise ExtractionStateError(
                        "No existe extractor especializado para este tipo de documento."
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


def _render_delete_analysis(
    doc: DocumentRecord, obra: WorkRecord,
    tables: dict[str, list[dict[str, str]]],
) -> None:
    """Eliminar exclusivamente los resultados del PDF elegido, nunca su archivo."""
    registered = next(
        (row for row in tables["Documentos"] if row["documento_id"] == doc.id),
        None,
    )
    attempts = [
        row for row in tables["Extracciones"]
        if row["documento_id"] == doc.id and row["obra_id"] == obra.id
    ]
    if not registered or (
        not attempts and not registered["resultado_id"]
        and registered["estado_procesamiento"] == "Pendiente"
    ):
        return
    with st.expander("Eliminar análisis guardado de este archivo"):
        st.warning(
            "La eliminación retirará las extracciones, datos derivados y "
            "revisiones asociadas a este PDF. **No eliminará el documento "
            "de Google Drive ni otros archivos de la obra.** "
            "Un nuevo análisis con Gemini podrá generar consumo adicional."
        )
        st.caption(
            f"Documento: {doc.name} · Solicitudes asociadas: {len(attempts)}"
        )
        confirm_key = f"ex_delete_confirm_{doc.id}"
        typed = st.text_input(
            "Para confirmar, escribe ELIMINAR",
            key=confirm_key, placeholder="ELIMINAR",
        )
        if st.button(
            "Eliminar análisis de este documento",
            key=f"ex_delete_button_{doc.id}",
            disabled=typed != "ELIMINAR",
            type="secondary",
        ):
            try:
                with get_writer_lock():
                    sheets = create_sheets_client(
                        st.secrets["gcp_service_account"]
                    )
                    result = delete_analysis(
                        sheets, st.secrets["storage"]["spreadsheet_id"],
                        doc, obra.id,
                        expected_result_id=registered["resultado_id"],
                        actor_email=st.user.email,
                    )
                    st.session_state["ex_status_tables"] = load_status_tables(
                        sheets, st.secrets["storage"]["spreadsheet_id"],
                    )
                st.session_state.pop("ex_last_run", None)
                st.session_state.pop(confirm_key, None)
                st.session_state["ex_delete_success"] = (
                    f"Análisis eliminado de {doc.name}. "
                    "El archivo sigue en Drive. Puede volver a analizarse "
                    "si su tipo tiene un extractor habilitado."
                )
                st.rerun()
            except ExtractionStateError as exc:
                st.error(
                    "No se completó la eliminación: " + str(exc)
                )
            except Exception:
                st.error(
                    "No se pudo confirmar el borrado. Comprueba Google Sheets "
                    "antes de intentarlo nuevamente."
                )


def render_expedientes(authenticated: bool) -> None:
    st.title("Expedientes de obra")
    st.caption(
        "Explorador conectado a Google Drive · Extracción por tipo documental"
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
        "Extractores disponibles: **PUC-v1**, **DICTAMEN_AD-v1**, "
        "**NOTIFICACION_AD-v1** y **ORDEN_AD-v1**. "
        "La extracción comienza solo al pulsar Analizar; otros documentos "
        "no se enviarán a Gemini hasta habilitar su esquema especializado."
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
                "Extractor": (
                    ENABLED_EXTRACTORS.get(code_from_filename(d.name, d.mime_type), "No habilitado")
                ),
                "Compatibilidad": (
                    "Listo" if 0 < d.size_bytes <= MAX_PDF_BYTES
                    else "Sin tamaño" if not d.size_bytes
                    else "Supera 50 MB"
                ),
            }
            for d in chosen
        ]), hide_index=True, use_container_width=True)

    # Solo cuatro tipos con extractor propio llegan a Gemini.
    eligible = [
        d for d in chosen
        if code_from_filename(d.name, d.mime_type) in ENABLED_EXTRACTORS
    ]
    ignored = [d for d in chosen if d.id not in {x.id for x in eligible}]
    if ignored:
        st.warning(
            f"{len(ignored)} documento(s) carecen de extractor habilitado. "
            "No se enviarán a Gemini."
        )

    registered = {row["documento_id"]: row for row in tables["Documentos"]}
    extractions = {row["cache_key"]: row for row in tables["Extracciones"]}
    to_process = []
    reused = 0
    blocked = 0
    for doc in eligible:
        if not (0 < doc.size_bytes <= MAX_PDF_BYTES):
            continue
        row = registered.get(doc.id)
        if not row or row["obra_id"] != obra.id or row["activo"] != "SI":
            continue
        code = code_from_filename(doc.name, doc.mime_type)
        schema = ENABLED_EXTRACTORS.get(code)
        if row["md5_checksum"] != doc.md5_checksum or row["tipo_documental"] != code:
            continue
        pending_attempt = any(
            e["documento_id"] == doc.id and e["obra_id"] == obra.id
            and e["version_esquema"] == schema
            and e["estado"] in ("EN_PROCESO", "REQUIERE_REVISION")
            for e in tables["Extracciones"]
        )
        if pending_attempt or states[doc.id].label in ("Parcial", "Revisar error"):
            blocked += 1
            continue
        saved = extractions.get(row["resultado_id"])
        if (
            saved and saved["version_esquema"] == schema
            and saved["estado"] == "COMPLETADO" and saved["resultado_json"]
            and saved["documento_id"] == doc.id and saved["obra_id"] == obra.id
        ):
            reused += 1
            continue
        if states[doc.id].label not in ("Sin registrar", "Desactualizado"):
            to_process.append(doc)
    batch = to_process[:MAX_BATCH]
    if blocked:
        st.warning(
            f"{blocked} documento(s) tienen intentos incompletos o inconsistencias. "
            "No habrá reintentos automáticos."
        )
    if reused:
        st.success(
            f"{reused} documento(s) con extracción especializada guardada. "
            "Se pueden consultar sin volver a consumir Gemini."
        )
    if len(to_process) > MAX_BATCH:
        st.caption(
            f"Se analizarán como máximo {MAX_BATCH} documentos por ejecución."
        )

    gemini = st.secrets.get("gemini", {})
    model = gemini.get("model") or DEFAULT_MODEL
    st.caption(
        f"Modelo Gemini: {model} · "
        "Extractores: PUC-v1, DICTAMEN_AD-v1, NOTIFICACION_AD-v1 y ORDEN_AD-v1"
    )
    disabled = not batch or not gemini.get("api_key")
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
    if st.session_state.get("ex_delete_success"):
        st.success(st.session_state.pop("ex_delete_success"))
    preview_id = st.selectbox(
        "Documento",
        doc_ids, format_func=doc_names.get, key=f"ex_preview_{obra.id}",
    )
    preview = next(d for d in obra.pdfs if d.id == preview_id)
    current_state = file_states(inventory, st.session_state["ex_status_tables"])[preview.id]
    st.write(f"**Estado:** {current_state.label} · {current_state.detail}")
    _summarize_saved(preview, st.session_state["ex_status_tables"], current_state)
    _render_delete_analysis(
        preview, obra, st.session_state["ex_status_tables"],
    )
    if re.fullmatch(r"[A-Za-z0-9_-]{10,}", preview.id):
        st.link_button(
            "Ver PDF en Drive",
            f"https://drive.google.com/file/d/{preview.id}/view",
        )
