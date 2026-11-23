"""Pantalla CC-01: capital contable 30 % en el PUC, por contrato de León.

Cálculos y citas guardados, nunca llamadas a Gemini ni escrituras automáticas.
"""
from __future__ import annotations

import re

import pandas as pd
import streamlit as st

from services.award_limits import money
from services.capital_contable import (
    MANUAL_CODE, MANUAL_URL, CapitalSourceError,
    evaluate_capital, read_capital_sources,
)
from services.contract_verifications import read_verified_portfolio
from services.contract_normalization import normalized_values
from services.puc_history import (
    PucHistoryError, latest_puc_review, read_puc_reviews,
)
from ui.puc_history_form import render_puc_history_form
from services.drive_service import create_drive_client
from services.sheets_service import create_sheets_client
from ui.contract_verification import render_verification_form


def _load_capital_data():
    sheets=create_sheets_client(dict(st.secrets["gcp_service_account"]))
    return read_capital_sources(sheets,st.secrets["storage"]["spreadsheet_id"])


def _load_portfolio():
    sheets=create_sheets_client(dict(st.secrets["gcp_service_account"]))
    return read_verified_portfolio(sheets,st.secrets["storage"]["spreadsheet_id"])


def _load_puc_reviews():
    sheets=create_sheets_client(dict(st.secrets["gcp_service_account"]))
    return read_puc_reviews(sheets,st.secrets["storage"]["spreadsheet_id"])


def render_capital_test() -> None:
    st.markdown("### Verificación de capital contable")
    st.caption(
        "Prueba CC-01 · Adjudicación directa de obra o servicios · Municipio de León."
    )
    st.info(
        f"**Revisión masiva CC-01:** {MANUAL_CODE}. Se utiliza la **fecha de "
        "firma del contrato como referencia operativa de asignación**. "
        "Primero se comprueba que el PUC esté vigente en esa fecha y después "
        "se compara el capital de la cédula con el **30 % del monto contractual**. "
        "El historial de movimientos de capital ante SOP se solicitará como "
        "verificación complementaria, no como requisito para clasificar cada obra."
    )
    st.link_button("Consultar procedimiento DGOP León (fuente)", MANUAL_URL)
    st.caption(
        "Base del 30 %: importe contractual total como consta en el contrato "
        "(sin deducir el IVA). Si el contrato no indica IVA, se conserva el "
        "criterio provisional de IVA incluido del piloto; NO se resta 16 % "
        "para calcular el capital. Las discrepancias fiscales requieren revisión."
    )
    if st.button("Actualizar contratos y PUC guardados",key="capital_reload"):
        st.session_state.pop("capital_sources",None)
        st.session_state.pop("award_limits_contracts",None)
        st.session_state.pop("puc_historical_reviews",None)
        st.rerun()

    if "award_limits_contracts" not in st.session_state:
        try:
            with st.spinner("Leyendo contratos y verificaciones guardadas..."):
                st.session_state["award_limits_contracts"]=_load_portfolio()
        except Exception:
            st.error("No se pudo consultar el registro de contratos y verificaciones.")
            return
    if "capital_sources" not in st.session_state:
        try:
            with st.spinner("Leyendo los PUC y dictámenes disponibles en Sheets..."):
                st.session_state["capital_sources"]=_load_capital_data()
        except CapitalSourceError as exc:
            st.error("No fue posible comprobar las tablas de PUC: "+str(exc))
            return
        except Exception:
            st.error(
                "No se pudieron consultar las extracciones de PUC y dictamen. "
                "Verifica el acceso de la cuenta de servicio a Google Sheets."
            )
            return

    if "puc_historical_reviews" not in st.session_state:
        try:
            st.session_state["puc_historical_reviews"]=_load_puc_reviews()
        except PucHistoryError as exc:
            st.error("Historial del PUC: "+str(exc))
            return
        except Exception:
            st.error("No se pudieron consultar las revisiones históricas del PUC.")
            return

    portfolio=st.session_state["award_limits_contracts"]
    sources=st.session_state["capital_sources"]
    revisions=st.session_state["puc_historical_reviews"]
    if not portfolio.records:
        st.warning("No existen contratos analizados para realizar la prueba.")
        return
    results=[
        (record,evaluate_capital(
            record,sources,latest_puc_review(
                revisions,record,sources.puc_by_work.get(record.obra_id)
            )
        )) for record in portfolio.records
    ]
    rows=[]
    for record,result in results:
        normalized,_=normalized_values(record)
        puc=result.puc
        rows.append({
            "Carpeta":record.nombre_carpeta,
            "Contrato":normalized.get("numero_contrato") or record.documento,
            "Contratista":normalized.get("contratista") or "—",
            "Modalidad":normalized.get("modalidad_adjudicacion") or "—",
            "Monto contractual total":money(result.contract_amount),
            "Capital mínimo 30%":money(result.requirement),
            "Capital de cédula PUC":money(result.capital_constancia),
            "Capital evaluado":money(result.capital),
            "Soporte histórico SOP":(
                "Documentado" if result.capital_historico_acreditado
                else "Complementario / opcional"
            ),
            "Diferencia capital":money(result.difference),
            "Capital / contrato (%)":(
                f"{result.coverage:.2f}%" if result.coverage is not None else "—"
            ),
            "Comparación 30%":result.comparison,
            "Vigencia PUC a la firma":result.vigencia_puc or "—",
            "Vigencia desde":result.vigencia_desde or "—",
            "Vigencia hasta":result.vigencia_hasta or "—",
            "Resultado CC-01":result.state,
            "Firma / asignación operativa":(
                result.assignment.fecha if result.assignment else "—"
            ),
            "Registro PUC":puc.registro if puc else "—",
            "Cotejo complementario SOP":result.historical,
        })

    df=pd.DataFrame(rows)
    states=df["Resultado CC-01"].value_counts()
    a,b,c,d=st.columns(4)
    a.metric("Contratos",len(df))
    b.metric("Cubren 30% y PUC vigente",int(
        df["Resultado CC-01"].str.startswith("Cubre el 30%").sum()
    ))
    c.metric("Capital inferior al 30%",int(
        df["Resultado CC-01"].str.startswith("Capital inferior al 30%").sum()
    ))
    d.metric("Pendientes o por revisar",int(
        (~df["Resultado CC-01"].str.startswith(
            ("Cubre el 30%", "Capital inferior al 30%")
        )).sum()
    ))
    st.markdown("#### Evaluación automática del capital contable")
    st.caption(
        "Clasificación inicial: PUC vigente a fecha de firma + capital de "
        "cédula frente al 30 %. El cotejo ante SOP sobre cambios de capital "
        "durante la vigencia se reserva para la revisión complementaria."
    )
    st.caption(
        "Selecciona una fila para ver abajo el detalle del capital, "
        "las evidencias del PUC y los formularios de revisión de esa obra."
    )
    table_event = st.dataframe(
        df, hide_index=True, use_container_width=True,
        height=min(520, 85 + len(df) * 38),
        selection_mode="single-row", on_select="rerun",
        key="capital_selectable_work_table",
    )
    selected_rows = table_event.selection.rows
    selected = selected_rows[0] if selected_rows else 0
    if not 0 <= selected < len(results):
        selected = 0
    st.download_button(
        "Exportar resultados de capital contable (CSV)",
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name="AuditorIA_CC01_Capital_Contable.csv",
        mime="text/csv",key="capital_csv",
    )

    st.markdown("#### Datos de la obra seleccionada")
    record,result=results[selected]
    normalized,_=normalized_values(record)
    if result.state == "Pendiente de PUC":
        st.warning(
            "No hay una cédula PUC analizada y vinculada con esta obra. "
            "Analiza el PUC en Expedientes para completar esta prueba."
        )
    elif result.state.startswith("Cubre el 30%"):
        st.success(
            "Cubre el 30 % y el PUC está vigente a la fecha de firma. "
            "Resultado de revisión masiva inicial; el historial de cambios "
            "de capital ante SOP podrá corroborarse después."
        )
    elif result.state.startswith("Capital inferior al 30%"):
        st.error(
            "El capital evaluado es inferior al 30 % requerido. "
            "Es una señal de riesgo para cotejo con el expediente y la SOP, "
            "no una determinación definitiva de incumplimiento."
        )
    elif result.state == "PUC fuera de vigencia en fecha de firma":
        st.warning(
            "La fecha de firma está fuera del periodo de esta cédula PUC. "
            "Verifica otros refrendos o antecedentes antes de concluir falta de vigencia."
        )
    else:
        st.warning(
            result.state + ". Verifica los datos señalados para completar "
            "la revisión masiva; la comparación aritmética es: "
            + result.comparison + "."
        )
    st.table({
        "Dato":[
            "Carpeta","Contratista","Número de contrato",
            "Monto total del contrato","30 % requerido",
            "Capital de cédula PUC","Capital evaluado","Diferencia",
            "Porcentaje de cobertura","Comparación aritmética",
            "Firma / asignación operativa", "Vigencia PUC desde",
            "Vigencia PUC hasta","Estado vigencia a la firma",
            "Seguimiento histórico SOP",
        ],
        "Valor":[
            record.nombre_carpeta,normalized.get("contratista") or "—",
            normalized.get("numero_contrato") or "—",
            money(result.contract_amount),money(result.requirement),
            money(result.capital_constancia),money(result.capital),money(result.difference),
            f"{result.coverage:.2f}%" if result.coverage is not None else "—",
            result.comparison,
            result.assignment.fecha if result.assignment else "—",
            result.vigencia_desde or "—",
            result.vigencia_hasta or "—",
            result.vigencia_puc or "—",
            result.historical,
        ],
    })
    puc=result.puc
    if puc:
        with st.expander("Evidencia documental del PUC",expanded=True):
            st.write("**Contratista registrado:**",puc.nombre or "—")
            st.write("**RFC del PUC:**",puc.rfc or "—")
            st.write("**Registro:**",puc.registro or "—")
            st.write("**Capital literal:**",puc.capital_text or "No identificado")
            st.write("**Estado del registro:**",puc.estado_registro or "No consta")
            st.write(
                "**Fechas:** Validación: "
                + (puc.fecha_validacion or "—")
                + " · Impresión: "+(puc.fecha_impresion or "—")
                + " · Vigencia hasta: "+(puc.vigencia_hasta or "—")
            )
            st.write("**Página:**",puc.capital_page or "Sin identificar")
            st.write(
                "**Cita del capital:**",puc.capital_evidence
                or "No se guardó evidencia textual suficiente."
            )
            if re.fullmatch(r"[A-Za-z0-9_-]{10,}",puc.documento_id):
                st.link_button(
                    "Abrir PUC original en Drive",
                    f"https://drive.google.com/file/d/{puc.documento_id}/view",
                )
    if result.assignment:
        st.caption(
            "Referencia temporal: "+result.assignment.fuente+
            " · "+(result.assignment.fecha or "sin fecha")
            +". Esta prueba inicial equipara firma y asignación; "
            "la fecha efectiva se verificará en una etapa complementaria."
        )
    if result.notes:
        with st.expander("Aspectos para cotejo complementario", expanded=False):
            for note in dict.fromkeys(result.notes):
                st.caption("• "+note)
    if result.revision:
        st.caption(
            "Revisión histórica: "+result.revision.fecha_utc+" · "+
            result.revision.auditor+" · Conclusión del auditor: "+
            result.revision.conclusion_capital+" · Soporte: "+
            result.revision.referencia
        )
    render_puc_history_form(record,result.puc,revisions,prefix="capital")
    render_verification_form(record,prefix="capital")
    st.caption(
        "Las correcciones del contrato se guardan mediante el formulario "
        "compartido con Resultados y AD-06. El PUC y sus evidencias se "
        "mantienen literales, sin reanálisis con Gemini."
    )
