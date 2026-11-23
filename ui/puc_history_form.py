"""Formulario de cotejo histórico usado tanto por CC-01 como por AD-03.

Cada guardado agrega un evento; no modifica PDFs ni respuestas Gemini.
"""
from __future__ import annotations

import streamlit as st

from services.puc_history import (
    CONCLUSIONS, STATES, PucHistoryError, latest_puc_review,
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
                f"{previous.conclusion_auditor}. Referencia: {previous.referencia}"
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
            st.caption(
                "Deja vacíos ambos campos si no cuentas con el historial "
                "oficial del capital. El importe de una cédula posterior no basta."
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
            conclusion = st.selectbox(
                "Conclusión del auditor (se guarda separada del resultado automático)",
                CONCLUSIONS,
                index=CONCLUSIONS.index(prev("conclusion_auditor"))
                if prev("conclusion_auditor") in CONCLUSIONS else 0,
                key=f"conclusion_{key}",
            )
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
                fecha_registro_capital=registered,
                fuente=source, referencia=reference,
                conclusion_auditor=conclusion, observaciones=note,
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
