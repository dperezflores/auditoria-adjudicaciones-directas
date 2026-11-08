"""Dashboard ejecutivo: una obra entra al listado al extraer su contrato.

No se exploran carpetas ni se consulta Gemini. Fuente exclusiva Google Sheets:
Obras/Documentos sólo permiten validar vigencia y asociación; las columnas
visibles proceden de DatosContrato y de la extracción JSON original.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pandas as pd
import plotly.express as px
import streamlit as st

from services.contract_portfolio import (
    DATA_FIELDS, FIELD_LABELS, ContractRecord,
    amount_summary, filter_contracts, money_text, read_contract_portfolio,
)
from services.sheets_service import create_sheets_client, storage_configured


def _fetch_portfolio() -> None:
    client = create_sheets_client(st.secrets["gcp_service_account"])
    st.session_state["results_portfolio"] = read_contract_portfolio(
        client, st.secrets["storage"]["spreadsheet_id"]
    )
    st.session_state["results_last_read"] = (
        datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    st.session_state.pop("results_read_error", None)


def _view_table(records: tuple[ContractRecord, ...]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "Obra": r.values["nombre_obra"] or "Sin nombre extraído",
            "Contrato": r.values["numero_contrato"] or "Sin número",
            "Contratista": r.values["contratista"] or "No identificado",
            "Monto con IVA": r.values["monto_con_iva"] or "No localizado",
            "Anticipo": r.values["porcentaje_anticipo"] or "No localizado",
            "Año de firma": r.signature_year,
            "Campos": r.coverage,
            "Estado": r.status_label,
        }
        for r in records
    ])


def _filtered_download(records: tuple[ContractRecord, ...]) -> bytes:
    rows = [{
        "obra_id": r.obra_id,
        "documento_id": r.documento_id,
        **{field: r.values[field] for field in DATA_FIELDS},
        "estado_extraccion": r.status_label,
        "campos_recuperados": r.completeness,
        "fecha_extraccion_utc": r.extracted_at,
    } for r in records]
    table = pd.DataFrame(rows)
    return table.to_csv(index=False).encode("utf-8-sig")


def _render_aggregate_visuals(records: tuple[ContractRecord, ...]) -> None:
    """Comparativos sólo cuando existen datos suficientes y comparables."""
    if len(records) < 2:
        return
    st.markdown("#### Comparativos del conjunto filtrado")
    amounts = [r for r in records if r.amount is not None]
    if len(amounts) >= 2 and len({r.currency for r in amounts}) == 1:
        grouped: dict[str, Decimal] = {}
        for r in amounts:
            key = r.values["contratista"] or "Sin contratista"
            grouped[key] = grouped.get(key, Decimal("0")) + (r.amount or Decimal("0"))
        if len(grouped) >= 2:
            df = pd.DataFrame([
                {"Contratista": name, "Monto": float(amount)}
                for name, amount in grouped.items()
            ]).sort_values("Monto")
            chart = px.bar(
                df, x="Monto", y="Contratista", orientation="h",
                labels={"Monto": "Monto extraído (sin validación)", "Contratista": ""},
                title="Importe por contratista",
            )
            chart.update_layout(
                margin=dict(l=5, r=10, t=50, b=10),
                height=max(300, min(520, 95 + 55 * len(df))),
                showlegend=False,
            )
            st.plotly_chart(chart, use_container_width=True)
    by_year: dict[str, int] = {}
    for r in records:
        if r.signature_year != "Sin año":
            by_year[r.signature_year] = by_year.get(r.signature_year, 0) + 1
    if len(by_year) >= 2:
        st.bar_chart(
            pd.DataFrame([
                {"Año de firma": year, "Contratos": count}
                for year, count in sorted(by_year.items())
            ]).set_index("Año de firma"),
            y="Contratos",
            use_container_width=True,
        )


def _render_details(record: ContractRecord) -> None:
    st.markdown("### Ficha del contrato")
    st.markdown(f"**{record.values['nombre_obra'] or 'Obra sin nombre identificado'}**")
    st.caption(
        f"Contrato: {record.values['numero_contrato'] or 'Sin número'} · "
        f"Estado: {record.status_label} · "
        f"Datos recuperados: {record.coverage}"
    )
    left, right = st.columns([1, 1], gap="large")
    with left:
        st.write("**Contratista**")
        st.write(record.values["contratista"] or "No identificado")
        st.write("**Fecha de firma**")
        st.write(record.values["fecha_firma"] or "No localizada")
        st.write("**Inicio de ejecución**")
        st.write(record.values["fecha_inicio"] or "No localizado")
    with right:
        st.write("**Monto contractual con IVA**")
        st.write(record.values["monto_con_iva"] or "No localizado")
        st.write("**Anticipo**")
        st.write(record.values["porcentaje_anticipo"] or "No localizado")
        st.write("**Término de ejecución**")
        st.write(record.values["fecha_termino"] or "No localizado")

    if record.missing_fields:
        labels = dict(FIELD_LABELS)
        st.warning(
            "Datos no localizados: " +
            ", ".join(labels[field] for field in record.missing_fields) +
            ". No deben suponerse valores."
        )

    with st.expander("Ver trazabilidad y evidencias extraídas", expanded=False):
        st.caption(
            "Las páginas y los fragmentos siguientes provienen del análisis "
            "automático; deben cotejarse con el contrato."
        )
        details = []
        for field, label in FIELD_LABELS:
            source = record.evidence.get(field) or {}
            page = source.get("pagina")
            evidence = source.get("evidencia")
            details.append({
                "Dato": label,
                "Valor registrado": record.values.get(field) or "No localizado",
                "Página propuesta": str(page) if isinstance(page, int) else "—",
                "Fragmento de evidencia": evidence or "Sin evidencia conservada",
            })
        st.dataframe(
            pd.DataFrame(details), hide_index=True, use_container_width=True,
            column_config={
                "Dato": st.column_config.TextColumn(width="medium"),
                "Fragmento de evidencia": st.column_config.TextColumn(width="large"),
            },
        )
        if record.observations:
            st.markdown("**Notas de la extracción**")
            for item in record.observations:
                st.write(f"• {item}")
        st.caption("Fecha del análisis (UTC): " + (record.extracted_at or "No disponible"))
        if record.documento_id:
            st.link_button(
                "Consultar contrato original en Drive",
                f"https://drive.google.com/file/d/{record.documento_id}/view",
            )


def render_results() -> None:
    st.title("Resultados")
    st.caption("Panorama de obras y contratos construido con datos extraídos por IA.")
    if not storage_configured(st.secrets):
        st.error("La conexión con Google Sheets todavía no está configurada.")
        return

    _, top_right = st.columns([4, 1])
    with top_right:
        refresh = st.button(
            "Actualizar datos", key="results_refresh",
            type="primary", use_container_width=True,
        )
    if refresh or "results_portfolio" not in st.session_state:
        try:
            with st.spinner("Consultando los datos contractuales registrados..."):
                _fetch_portfolio()
        except Exception:
            st.session_state.pop("results_portfolio", None)
            st.session_state["results_read_error"] = (
                "No fue posible obtener un listado contractual consistente "
                "de Google Sheets. Verifica sus encabezados y permisos."
            )
    if st.session_state.get("results_read_error"):
        st.error(st.session_state["results_read_error"])
        return

    portfolio = st.session_state["results_portfolio"]
    st.caption(
        "Fuente: Google Sheets · Última consulta: " +
        st.session_state.get("results_last_read", "No disponible") + " UTC"
    )
    if not portfolio.records:
        st.info(
            "Todavía no hay contratos activos con datos extraídos. "
            "Cuando analices el primer contrato en Expedientes, su obra aparecerá aquí."
        )
        return

    st.markdown("#### Explorar contratos")
    filter1, filter2, filter3, filter4 = st.columns([2.5, 1, 1.6, 1.5])
    with filter1:
        search = st.text_input(
            "Buscar",
            placeholder="Obra, número de contrato o contratista",
            key="results_search",
        )
    with filter2:
        years = sorted(
            {r.signature_year for r in portfolio.records},
            reverse=True,
        )
        year = st.selectbox(
            "Año de firma", ["Todos", *years], key="results_year",
        )
    with filter3:
        contractors = sorted({
            r.values["contratista"] for r in portfolio.records
            if r.values["contratista"]
        })
        contractor = st.selectbox(
            "Contratista", ["Todos", *contractors], key="results_contractor",
        )
    with filter4:
        states = sorted({r.status_label for r in portfolio.records})
        state = st.selectbox(
            "Estado de extracción", ["Todos", *states], key="results_state",
        )

    filtered = filter_contracts(
        portfolio, query=search, year=year,
        contractor=contractor, status=state,
    )

    total, amount_note, _ = amount_summary(filtered)
    currencies = {r.currency for r in filtered if r.amount is not None}
    currency = next(iter(currencies)) if len(currencies) == 1 else ""
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Obras con contrato", len({r.obra_id for r in filtered}))
    col2.metric("Contratos extraídos", len(filtered))
    col3.metric("Monto identificado", money_text(total, currency) if total is not None else "—")
    col4.metric("Campos sin dato", sum(len(r.missing_fields) for r in filtered))
    st.caption(
        f"Indicadores correspondientes a los filtros actuales. {amount_note} "
        "Los importes no constituyen montos auditados."
    )

    st.markdown("#### Listado de obras y contratos")
    st.caption(
        f"{len(filtered)} contrato(s) en el conjunto filtrado. "
        "Selecciona una fila para consultar fechas, datos completos y evidencias."
    )
    if not filtered:
        st.info("Ningún contrato coincide con los filtros.")
        return

    event = st.dataframe(
        _view_table(filtered),
        hide_index=True,
        use_container_width=True,
        height=min(520, 80 + len(filtered) * 38),
        selection_mode="single-row",
        on_select="rerun",
        key="results_contract_table",
        column_config={
            "Obra": st.column_config.TextColumn(width="large"),
            "Contrato": st.column_config.TextColumn(width="medium"),
            "Contratista": st.column_config.TextColumn(width="large"),
            "Monto con IVA": st.column_config.TextColumn(width="medium"),
            "Estado": st.column_config.TextColumn(width="medium"),
        },
    )

    st.download_button(
        "Exportar listado filtrado (CSV)",
        data=_filtered_download(filtered),
        file_name="AuditorIA_contratos_extraidos.csv",
        mime="text/csv",
        key="results_download",
    )

    _render_aggregate_visuals(filtered)
    st.divider()
    selected_rows = event.selection.rows
    chosen_index = selected_rows[0] if selected_rows else 0
    if chosen_index < 0 or chosen_index >= len(filtered):
        chosen_index = 0
    _render_details(filtered[chosen_index])
    st.caption(
        "Los resultados son extracciones documentales. "
        "La valoración de cumplimiento, hallazgos y riesgos será materia "
        "del módulo de Pruebas de adjudicación."
    )
