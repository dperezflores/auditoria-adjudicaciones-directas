"""Dashboard del piloto con solo lectura de Sheets y estado de cotejo."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4
import re
import pandas as pd
import streamlit as st

from services.dashboard_service import DashboardDataError, read_dashboard
from services.sheets_service import create_sheets_client, storage_configured
from services.review_service import ReviewError, validate_review, save_review
from services.writer_lock import get_writer_lock

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

    if st.session_state.get("review_last_result"):
        st.success(st.session_state.pop("review_last_result"))
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
                    "Valor IA": contract.datos.get(key) or "No localizado",
                    "Cotejo humano": (
                        contract.revisiones[key].decision
                        if key in contract.revisiones else "Pendiente"
                    ),
                    "Valor cotejado": (
                        contract.revisiones[key].valor_cotejado
                        if key in contract.revisiones else ""
                    ),
                    "Página": (
                        contract.revisiones[key].pagina
                        if key in contract.revisiones else ""
                    ),
                }
                for label, key in _LABELS
            ]),
            hide_index=True,
            use_container_width=True,
        )
        st.caption(
            f"**Avance del cotejo: {contract.campos_cotejados}/8 campos.** "
            "Las revisiones humanas quedan registradas sin sobrescribir la respuesta de IA."
        )
        # Un vínculo directo permite cotejar visualmente el PDF escaneado.
        if re.fullmatch(r"[A-Za-z0-9_-]{10,}", contract.documento_id):
            st.link_button(
                "Abrir PDF original en Google Drive",
                f"https://drive.google.com/file/d/{contract.documento_id}/view",
            )

        st.markdown("#### Cotejo manual por campo")
        st.caption(
            "Confirma o corrige cada dato después de verificarlo en el PDF. "
            "Registrar una página o cita no verifica automáticamente su exactitud."
        )
        labels = {key: label for label, key in _LABELS}
        field_key = st.selectbox(
            "Campo que deseas cotejar",
            [key for _, key in _LABELS],
            format_func=labels.get,
            key=f"review_selector_{contract.documento_id}",
        )
        extracted_value = contract.datos.get(field_key, "")
        earlier = contract.revisiones.get(field_key)
        if earlier:
            st.info(
                f"Último cotejo: {earlier.decision} por "
                f"{earlier.revisor_email} el {earlier.fecha_utc}. "
                "Guardar una nueva revisión conserva el evento anterior."
            )
        st.write(f"**Valor que propuso la IA:** {extracted_value or 'No localizado'}")
        prefix = f"review_{contract.documento_id}_{field_key}"
        with st.form(key=f"form_{prefix}"):
            decision = st.selectbox(
                "Decisión del auditor",
                ["Confirmado", "Corregido", "No localizado"],
                index=2 if not extracted_value else 0,
                key=f"decision_{prefix}",
            )
            corrected = st.text_input(
                "Valor cotejado (vacío si no fue localizado)",
                value=extracted_value,
                key=f"valor_{prefix}",
            )
            page = st.text_input(
                "Página del PDF donde aparece",
                placeholder="Ejemplo: 1",
                key=f"pagina_{prefix}",
            )
            quote = st.text_area(
                "Fragmento de evidencia localizado en el PDF",
                placeholder="Transcribe el texto que respalda el dato",
                key=f"evidencia_{prefix}",
                max_chars=1000,
                height=88,
            )
            reason = st.text_area(
                "Justificación (obligatoria para correcciones o datos no localizados)",
                key=f"justificacion_{prefix}",
                max_chars=2000,
                height=82,
            )
            submitted = st.form_submit_button(
                "Guardar cotejo del campo",
                type="primary",
            )
        if submitted:
            token_key = f"revision_token_{contract.documento_id}_{field_key}"
            if token_key not in st.session_state:
                st.session_state[token_key] = uuid4().hex
            try:
                reviewer_email = st.user.email
                event = validate_review(
                    obra_id=contract.obra_id,
                    documento_id=contract.documento_id,
                    cache_key=contract.cache_key,
                    campo=field_key,
                    decision=decision,
                    valor_extraido=extracted_value,
                    valor_cotejado=corrected,
                    pagina=page,
                    evidencia=quote,
                    justificacion=reason,
                    revisor_email=reviewer_email,
                    revision_id=st.session_state[token_key],
                )
                with get_writer_lock():
                    client = create_sheets_client(st.secrets["gcp_service_account"])
                    created, _ = save_review(
                        client, st.secrets["storage"]["spreadsheet_id"], event
                    )
                    refreshed = read_dashboard(
                        client, st.secrets["storage"]["spreadsheet_id"]
                    )
                st.session_state["dashboard_live_snapshot"] = refreshed
                st.session_state["dashboard_live_updated"] = (
                    datetime.now(timezone.utc).isoformat(timespec="seconds")
                )
                st.session_state["review_last_result"] = (
                    "Cotejo registrado en RevisionesContrato."
                    if created else "La revisión ya estaba registrada; no se duplicó."
                )
                st.session_state.pop(token_key, None)
                for suffix in ("decision", "valor", "pagina", "evidencia", "justificacion"):
                    st.session_state.pop(f"{suffix}_{prefix}", None)
                st.rerun()
            except ReviewError as exc:
                st.error(str(exc))
            except Exception:
                st.error(
                    "No se pudo confirmar el guardado del cotejo. "
                    "Consulta RevisionesContrato antes de intentar nuevamente."
                )
        st.caption(
            "Los cotejos son registros de revisión profesional del piloto, "
            "no dictámenes ni determinaciones de cumplimiento normativo."
        )
