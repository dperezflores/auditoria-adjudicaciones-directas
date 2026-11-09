"""Dashboard ejecutivo: una obra entra al listado al extraer su contrato.

No se exploran carpetas ni se consulta Gemini. Fuente exclusiva Google Sheets:
Obras/Documentos sólo permiten validar vigencia y asociación; las columnas
visibles proceden de DatosContrato y de la extracción JSON original.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from decimal import Decimal
import pandas as pd
import plotly.express as px
import streamlit as st

from services.contract_portfolio import (
    FIELD_LABELS, ContractRecord,
    amount_summary, filter_contracts, money_text, read_contract_portfolio,
)
from services.sheets_service import create_sheets_client, storage_configured
from services.analysis_catalog import load_status_tables
from services.catalogo_xlsx import CATALOGO_SCHEMA_VERSION
from services.contract_v2 import FIELD_LABELS_V2
from services.contract_table import contract_table_rows
from ui.document_crosscheck import render_document_crosscheck


def _fetch_portfolio() -> None:
    client = create_sheets_client(st.secrets["gcp_service_account"])
    st.session_state["results_portfolio"] = read_contract_portfolio(
        client, st.secrets["storage"]["spreadsheet_id"]
    )
    tables = load_status_tables(client, st.secrets["storage"]["spreadsheet_id"])
    saved = {r["cache_key"]: r for r in tables["Extracciones"]}
    catalogs = {}
    for doc in tables["Documentos"]:
        if doc["tipo_documental"] != "CATALOGO" or doc["activo"] != "SI":
            continue
        entry = saved.get(doc["resultado_id"])
        if not entry or entry["version_esquema"] != CATALOGO_SCHEMA_VERSION:
            continue
        if entry["documento_id"] != doc["documento_id"] or entry["obra_id"] != doc["obra_id"]:
            continue
        if entry["estado"] != "COMPLETADO" or not entry["resultado_json"]:
            continue
        try:
            summary = json.loads(entry["resultado_json"])
            catalogs.setdefault(doc["obra_id"], []).append(summary)
        except (ValueError, TypeError):
            continue
    st.session_state["results_catalogs"] = catalogs
    st.session_state["results_last_read"] = (
        datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    st.session_state.pop("results_read_error", None)


def _view_table(records: tuple[ContractRecord, ...]) -> pd.DataFrame:
    """Listado horizontal completo, con selección interactiva por fila."""
    return pd.DataFrame(contract_table_rows(records))


def _filtered_download(records: tuple[ContractRecord, ...]) -> bytes:
    # Exportación congruente con todas las columnas visibles del dashboard.
    rows = contract_table_rows(records)
    for record, row in zip(records, rows):
        row["ID de obra"] = record.obra_id
        row["ID de documento"] = record.documento_id
        row["Versión de extracción"] = record.source_schema
        row["Fecha de extracción (UTC)"] = record.extracted_at
    return pd.DataFrame(rows).to_csv(index=False).encode("utf-8-sig")


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
    """Ficha reactiva al seleccionar una fila del listado contractual."""
    st.markdown("### Ficha del contrato seleccionado")
    st.write(record.values["nombre_obra"] or "Obra o servicio no localizado")
    st.caption(
        f"Número: {record.values['numero_contrato'] or 'No localizado'} · "
        f"Tipo de extracción: {record.source_schema} · "
        f"Campos con valor: {record.coverage} · "
        f"Estado: {record.status_label}"
    )

    general, people, legal, evidence_tab = st.tabs([
        "Datos contractuales", "Personas participantes",
        "Legislación y recursos", "Evidencias del PDF",
    ])
    with general:
        if record.full_values is not None:
            st.dataframe(
                pd.DataFrame([
                    {"Dato": label, "Texto literal del contrato": record.full_values.get(key) or "No localizado"}
                    for key, label in FIELD_LABELS_V2
                    if key not in ("legislacion_citada", "fuente_financiamiento")
                ]),
                hide_index=True, use_container_width=True,
                column_config={
                    "Dato": st.column_config.TextColumn(width="medium"),
                    "Texto literal del contrato": st.column_config.TextColumn(width="large"),
                },
            )
        else:
            st.info(
                "Este contrato fue extraído con una plantilla anterior. "
                "Los campos nuevos no se deducirán: puedes volver a analizar "
                "el contrato en Expedientes con la versión actual cuando sea necesario."
            )
            st.dataframe(
                pd.DataFrame([
                    {"Dato": label, "Valor previamente extraído": record.values.get(field) or "No localizado"}
                    for field, label in FIELD_LABELS
                ]), hide_index=True, use_container_width=True,
            )
        if record.missing_fields:
            labels = dict(FIELD_LABELS_V2) if record.full_values else dict(FIELD_LABELS)
            st.caption(
                "Campos no encontrados: " +
                ", ".join(labels.get(key, key) for key in record.missing_fields)
            )

    with people:
        if record.full_values is None:
            st.info("La plantilla anterior no conservaba la lista estructurada de participantes.")
        elif record.participants:
            st.dataframe(pd.DataFrame([
                {
                    "Nombre (literal)": row.get("nombre") or "",
                    "Cargo o carácter (literal)": row.get("cargo_o_caracter") or "No localizado",
                    "Representa a": row.get("representacion") or "No localizado",
                    "Página": row.get("pagina") if row.get("pagina") is not None else "—",
                    "Evidencia": row.get("evidencia") or "Sin evidencia",
                } for row in record.participants
            ]), hide_index=True, use_container_width=True)
        else:
            st.info("No se identificaron personas participantes en la extracción.")

    with legal:
        if record.full_values is None:
            st.info("Este campo no estaba disponible en la plantilla anterior.")
        else:
            st.write("**Fuente de financiamiento — texto del contrato**")
            st.write(record.full_values.get("fuente_financiamiento") or "No localizado")
            st.write("**Legislación o fundamento citado — texto del contrato**")
            st.write(record.full_values.get("legislacion_citada") or "No localizado")
            st.write("**Ámbito identificado preliminarmente (no es transcripción literal)**")
            st.info(record.normative_scope)
            st.caption(
                "La legislación citada no determina por sí sola el límite "
                "de adjudicación. Deben verificarse recursos, ejercicio fiscal, "
                "ente contratante y normas aplicables. Sin prueba legal automática."
            )

    with evidence_tab:
        st.caption(
            "La evidencia y el número de página son referencias propuestas por IA. "
            "Los textos se conservan sin normalizar."
        )
        fields = FIELD_LABELS_V2 if record.full_values is not None else FIELD_LABELS
        details = []
        for field, label in fields:
            source = record.evidence.get(field) or {}
            page = source.get("pagina")
            details.append({
                "Dato": label,
                "Valor literal": (
                    (record.full_values or {}).get(field) if record.full_values is not None
                    else record.values.get(field)
                ) or "No localizado",
                "Página": str(page) if isinstance(page, int) else "—",
                "Evidencia": source.get("evidencia") or "Sin evidencia conservada",
            })
        st.dataframe(pd.DataFrame(details), hide_index=True, use_container_width=True)
        if record.observations:
            st.markdown("**Observaciones de extracción**")
            for item in record.observations:
                st.write("• " + item)
        st.caption("Fecha de extracción UTC: " + (record.extracted_at or "No disponible"))
        st.link_button(
            "Abrir contrato en Google Drive",
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
        "La suma reúne importes extraídos de los contratos, sin ajustes ni validación de auditoría."
    )

    st.markdown("#### Listado de obras y contratos")
    st.caption(
        f"{len(filtered)} contrato(s) en el conjunto filtrado. "
        "Las modalidades y las fechas se muestran normalizadas (DD/MM/AAAA). "
        "El importe contractual aparece en una sola columna con formato moneda, "
        "tal como fue extraído, sin cálculos adicionales. "
        "Desplázate horizontalmente y selecciona una fila para ver el texto original."
    )
    st.caption(
        "La normalización es únicamente visual y no modifica los datos extraídos. "
        "Cuando el monto no pueda interpretarse inequívocamente, aparecerá —. "
        "Consulta siempre el contrato original antes de formular observaciones."
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
            "Obra o servicio": st.column_config.TextColumn(width="large"),
            "Número de contrato": st.column_config.TextColumn(width="medium"),
            "Contratista (nombre o razón social)": st.column_config.TextColumn(width="large"),
            "Monto del contrato": st.column_config.TextColumn(width="medium"),
            "Personas que participan en el contrato": st.column_config.TextColumn(width="large"),
            "Legislación citada en el contrato": st.column_config.TextColumn(width="large"),
        },
    )

    st.download_button(
        "Exportar listado filtrado (CSV)",
        data=_filtered_download(filtered),
        file_name="AuditorIA_contratos_extraidos.csv",
        mime="text/csv",
        key="results_download",
    )

    selected_rows = event.selection.rows
    chosen_index = selected_rows[0] if selected_rows else 0
    if chosen_index < 0 or chosen_index >= len(filtered):
        chosen_index = 0
    st.caption(
        "Al seleccionar otra fila de la tabla, la ficha inferior cambia "
        "automáticamente sin volver a ejecutar IA."
    )
    chosen_contract = filtered[chosen_index]
    _render_details(chosen_contract)
    for summary in st.session_state.get("results_catalogs", {}).get(chosen_contract.obra_id, []):
        st.markdown("#### Catálogo original de la obra (Excel, sin IA)")
        a, b, c = st.columns(3)
        a.metric("Conceptos contratados", summary["conceptos_originales"])
        b.metric("Conceptos fuera de catálogo excluidos", summary["excluidos_fuera_catalogo"])
        c.metric("Importe inicial calculado sin IVA", summary["importe_original_calculado_sin_iva"])
        if summary.get("claves_repetidas", 0):
            st.info(
                f"{summary['claves_repetidas']} clave(s) utilizadas en "
                f"{summary['renglones_con_clave_repetida']} renglones. "
                "Se mantuvieron por capítulo y fila de origen."
            )
        st.caption("Fuente: CATALOGO.xlsx · Cantidad Inicial × Precio U. "
                   "No se incluyen excedentes ni conceptos extraordinarios. "
                   "Consultar detalle y filas en Expedientes.")
    st.divider()
    render_document_crosscheck(chosen_contract, portfolio.supporting_documents)
    st.divider()
    _render_aggregate_visuals(filtered)
    st.caption(
        "Los resultados son extracciones documentales. "
        "La valoración de cumplimiento, hallazgos y riesgos será materia "
        "del módulo de Pruebas de adjudicación."
    )
