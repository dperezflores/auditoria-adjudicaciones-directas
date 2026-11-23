"""Pantalla CC-01: capital contable 30 % en el PUC, por contrato de León.

Cálculos y citas guardados, nunca llamadas a Gemini ni escrituras automáticas.
"""
from __future__ import annotations

import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from services.award_limits import money
from services.capital_contable import (
    MANUAL_CODE, MANUAL_URL, CapitalSourceError,
    evaluate_capital, read_capital_sources,
)
from services.work_groups import ALL_GROUPS, selected_records
from services.contract_verifications import read_verified_portfolio
from services.contract_normalization import normalized_values
from services.capital_risk_chart import (
    CapitalDeficit, contract_selection_key, selected_deficit_record,
    undercapitalized_contracts,
)
from services.puc_history import (
    PucHistoryError, latest_puc_review, read_puc_reviews,
)
from ui.puc_history_form import render_puc_history_form
from services.drive_service import create_drive_client
from services.sheets_service import create_sheets_client
from ui.contract_verification import render_verification_form


_TABLE_KEY = "capital_selectable_work_table"
_CHART_KEY = "capital_deficit_selectable_chart"
_SELECTED_KEY = "capital_active_contract_key"


def _select_capital_from_table(contract_keys: tuple[str, ...]) -> None:
    """La fila del listado actualiza la misma ficha que el gráfico."""
    event = st.session_state.get(_TABLE_KEY) or {}
    rows = (event.get("selection") or {}).get("rows") or []
    if rows and isinstance(rows[0], int) and 0 <= rows[0] < len(contract_keys):
        st.session_state[_SELECTED_KEY] = contract_keys[rows[0]]


def _select_capital_from_chart(valid_keys: tuple[str, ...]) -> None:
    """La barra usa su ID de contrato, no el nombre repetible del contratista."""
    event = st.session_state.get(_CHART_KEY) or {}
    selected_key = selected_deficit_record(event, valid_keys)
    if selected_key:
        st.session_state[_SELECTED_KEY] = selected_key


def _render_capital_deficit_chart(
    deficits: tuple[CapitalDeficit, ...],
) -> None:
    st.markdown("#### Contratos que no cubren el 30 % del capital")
    if not deficits:
        st.info(
            "No se identificaron contratos con capital inferior al 30 % "
            "entre los importes comparables. Los expedientes pendientes "
            "de importe o PUC se revisan en la tabla general."
        )
        return

    st.caption(
        "Cada barra representa **un contrato**, incluso cuando un mismo "
        "contratista tiene varias obras. Su longitud indica el capital "
        "**faltante en pesos** para alcanzar el 30 %. "
        "**Haz clic en una barra** para cargar la ficha y las evidencias "
        "de esa obra abajo, igual que al seleccionar su fila en la tabla."
    )
    total_deficit = sum((item.faltante for item in deficits), start=0)
    a, b = st.columns(2)
    a.metric("Contratos con déficit", len(deficits))
    b.metric("Suma de faltantes por contrato", money(total_deficit))

    labels = [
        (
            item.contratista[:39] + ("…" if len(item.contratista) > 39 else "")
            + " · " + item.contrato[:25]
        )
        for item in deficits
    ]
    fig = go.Figure(go.Bar(
        x=[float(item.faltante) for item in deficits],
        y=list(range(len(deficits))),
        orientation="h",
        customdata=[
            [
                item.record_key, item.contratista, item.contrato,
                item.carpeta, float(item.capital), float(item.minimo),
                str(item.cobertura) if item.cobertura is not None else "—",
                item.vigencia, item.resultado,
            ] for item in deficits
        ],
        hovertemplate=(
            "<b>%{customdata[1]}</b>"
            "<br>Contrato: %{customdata[2]}"
            "<br>Carpeta: %{customdata[3]}"
            "<br>Capital evaluado: $%{customdata[4]:,.2f}"
            "<br>Mínimo requerido: $%{customdata[5]:,.2f}"
            "<br><b>Faltante: $%{x:,.2f}</b>"
            "<br>Cobertura contractual: %{customdata[6]} %"
            "<br>PUC a la firma: %{customdata[7]}"
            "<br>Resultado: %{customdata[8]}"
            "<extra></extra>"
        ),
    ))
    fig.update_layout(
        height=max(350, 105 + 42 * len(deficits)),
        margin=dict(l=20, r=60, t=25, b=50),
        clickmode="event+select",
        dragmode=False,
        showlegend=False,
    )
    fig.update_xaxes(
        title_text="Capital faltante para alcanzar el 30 % (MXN)",
        tickprefix="$", tickformat=",.0f", rangemode="tozero",
    )
    fig.update_yaxes(
        tickmode="array", tickvals=list(range(len(deficits))),
        ticktext=labels, autorange="reversed",
    )
    valid_keys = tuple(item.record_key for item in deficits)
    if len(deficits) > 18:
        with st.container(height=860, border=False):
            st.plotly_chart(
                fig, width="stretch",
                key=_CHART_KEY, selection_mode="points",
                on_select=lambda: _select_capital_from_chart(valid_keys),
                alt="Gráfico de barras seleccionables del déficit de capital por contrato",
            )
    else:
        st.plotly_chart(
            fig, width="stretch",
            key=_CHART_KEY, selection_mode="points",
            on_select=lambda: _select_capital_from_chart(valid_keys),
            alt="Gráfico de barras seleccionables del déficit de capital por contrato",
        )
    st.caption(
        "Incluye déficits aritméticos aunque la vigencia o identidad del PUC "
        "requiera cotejo; consulta el estado CC-01 en la ficha seleccionada. "
        "El gráfico señala riesgos para auditoría, no incumplimientos definitivos."
    )


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
    scoped = selected_records(
        portfolio.records, st.session_state.get("work_groups_catalog"),
        st.session_state.get("work_group_selection", ALL_GROUPS),
    )
    if not scoped:
        st.info("No hay contratos analizados en el grupo seleccionado.")
        return
    results=[
        (record,evaluate_capital(
            record,sources,latest_puc_review(
                revisions,record,sources.puc_by_work.get(record.obra_id)
            )
        )) for record in scoped
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
    contract_keys = tuple(contract_selection_key(record) for record, _ in results)
    selected_key = st.session_state.get(_SELECTED_KEY)
    if selected_key not in contract_keys:
        selected_key = contract_keys[0]
        st.session_state[_SELECTED_KEY] = selected_key
    deficits = undercapitalized_contracts(results)
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
    _render_capital_deficit_chart(deficits)
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
    # El indicador en la tabla también sigue las selecciones del gráfico.
    display_df = df.copy()
    display_df.insert(0, "Seleccionada", [
        "●" if key == st.session_state[_SELECTED_KEY] else ""
        for key in contract_keys
    ])
    table_event = st.dataframe(
        display_df, hide_index=True, use_container_width=True,
        height=min(520, 85 + len(df) * 38),
        selection_mode="single-row",
        on_select=lambda: _select_capital_from_table(contract_keys),
        key="capital_selectable_work_table",
    )
    selected_rows = table_event.selection.rows
    selected_key = st.session_state.get(_SELECTED_KEY)
    selected = contract_keys.index(selected_key) if selected_key in contract_keys else 0
    st.download_button(
        "Exportar resultados de capital contable (CSV)",
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name="AuditorIA_CC01_Capital_Contable.csv",
        mime="text/csv",key="capital_csv",
    )

    st.markdown("#### Datos de la obra seleccionada")
    record,result=results[selected]
    st.caption(
        f"**Obra:** {record.nombre_carpeta} · **Contrato:** "
        f"{normalized_values(record)[0].get('numero_contrato') or record.documento}"
    )
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
