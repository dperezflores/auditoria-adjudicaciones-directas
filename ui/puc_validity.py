"""Interfaz AD-03: fecha de firma frente al año de vigencia del PUC."""
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
        "Prueba AD-03 · Comparar fecha de firma contractual con el periodo anual "
        "de vigencia del PUC · Municipio de León."
    )
    st.info(
        "**Criterio de la prueba:** verificar si la fecha de firma está dentro "
        "del periodo del PUC. Cuando la cédula solo indica «Vigencia hasta», "
        "el inicio se calcula **exactamente un año calendario antes**. "
        "Las fechas calculadas se identifican y no modifican la extracción original."
    )
    if st.button("Actualizar contratos y PUC guardados", key="puc_validity_reload"):
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
        st.error("No fue posible consultar contratos o PUC en Google Sheets.")
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
            "Fecha firma contrato": result.signature_date or "—",
            "Vigencia desde": result.period_from or "—",
            "Inicio calculado": "Sí (un año antes)" if result.inferred_start else "No",
            "Vigencia hasta": result.period_to or "—",
            "Resultado AD-03": result.state,
        })

    df = pd.DataFrame(rows)
    a, b, c = st.columns(3)
    a.metric("Contratos evaluados", len(df))
    b.metric("Vigentes según periodo", int(
        (df["Resultado AD-03"] == "Vigente en fecha de firma").sum()
    ))
    c.metric("Fuera de periodo", int(
        (df["Resultado AD-03"] == "Fuera del periodo PUC en fecha de firma").sum()
    ))
    st.dataframe(df, hide_index=True, use_container_width=True)
    st.download_button(
        "Exportar verificación de vigencia PUC (CSV)",
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name="AuditorIA_AD03_Vigencia_PUC.csv", mime="text/csv",
        key="puc_validity_csv",
    )

    selected = st.selectbox(
        "Contrato a revisar", list(range(len(results))),
        format_func=lambda i: (
            results[i][0].nombre_carpeta + " · "
            + (normalized_values(results[i][0])[0].get("numero_contrato")
               or results[i][0].documento)
        ),
        key="puc_validity_selected",
    )
    record, result, review = results[selected]
    if result.state == "Vigente en fecha de firma":
        st.success(result.state)
    else:
        st.warning(result.state)
    st.table({
        "Dato": [
            "Fecha de firma del contrato",
            "Vigencia del PUC desde",
            "Vigencia del PUC hasta",
            "Origen del intervalo",
            "Resultado",
        ],
        "Valor": [
            result.signature_date or "—",
            result.period_from or "—",
            result.period_to or "—",
            result.period_source or "—",
            result.state,
        ],
    })
    if result.inferred_start:
        st.caption(
            "La fecha «Vigencia desde» es un cálculo del sistema (vencimiento "
            "menos un año calendario), no un dato transcrito del PDF."
        )
    if result.puc:
        with st.expander("Datos originales y evidencia del PUC"):
            st.write("**Registro:**", result.puc.registro or "—")
            st.write("**Estado reportado:**", result.puc.estado_registro or "—")
            st.write("**Inicio literal:**", result.puc.vigencia_desde or "No indicado")
            st.write("**Vencimiento literal:**", result.puc.vigencia_hasta or "No indicado")
            st.write("**Validación:**", result.puc.fecha_validacion or "—")
            st.write("**Impresión:**", result.puc.fecha_impresion or "—")
            st.write(
                "**Documento original:**",
                f"https://drive.google.com/file/d/{result.puc.documento_id}/view",
            )
    if review:
        st.caption(
            "Cotejo adicional registrado: " + review.fecha_utc + " · "
            + review.auditor + " · Conclusión del auditor: "
            + review.conclusion_vigencia + " · Soporte: " + review.referencia
        )
    if result.notes:
        with st.expander("Aspectos que requieren cotejo"):
            for note in result.notes:
                st.caption("• " + note)
    # Se conserva el formulario manual histórico ya existente como apoyo
    # opcional; NO es necesario usarlo para el cálculo automático AD-03.
    render_puc_history_form(record, result.puc, reviews, prefix="puc_validity")
