"""Explorador operativo de obras y PDFs: seleccionar 1, varios o toda carpeta.

No hay carga a Gemini al navegar, listar carpetas o consultar resultados.
El análisis se solicita únicamente al pulsar el botón habilitado del extractor.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from services.bulk_analysis import BULK_CODES, BulkItem, plan_bulk_analysis
from services.analysis_catalog import (
    FileStatus, file_states, folder_states, load_status_tables,
)
from services.catalogo_xlsx import CATALOGO_SCHEMA_VERSION
from services.catalogo_store import import_or_reuse_catalogo, load_catalog_rows
import json
from services.document_classifier import XLSX_MIME, guess_from_name, code_from_filename
from services.contract_schema import ExtraccionContrato
from services.amount_iva import identify_contract_amount_iva
from services.contract_upgrade import eligible_contract_upgrade
from services.contract_prompt import PROMPT_VERSION
from services.contract_v2 import (
    CONTRACT_SCHEMA_V2, ContractExtractionV2, FIELD_LABELS_V2,
    classify_cited_regime,
)
from services.extraction_store_v2 import extract_or_reuse_v2
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
    DriveConfigurationError, MAX_PDF_BYTES, MAX_XLSX_BYTES, create_drive_client,
    download_verified_pdf, download_verified_xlsx, is_configured, scan_drive,
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
# Extractores especializados autorizados. El contrato reutiliza su esquema v2.
ENABLED_EXTRACTORS = {
    "CATALOGO": CATALOGO_SCHEMA_VERSION,
    "CONTRATO": CONTRACT_SCHEMA_V2,
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
    # Un resultado anterior puede pertenecer a otra sesión de expedientes.
    st.session_state.pop("ex_last_run", None)
    st.session_state.pop("ex_last_run_obra_id", None)
    st.session_state.pop("ex_bulk_last_run", None)


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
                    if old.get("version_prompt") != PROMPT_VERSION
                    or name != "representante_tecnico"
                ]), hide_index=True, use_container_width=True)
                iva_amount = identify_contract_amount_iva(
                    result.monto_contrato.valor or "",
                    evidence=result.monto_contrato.evidencia or "",
                    page=result.monto_contrato.pagina,
                )
                if old.get("version_prompt") != PROMPT_VERSION:
                    st.caption(
                        "Indicador derivado (no literal): IVA "
                        + iva_amount.basis + " · " + iva_amount.source
                        + (f" · Página {iva_amount.page}" if iva_amount.page else "")
                    )
                else:
                    st.caption(
                        "Vista literal de los 15 campos extraídos. "
                        "La normalización, IVA supuesto y verificaciones "
                        "se muestran en Resultados y AD-06."
                    )
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
        elif old["version_esquema"] == CATALOGO_SCHEMA_VERSION:
            try:
                summary = json.loads(old["resultado_json"])
                st.markdown("#### Catálogo original importado desde Excel (sin IA)")
                a, b, c = st.columns(3)
                a.metric("Conceptos contratados", summary["conceptos_originales"])
                b.metric("Conceptos fuera de catálogo excluidos", summary["excluidos_fuera_catalogo"])
                c.metric("Importe inicial calculado sin IVA", summary["importe_original_calculado_sin_iva"])
                if summary.get("claves_repetidas", 0):
                    st.info(
                        f"{summary['claves_repetidas']} clave(s) se utilizan en "
                        f"{summary['renglones_con_clave_repetida']} renglones del catálogo. "
                        "Se conservaron todos por capítulo, hoja y fila de origen."
                    )
                st.caption(summary["nota"])
                sheets = create_sheets_client(st.secrets["gcp_service_account"])
                records = [
                    r for r in load_catalog_rows(sheets, st.secrets["storage"]["spreadsheet_id"])
                    if r[0] == status.cache_key and r[2] == document.id
                ]
                if len(records) != int(summary["conceptos_originales"]):
                    st.error("El detalle de DatosCatalogo no coincide con el resumen guardado.")
                else:
                    st.dataframe(pd.DataFrame([
                        {
                            "Clave": r[6], "Descripción": r[7], "Unidad": r[8],
                            "Cantidad inicial": r[9], "Precio U.": r[10],
                            "Importe inicial": r[11], "Capítulo": r[5],
                            "Hoja": r[3], "Fila Excel": r[4],
                        } for r in records[:300]
                    ]), hide_index=True, use_container_width=True)
                    if len(records) > 300:
                        st.caption("Vista de los primeros 300 conceptos; se guardaron todos en DatosCatalogo.")
                    st.caption("Cantidades Excedente y Total Aut. no sustituyen la cantidad Inicial.")
            except Exception:
                st.warning("El catálogo está registrado, pero no fue posible consultar sus filas.")
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
                code = code_from_filename(doc.name, doc.mime_type)
                payload = (
                    download_verified_xlsx(drive, doc, obra.id)
                    if code == "CATALOGO"
                    else download_verified_pdf(drive, doc, obra.id)
                )
                stage = "sheets"
                sheets = create_sheets_client(st.secrets["gcp_service_account"])
                stage = "analisis"
                # Despacho explícito por código de archivo: nunca reutilizar
                # el prompt del contrato para PUC o DICTAMEN_AD.
                if code == "CATALOGO":
                    result = import_or_reuse_catalogo(
                        sheets, st.secrets["storage"]["spreadsheet_id"],
                        payload, doc, obra.id,
                    )
                elif code == "CONTRATO":
                    result = extract_or_reuse_v2(
                        sheets, st.secrets["storage"]["spreadsheet_id"],
                        payload, doc, obra.id, st.secrets["gemini"]["api_key"],
                        model=model,
                    )
                elif code == "PUC":
                    result = extract_or_reuse_puc(
                        sheets, st.secrets["storage"]["spreadsheet_id"],
                        payload, doc, obra.id, st.secrets["gemini"]["api_key"],
                        model=model,
                    )
                elif code == "DICTAMEN_AD":
                    result = extract_or_reuse_dictamen(
                        sheets, st.secrets["storage"]["spreadsheet_id"],
                        payload, doc, obra.id, st.secrets["gemini"]["api_key"],
                        model=model,
                    )
                elif code == "NOTIFICACION_AD":
                    result = extract_or_reuse_notificacion(
                        sheets, st.secrets["storage"]["spreadsheet_id"],
                        payload, doc, obra.id, st.secrets["gemini"]["api_key"],
                        model=model,
                    )
                elif code == "ORDEN_AD":
                    result = extract_or_reuse_orden(
                        sheets, st.secrets["storage"]["spreadsheet_id"],
                        payload, doc, obra.id, st.secrets["gemini"]["api_key"],
                        model=model,
                    )
                else:
                    raise ExtractionStateError(
                        "No existe extractor especializado para este tipo de documento."
                    )
                reused = result.cached
            outcome = (
                "Reutilizado (sin IA)" if reused
                else "Importado desde Excel (sin IA)" if code == "CATALOGO"
                else "Analizado y guardado"
            )
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


def _run_bulk_batch(batch: tuple[BulkItem, ...], model: str) -> list[dict[str, str]]:
    """Procesamiento multicarpeta SECUENCIAL, mismo extractor/caché por obra.

    No hay una nueva ruta de Gemini: _analyze valida el PDF y registra
    resultados en Sheets con el mismo cerrojo que la extracción individual.
    """
    if not batch or len(batch) > MAX_BATCH:
        raise ValueError("El lote no contiene un bloque válido de hasta 10 PDFs.")
    grouped: dict[str, tuple[WorkRecord, list[DocumentRecord]]] = {}
    for item in batch:
        if item.work.id not in grouped:
            grouped[item.work.id] = (item.work, [])
        grouped[item.work.id][1].append(item.document)
    log: list[dict[str, str]] = []
    for work, docs in grouped.values():
        for entry in _analyze(work, docs, model):
            log.append({
                "Carpeta": work.name,
                "Documento": entry["Documento"],
                "Tipo": (
                    code_from_filename(entry["Documento"], "application/pdf")
                    or "Sistema"
                ),
                "Resultado": entry["Resultado"],
            })
    return log


def _render_bulk_analysis(
    inventory: DriveInventory,
    tables: dict[str, list[dict[str, str]]],
    states: dict[str, FileStatus],
) -> None:
    """Elegir todas o algunas carpetas y CONTRATO, PUC o ambos.

    Una pulsación procesa como máximo MAX_BATCH PDFs, incluso si se
    seleccionaron 100 carpetas. Para el siguiente bloque se vuelve a
    pulsar tras ver resultados, sin volver a cobrar PDFs ya completados.
    """
    st.markdown("#### Analizar documentos en varias carpetas")
    st.caption(
        "Elige el universo de obras y qué tipo documental analizar. "
        "Se usan las mismas carpetas de Google Drive y los mismos "
        "extractores CONTRATO-v2 y PUC-v1."
    )
    works_by_id = {work.id: work for work in inventory.works}
    choices = [work.id for work in inventory.works]
    scope = st.radio(
        "Carpetas a incluir",
        ["Todas las carpetas", "Seleccionar varias carpetas"],
        horizontal=True, key="ex_bulk_scope",
    )
    if scope == "Todas las carpetas":
        folder_ids = choices
        st.caption(f"Se incluyen las {len(choices)} carpetas del inventario.")
    else:
        folder_ids = st.multiselect(
            "Selecciona las carpetas",
            choices,
            key="ex_bulk_selected_folders",
            format_func=lambda folder_id: works_by_id[folder_id].name,
            help="Puedes buscar por el nombre de la carpeta y elegir varias obras.",
        )
    codes = st.multiselect(
        "Documentos a analizar en cada carpeta",
        BULK_CODES,
        default=["CONTRATO"],
        key="ex_bulk_codes",
        format_func=lambda code: (
            "CONTRATO.pdf" if code == "CONTRATO" else "PUC.pdf"
        ),
        help="Selecciona CONTRATO, PUC o los dos. Los demás documentos no se procesarán.",
    )
    if not folder_ids or not codes:
        st.info("Selecciona al menos una carpeta y un tipo documental.")
        return
    try:
        plan = plan_bulk_analysis(inventory, tables, states, folder_ids, codes)
    except ValueError as exc:
        st.error(str(exc))
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Carpetas incluidas", plan.folders)
    c2.metric("PDF pendientes", plan.ready)
    c3.metric("Ya analizados", plan.count("Ya analizado"))
    c4.metric(
        "Requieren atención",
        sum(plan.count(k) for k in ("Bloqueado", "Ambiguo", "Desactualizado")),
    )

    if plan.decisions:
        with st.expander(
            "Ver documentos y estado por carpeta", expanded=False,
        ):
            st.dataframe(pd.DataFrame([
                {
                    "Carpeta": entry.folder,
                    "Tipo": entry.code,
                    "Documento": entry.document,
                    "Estado": entry.status,
                    "Detalle": entry.detail,
                }
                for entry in plan.decisions
            ]), hide_index=True, use_container_width=True, height=345)
            st.caption(
                "Los documentos ya analizados se omiten para evitar gasto "
                "de IA. Los archivos duplicados, desactualizados o con "
                "intentos incompletos se excluyen hasta su revisión."
            )

    batch = plan.pending[:MAX_BATCH]
    if batch:
        st.markdown(f"**Próximo bloque: {len(batch)} de {plan.ready} PDF pendientes**")
        st.caption(
            "Máximo 10 documentos por ejecución. Se procesarán de forma "
            "secuencial, aunque correspondan a distintas carpetas. "
            "Si hay más pendientes, vuelve a pulsar el botón después "
            "de revisar el resultado del bloque."
        )
        st.dataframe(pd.DataFrame([
            {
                "Carpeta": item.work.name,
                "Documento": item.document.name,
                "Tipo": item.code,
                "Tamaño (MB)": round(item.document.size_bytes / 1_000_000, 2),
            } for item in batch
        ]), hide_index=True, use_container_width=True, height=295)
    else:
        st.success(
            "No hay documentos pendientes compatibles con esta selección. "
            "Revisa los omitidos o actualiza Google Drive si es necesario."
        )

    gemini = st.secrets.get("gemini", {})
    model = gemini.get("model") or DEFAULT_MODEL
    st.caption(f"Modelo Gemini: {model}. Ningún PDF se envía hasta tu confirmación.")
    approved = st.checkbox(
        "Confirmo que deseo analizar los documentos de este bloque "
        "y que cada extracción nueva puede consumir API de Gemini.",
        key="ex_bulk_approve",
    )
    disabled = not batch or not approved or not gemini.get("api_key")
    if st.button(
        f"Analizar siguiente bloque de {len(batch)} PDF(s)",
        type="primary", disabled=disabled, key="ex_bulk_analyze",
    ):
        st.session_state["ex_bulk_last_run"] = _run_bulk_batch(
            tuple(batch), model,
        )
        st.session_state["ex_bulk_approve"] = False
        # El análisis ya actualizó Sheets; refrescar Resultados y AD-06.
        st.session_state.pop("results_portfolio", None)
        st.session_state.pop("award_limits_contracts", None)
        st.rerun()

    if st.session_state.get("ex_bulk_last_run"):
        st.markdown("#### Resultado del último bloque multicarpeta")
        st.dataframe(
            pd.DataFrame(st.session_state["ex_bulk_last_run"]),
            hide_index=True, use_container_width=True,
        )
        st.caption(
            "Los documentos finalizados ya no se seleccionarán en el "
            "siguiente bloque. Si algún documento falló o no quedó "
            "confirmado, revisa Extracciones y su estado antes de reintentar."
        )


def _render_contract_upgrade(
    doc: DocumentRecord, obra: WorkRecord,
    tables: dict[str, list[dict[str, str]]],
) -> None:
    """Permite actualizar expresamente un contrato v2 anterior sin borrarlo.

    En el primer clic solo se confirma intención. Solo la segunda acción
    solicita la descarga verificada de Drive y el extractor actual a Gemini.
    """
    registered = next(
        (r for r in tables["Documentos"] if r["documento_id"] == doc.id), None,
    )
    saved = next(
        (r for r in tables["Extracciones"]
         if registered and r["cache_key"] == registered["resultado_id"]), None,
    )
    allowed, note = eligible_contract_upgrade(
        doc, obra.id, registered, saved, tables["Extracciones"],
    )
    if not allowed:
        return
    with st.expander("Actualizar este contrato con el extractor mejorado"):
        st.info(
            f"{note} El análisis actual se conservará en el historial. "
            "La nueva versión incluye revisión de la modalidad económica "
            "(precios unitarios/precio alzado) y evita clasificar testigos "
            "como representantes técnicos."
        )
        st.warning(
            "Esta acción realizará una nueva solicitud a Gemini y puede "
            "generar consumo de API. No borra los análisis anteriores. "
            "Si la nueva extracción no se confirma, revisa los registros "
            "antes de intentar nuevamente."
        )
        accepted = st.checkbox(
            "Confirmo que deseo volver a analizar únicamente este contrato "
            "y entiendo el posible consumo de Gemini.",
            key=f"ex_upgrade_confirm_{doc.id}",
        )
        gemini = st.secrets.get("gemini", {})
        model = gemini.get("model") or DEFAULT_MODEL
        if st.button(
            f"Actualizar análisis de CONTRATO ({PROMPT_VERSION})",
            key=f"ex_upgrade_button_{doc.id}",
            disabled=not accepted or not gemini.get("api_key"),
            type="primary",
        ):
            # _analyze comprueba Drive/MD5, utiliza el lock de Sheets y
            # conserva extracciones anteriores mediante cache_key distinta.
            # Este botón NO usa la eliminación ni modifica el PDF original.
            st.session_state["ex_last_run"] = _analyze(obra, [doc], model)
            st.session_state["ex_last_run_obra_id"] = obra.id
            st.session_state.pop("results_portfolio", None)
            st.session_state.pop("award_limits_contracts", None)
            st.rerun()


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
            "revisiones asociadas a este documento. **No eliminará el archivo "
            "de Google Drive ni otros archivos de la obra.** "
            "Un nuevo análisis PDF con Gemini podría generar consumo; Excel se importa sin IA."
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


def _choose_folder(folder_id: str) -> None:
    """Cambiar de obra desde el árbol lateral, sin ejecutar extractores."""
    st.session_state["ex_selected_folder"] = folder_id


def _render_sidebar_folders(
    inventory: DriveInventory,
    folders: dict,
    states: dict[str, FileStatus],
    *,
    folder_container=None,
) -> str:
    """Explorador lateral desplegable; la extracción permanece arriba a la derecha.

    La selección usa el mismo ID de obra y la misma clave de sesión anterior.
    Buscar, abrir carpetas y consultar estados no consumen Gemini.
    """
    ids = [work.id for work in inventory.works]
    label_by_id = {work.id: work.name for work in inventory.works}
    work_by_id = {work.id: work for work in inventory.works}
    if st.session_state.get("ex_selected_folder") not in work_by_id:
        st.session_state["ex_selected_folder"] = ids[0]

    panel = folder_container if folder_container is not None else st.sidebar
    with panel:
        st.markdown("### 📁 Carpetas de obra")
        st.caption(f"{len(ids)} obras detectadas en Google Drive")
        obra_id = st.selectbox(
            "Carpeta a trabajar",
            ids,
            format_func=lambda item: label_by_id[item],
            key="ex_selected_folder",
            help="Escribe parte del nombre para localizar una obra. "
                 "La selección cambia el expediente de la zona principal.",
        )
        selected_work = work_by_id[obra_id]
        selected_state = folders[obra_id]
        st.caption(
            f"**{selected_state.label}** · "
            f"{selected_state.complete}/{selected_state.total} documentos procesados"
        )

        with st.expander("Buscar y explorar obras", expanded=True):
            search = st.text_input(
                "Buscar carpeta o PDF",
                placeholder="Nombre de obra, número o archivo...",
                key="ex_search",
            ).casefold().strip()
            filter_status = st.selectbox(
                "Filtrar estado",
                ["Todos", "Analizada", "Parcial", "Pendiente", "Revisar error", "Sin PDF"],
                key="ex_folder_filter",
            )
            visible = [
                work for work in inventory.works
                if (
                    not search or search in work.name.casefold()
                    or any(
                        search in file.name.casefold()
                        for file in (*work.pdfs, *work.other_files)
                    )
                )
                and (
                    filter_status == "Todos"
                    or folders[work.id].label == filter_status
                )
            ]
            st.caption(f"{len(visible)} carpeta(s) coinciden con el filtro")
            if not visible:
                st.info("No hay carpetas que coincidan con el filtro.")
            else:
                # Evita apilar cientos de controles en la barra lateral. La
                # lista se desplaza por separado, sin mover la extracción.
                with st.container(height=300, border=False):
                    for work in visible[:60]:
                        fs = folders[work.id]
                        selected_icon = "●" if work.id == obra_id else "📁"
                        st.button(
                            f"{selected_icon} {work.name}",
                            key=f"ex_nav_folder_{work.id}",
                            use_container_width=True,
                            help=(
                                f"{fs.label} · "
                                f"{fs.complete}/{fs.total} documentos procesados"
                            ),
                            on_click=_choose_folder,
                            args=(work.id,),
                        )
                        st.caption(
                            f"{fs.label} · {fs.complete}/{fs.total} procesados"
                        )
                if len(visible) > 60:
                    st.caption(
                        f"Se muestran 60 de {len(visible)} carpetas. "
                        "Escribe parte del nombre para acotar la búsqueda; "
                        "también puedes buscar directamente en «Carpeta a trabajar»."
                    )

        with st.expander("Documentos de la carpeta seleccionada", expanded=False):
            work_docs = [
                *selected_work.pdfs,
                *(
                    doc for doc in selected_work.other_files
                    if code_from_filename(doc.name, doc.mime_type) == "CATALOGO"
                ),
            ]
            if not work_docs:
                st.caption("Sin documentos compatibles con los extractores.")
            for doc in work_docs:
                path_label = (
                    (doc.relative_path + "/" if doc.relative_path else "")
                    + doc.name
                )
                st.markdown(f"**{path_label}**")
                st.caption(
                    f"{guess_from_name(doc.name, doc.mime_type).label} · "
                    f"{states[doc.id].label} · {doc.modified_time or 'Sin fecha'}"
                )
            other_files = [
                doc for doc in selected_work.other_files if doc not in work_docs
            ]
            if other_files:
                st.markdown("**Otros archivos detectados**")
                for doc in other_files:
                    st.caption(
                        f"{doc.name} · {guess_from_name(doc.name, doc.mime_type).label}"
                        " · Sin extractor compatible"
                    )
            st.caption(
                "Los tipos se asignan por nombre y extensión. Si un PDF "
                "aparece como POR_IDENTIFICAR, renómbralo en Drive y sincroniza."
            )
    return obra_id


def render_expedientes(authenticated: bool, folder_container=None) -> None:
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
    st.caption(
        f"Carpeta raíz: {inventory.root_name} · "
        f"Última sincronización: {st.session_state.get('ex_synced_at', 'Sin fecha')} UTC"
    )
    if not inventory.works:
        st.info(
            "No hay carpetas de obra en el directorio autorizado. "
            "Compártelas con la cuenta de servicio y actualiza Drive."
        )
        return

    # La navegación y el inventario ahora viven en la barra lateral,
    # desplegable de Streamlit. El motor y los IDs de obra no cambian.
    obra_id = _render_sidebar_folders(
        inventory, folders, states, folder_container=folder_container,
    )
    obra = next(work for work in inventory.works if work.id == obra_id)

    st.markdown("### Extracción documental")
    selection_mode = st.radio(
        "Modalidad de análisis",
        ["Una carpeta", "Varias carpetas"],
        horizontal=True, key="ex_analysis_mode",
        help="Una carpeta conserva el flujo habitual. Varias carpetas "
             "permite elegir CONTRATO, PUC o ambos en todas o algunas obras.",
    )
    if selection_mode == "Varias carpetas":
        _render_bulk_analysis(inventory, tables, states)
        return
    st.caption(
        f"Obra seleccionada: **{obra.name}** · "
        f"{folders[obra.id].complete}/{folders[obra.id].total} documentos procesados"
    )
    st.info(
        "Extractores disponibles: **CONTRATO-v2 (16 campos)**, **PUC-v1**, **DICTAMEN_AD-v1**, "
        "**NOTIFICACION_AD-v1**, **ORDEN_AD-v1** y **CATALOGO.xlsx (sin IA)**. "
        "Los PDF se analizan con Gemini solo al pulsar Analizar; el Excel "
        "se lee localmente sin IA y excluye los conceptos fuera de catálogo."
    )
    work_docs = [
        *obra.pdfs,
        *(d for d in obra.other_files if code_from_filename(d.name, d.mime_type) == "CATALOGO"),
    ]
    if not work_docs:
        st.info("Esta carpeta no contiene PDFs o CATALOGO.xlsx para procesar.")
        return
    doc_ids = [doc.id for doc in work_docs]
    doc_names = {
        doc.id: (doc.relative_path + "/" if doc.relative_path else "") + doc.name
        for doc in work_docs
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
        st.caption("Se seleccionarán todos los PDF y CATALOGO.xlsx de la carpeta.")

    chosen = [doc for doc in work_docs if doc.id in selected]
    st.caption(
        f"Seleccionados: {len(chosen)} archivos · "
        f"Límite por ejecución: {MAX_BATCH} · PDF máximo: 50 MB · XLSX máximo: 15 MB"
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
                    "Listo" if 0 < d.size_bytes <= (
                        MAX_XLSX_BYTES if d.mime_type == XLSX_MIME else MAX_PDF_BYTES
                    ) else "Sin tamaño" if not d.size_bytes
                    else "Supera límite XLSX 15 MB" if d.mime_type == XLSX_MIME
                    else "Supera 50 MB"
                ),
            }
            for d in chosen
        ]), hide_index=True, use_container_width=True)

    # Solo los tipos con extractor propio llegan a Gemini.
    eligible = [
        d for d in chosen
        if code_from_filename(d.name, d.mime_type) in ENABLED_EXTRACTORS
    ]
    ignored = [d for d in chosen if d.id not in {x.id for x in eligible}]
    if ignored:
        st.warning(
            f"{len(ignored)} documento(s) no tienen un nombre canónico "
            "reconocido o un extractor compatible con su formato. "
            "Revisa nombre y extensión en Drive. No se enviarán a Gemini."
        )

    registered = {row["documento_id"]: row for row in tables["Documentos"]}
    extractions = {row["cache_key"]: row for row in tables["Extracciones"]}
    to_process = []
    reused = 0
    blocked = 0
    needs_sync = 0
    for doc in eligible:
        limit = MAX_XLSX_BYTES if doc.mime_type == XLSX_MIME else MAX_PDF_BYTES
        if not (0 < doc.size_bytes <= limit):
            continue
        row = registered.get(doc.id)
        if not row or row["obra_id"] != obra.id or row["activo"] != "SI":
            continue
        code = code_from_filename(doc.name, doc.mime_type)
        schema = ENABLED_EXTRACTORS.get(code)
        if row["md5_checksum"] != doc.md5_checksum or row["tipo_documental"] != code:
            needs_sync += 1
            continue
        pending_attempt = any(
            e["documento_id"] == doc.id and e["obra_id"] == obra.id
            and e["version_esquema"] == schema
            and e["estado"] in ("EN_PROCESO", "REQUIERE_REVISION")
            for e in tables["Extracciones"]
        )
        # Bloquear solo intentos de este esquema; las versiones anteriores
        # pueden actualizarse mediante una nueva solicitud explícita.
        if pending_attempt:
            blocked += 1
            continue
        saved = extractions.get(row["resultado_id"])
        if (
            saved and saved["version_esquema"] == schema
            and states[doc.id].label == "Analizado"
            and saved["estado"] == "COMPLETADO" and saved["resultado_json"]
            and saved["documento_id"] == doc.id and saved["obra_id"] == obra.id
        ):
            reused += 1
            continue
        if states[doc.id].label != "Sin registrar":
            to_process.append(doc)
    batch = to_process[:MAX_BATCH]
    if needs_sync:
        st.warning(
            f"{needs_sync} documento(s) tienen la clasificación o huella "
            "desactualizada en Google Sheets. Pulsa Actualizar Google Drive "
            "antes de analizarlos; no se enviarán a Gemini mientras tanto."
        )
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
        "Extractores: CONTRATO-v2, PUC-v1, DICTAMEN_AD-v1, "
        "NOTIFICACION_AD-v1, ORDEN_AD-v1 y CATALOGO-xlsx-v1 (sin IA)"
    )
    requires_gemini = any(d.mime_type != XLSX_MIME for d in batch)
    disabled = not batch or (requires_gemini and not gemini.get("api_key"))
    button_label = (
        "No hay documentos pendientes para procesar" if not batch
        else f"Analizar {len(batch)} documento(s) con IA y/o importar Excel"
        if requires_gemini else f"Importar {len(batch)} catálogo(s) sin IA"
    )
    if st.button(
        button_label,
        type="primary", disabled=disabled, key="ex_analyze",
    ):
        st.session_state["ex_last_run"] = _analyze(obra, batch, model)
        st.session_state["ex_last_run_obra_id"] = obra.id
        # El dashboard y AD-06 deben leer los nuevos datos de Sheets.
        st.session_state.pop("results_portfolio", None)
        st.session_state.pop("award_limits_contracts", None)
        st.rerun()

    if (
        st.session_state.get("ex_last_run_obra_id") == obra.id
        and st.session_state.get("ex_last_run")
    ):
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
    preview = next(d for d in work_docs if d.id == preview_id)
    current_state = file_states(inventory, st.session_state["ex_status_tables"])[preview.id]
    st.write(f"**Estado:** {current_state.label} · {current_state.detail}")
    _summarize_saved(preview, st.session_state["ex_status_tables"], current_state)
    _render_contract_upgrade(
        preview, obra, st.session_state["ex_status_tables"],
    )
    _render_delete_analysis(
        preview, obra, st.session_state["ex_status_tables"],
    )
    if re.fullmatch(r"[A-Za-z0-9_-]{10,}", preview.id):
        st.link_button(
            "Ver documento en Drive",
            f"https://drive.google.com/file/d/{preview.id}/view",
        )
