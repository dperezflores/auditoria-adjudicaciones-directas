"""Interfaz AD-03: verificación independiente de vigencia histórica del PUC."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from services.contract_normalization import normalized_values
from services.contract_verifications import read_verified_portfolio
from services.capital_contable import read_capital_sources
from services.puc_validity import evaluate_puc_validity
from services.puc_history import (
    PucHistoryError, latest_puc_review, read_puc_reviews,
)
from services.sheets_service import create_sheets_client
from ui.puc_history_form import render_puc_history_form


def render_puc_validity_test() -> None:
    st.markdown("### Verificación de vigencia del PUC")
    st.caption(
        "Prueba AD-03 · Vigencia del registro o refrendo en las fechas de "
        "asignación y firma del contrato · Municipio de León."
    )
    st.info(
        "Se evalúan los periodos de vigencia del PUC, no el capital. "
        "La impresión de una constancia después de adjudicar NO invalida "
        "por sí sola el registro. Una cédula sin historial completo tampoco "
        "prueba automáticamente que el contratista carecía de registro."
    )
    if st.button("Actualizar contratos y revisiones del PUC", key="puc_validity_reload"):
        for name in ("capital_sources", "award_limits_contracts", "puc_historical_reviews"):
            st.session_state.pop(name, None)
        st.rerun()

    client = create_sheets_client(dict(st.secrets["gcp_service_account"]))
    book = str(st.secrets["storage"]["spreadsheet_id"])
    try:
        if "award_limits_contracts" not in st.session_state:
            st.session_state["award_limits_contracts"] = read_verified_portfolio(client, book)
        if "capital_sources" not in st.session_state:
            st.session_state["capital_sources"] = read_capital_sources(client, book)
        if "puc_historical_reviews" not in st.session_state:
            st.session_state["puc_historical_reviews"] = read_puc_reviews(client, book)
    except PucHistoryError as exc:
        st.error("No se pudo verificar el historial PUC: " + str(exc))
        return
    except Exception:
        st.error("No fue posible consultar contratos, PUC o revisiones en Sheets.")
        return

    portfolio = st.session_state["award_limits_contracts"]
    sources = st.session_state["capital_sources"]
    reviews = st.session_state["puc_historical_reviews"]
    if not portfolio.records:
        st.warning("No hay contratos analizados para ejecutar esta prueba.")
        return

    results = []
    rows = []
    for record in portfolio.records:
        puc = sources.puc_by_work.get(record.obra_id)
        review = latest_puc_review(reviews, record, puc)
        result = evaluate_puc_validity(record, sources, review)
        results.append((record, result, review))
        norm, _ = normalized_values(record)
        rows.append({
            "Carpeta": record.nombre_carpeta,
            "Contrato": norm.get("numero_contrato") or record.documento,
            "Contratista": norm.get("contratista") or "—",
            "Registro PUC": puc.registro if puc else "—",
            "Asignación (referencia)": result.assignment_date or "—",
            "Firma contrato": result.signature_date or "—",
            "Vigencia desde": result.period_from or "—",
            "Vigencia hasta": result.period_to or "—",
            "Comparación asignación": result.assignment_result,
            "Comparación firma": result.contract_result,
            "Resultado AD-03": result.state,
            "Conclusión del auditor": review.conclusion_auditor if review else "Sin revisión",
        })
    df = pd.DataFrame(rows)
    a, b, c = st.columns(3)
    a.metric("Contratos", len(df))
    b.metric("Compatibilidad preliminar", int(
        (df["Resultado AD-03"] == "Vigencia documental compatible (preliminar)").sum()
    ))
    c.metric("Pendientes / cotejo", int(
        (df["Resultado AD-03"] != "Vigencia documental compatible (preliminar)").sum()
    ))
    st.dataframe(df, hide_index=True, use_container_width=True)
    st.download_button(
        "Exportar verificación de vigencia PUC (CSV)",
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name="AuditorIA_AD03_Vigencia_PUC.csv", mime="text/csv",
        key="puc_validity_csv",
    )

    chosen = st.selectbox(
        "Contrato a revisar", list(range(len(results))),
        format_func=lambda i: (
            results[i][0].nombre_carpeta + " · "
            + (normalized_values(results[i][0])[0].get("numero_contrato")
               or results[i][0].documento)
        ),
        key="puc_validity_selected",
    )
    record, result, review = results[chosen]
    if result.state == "Vigencia documental compatible (preliminar)":
        st.success(result.state + " · Sujeto a cotejo del refrendo y fecha efectiva.")
    else:
        st.warning(result.state)
    st.table({
        "Dato": [
            "Fecha de asignación", "Fuente de fecha",
            "Fecha de firma del contrato", "Inicio del periodo acreditado",
            "Fin del periodo acreditado", "Fuente del periodo",
            "Estado en asignación", "Estado en firma", "Resultado",
        ],
        "Valor": [
            result.assignment_date or "—", result.assignment_source or "—",
            result.signature_date or "—", result.period_from or "—",
            result.period_to or "—", result.period_source or "—",
            result.assignment_result, result.contract_result, result.state,
        ],
    })
    if result.puc:
        with st.expander("Datos literales y evidencia del PUC", expanded=False):
            st.write("**Registro:**", result.puc.registro or "—")
            st.write("**Estado reportado:**", result.puc.estado_registro or "—")
            st.write("**Validación:**", result.puc.fecha_validacion or "—")
            st.write("**Impresión:**", result.puc.fecha_impresion or "—")
            st.write(
                "**Documento original:**",
                f"https://drive.google.com/file/d/{result.puc.documento_id}/view",
            )
    if review:
        st.caption(
            "Último cotejo manual: " + review.fecha_utc + " · " + review.auditor
            + " · Conclusión: " + review.conclusion_auditor
            + " · Soporte: " + review.referencia
        )
    if result.notes:
        with st.expander("Advertencias y aspectos por cotejar"):
            for note in result.notes:
                st.caption("• " + note)
    render_puc_history_form(
        record, result.puc, reviews, prefix="puc_validity"
    )
