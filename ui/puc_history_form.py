"""Formulario de cotejo histórico usado tanto por CC-01 como por AD-03.

Cada guardado agrega un evento; no modifica PDFs ni respuestas Gemini.
"""
from __future__ import annotations

import streamlit as st

from services.puc_history import (
    CONCLUSIONS, STATES, ALCANCES_CAPITAL, PucHistoryError, latest_puc_review,
    make_puc_review, save_puc_review,
)
from services.sheets_service import create_sheets_client
from services.writer_lock import get_writer_lock


def render_puc_history_form(record, puc, reviews, *, prefix: str) -> None:
    if not puc:
        st.caption("Para registrar una verificación histórica primero debe existir PUC analizado.")
        return
    previous = latest_puc_review(reviews, record, puc)
    key = f"{prefix}_{record.documento_id}_{record.cache_key[:12]}_{puc.cache_key[:12]}"
    with st.expander("Registrar evidencia histórica del PUC (guardar con auditor y fecha)"):
        st.caption(
            "El auditor incorpora una referencia verificable de refrendos y/o "
            "actualizaciones de capital. La impresión y validación del PDF no "
            "se tratan como fechas de registro del capital. Cada guardado "
            "queda en RevisionesPUC; la extracción original no cambia."
        )
        if previous:
            st.info(
                f"Última revisión: {previous.fecha_utc} · {previous.auditor} · "
                f"Capital: {previous.conclusion_capital} · Vigencia: "
                f"{previous.conclusion_vigencia}. Referencia: {previous.referencia}"
            )
        def prev(name):
            return getattr(previous, name) if previous else ""

        with st.form(f"hist_puc_{key}"):
            st.markdown("**Fecha efectiva de adjudicación y refrendo**")
            a, b, c = st.columns(3)
            with a:
                assignment = st.text_input(
                    "Fecha efectiva de asignación (DD/MM/AAAA)",
                    value=prev("fecha_asignacion"), key=f"assignment_{key}",
                    placeholder="15/06/2025",
                )
            with b:
                start = st.text_input(
                    "Inicio del registro/refrendo histórico",
                    value=prev("vigencia_desde"), key=f"valid_from_{key}",
                    placeholder="22/11/2024",
                )
            with c:
                end = st.text_input(
                    "Fin del registro/refrendo histórico",
                    value=prev("vigencia_hasta"), key=f"valid_to_{key}",
                    placeholder="22/11/2025",
                )
            state = st.selectbox(
                "Estado histórico acreditado (opcional)",
                STATES, index=STATES.index(prev("estado_registro_historico"))
                if prev("estado_registro_historico") in STATES else 0,
                key=f"status_{key}",
            )
            st.markdown("**Capital oficialmente registrado en la asignación**")
            a, b = st.columns(2)
            with a:
                capital = st.text_input(
                    "Importe de capital histórico (MXN)",
                    value=prev("capital_historico"),
                    key=f"hist_capital_{key}", placeholder="900000.00",
                )
            with b:
                registered = st.text_input(
                    "Fecha en que se registró ese capital ante el PUC",
                    value=prev("fecha_registro_capital"),
                    key=f"reg_capital_{key}", placeholder="01/04/2025",
                )
            scope = st.selectbox(
                "Alcance del soporte para acreditar el último capital a la asignación",
                ALCANCES_CAPITAL,
                index=ALCANCES_CAPITAL.index(prev("alcance_capital"))
                if prev("alcance_capital") in ALCANCES_CAPITAL else 0,
                key=f"scope_capital_{key}",
            )
            st.caption(
                "El importe y su fecha no bastan si el soporte únicamente "
                "acredita un movimiento aislado. Para aplicar el capital como "
                "histórico se requiere historial completo o certificación "
                "del saldo vigente en la fecha de asignación."
            )
            st.markdown("**Trazabilidad y juicio profesional**")
            source = st.text_input(
                "Fuente de la evidencia (obligatorio)",
                value=prev("fuente"), key=f"source_{key}",
                placeholder="Historial PUC emitido por autoridad administradora",
            )
            reference = st.text_input(
                "Identificación verificable del soporte (obligatorio)",
                value=prev("referencia"), key=f"reference_{key}",
                placeholder="Oficio, folio, fecha, página o enlace del documento",
            )
            a, b = st.columns(2)
            with a:
                conclusion_capital = st.selectbox(
                    "Conclusión del auditor: capital (CC-01)",
                    CONCLUSIONS,
                    index=CONCLUSIONS.index(prev("conclusion_capital"))
                    if prev("conclusion_capital") in CONCLUSIONS else 0,
                    key=f"conclusion_capital_{key}",
                )
            with b:
                conclusion_vigencia = st.selectbox(
                    "Conclusión del auditor: vigencia (AD-03)",
                    CONCLUSIONS,
                    index=CONCLUSIONS.index(prev("conclusion_vigencia"))
                    if prev("conclusion_vigencia") in CONCLUSIONS else 0,
                    key=f"conclusion_vigencia_{key}",
                )
            st.caption("Las conclusiones profesionales se guardan separadas del motor automático.")
            note = st.text_area(
                "Explicación del cotejo (obligatoria)",
                value=prev("observaciones"), max_chars=1800,
                key=f"note_{key}",
            )
            submitted = st.form_submit_button(
                "Guardar revisión histórica del PUC", type="primary",
            )
        if not submitted:
            return

        try:
            event = make_puc_review(
                obra_id=record.obra_id,
                contrato_documento_id=record.documento_id,
                contrato_cache_key=record.cache_key,
                puc_documento_id=puc.documento_id,
                puc_cache_key=puc.cache_key,
                auditor=str(getattr(st.user, "email", "") or ""),
                fecha_asignacion=assignment, vigencia_desde=start,
                vigencia_hasta=end, estado_registro_historico=state,
                capital_historico=capital,
                fecha_registro_capital=registered, alcance_capital=scope,
                fuente=source, referencia=reference,
                conclusion_capital=conclusion_capital,
                conclusion_vigencia=conclusion_vigencia, observaciones=note,
            )
            client = create_sheets_client(dict(st.secrets["gcp_service_account"]))
            with get_writer_lock():
                save_puc_review(
                    client, str(st.secrets["storage"]["spreadsheet_id"]), event
                )
        except PucHistoryError as exc:
            st.error(str(exc))
            return
        except Exception:
            st.error(
                "No se confirmó el registro en RevisionesPUC. "
                "Comprueba la hoja antes de intentar otro guardado."
            )
            return
        st.session_state.pop("puc_historical_reviews", None)
        st.session_state.pop("capital_sources", None)
        st.session_state.pop("award_limits_contracts", None)
        st.success("Revisión histórica guardada en Google Sheets.")
        st.rerun()
