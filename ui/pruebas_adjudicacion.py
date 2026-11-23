"""Nueva prueba independiente: verificación de límites por importe 2021–2026.

No ejecuta Gemini ni modifica los datos guardados, y no afecta AD-01…AD-05.
"""
from __future__ import annotations

from urllib.parse import urlparse

import pandas as pd
import streamlit as st

from services.award_limits import (
    Catalog, LimitsError, PILOT_MUNICIPALITY, evaluate,
    infer_regime, money, read_drive_catalog, year_from_date,
)
from services.contract_verifications import read_verified_portfolio
from services.contract_normalization import normalized_values, verified_fields
from ui.contract_verification import render_verification_form
from ui.capital_contable import render_capital_test
from ui.puc_validity import render_puc_validity_test
from services.amount_iva import identify_record_iva
from services.drive_service import create_drive_client, is_configured
from services.sheets_service import create_sheets_client, storage_configured


def _source_link(url: str) -> None:
    parsed = urlparse(url or "")
    host = (parsed.hostname or "").lower()
    if parsed.scheme == "https" and (
        host == "congresogto.gob.mx"
        or host == "www.congresogto.gob.mx"
        or host == "finanzas.guanajuato.gob.mx"
        or host == "transparencia.guanajuato.gob.mx"
        or host.endswith(".congresogto.gob.mx")
        or host == "congreso-gto.s3.amazonaws.com"
    ):
        st.link_button("Consultar referencia oficial", url)


def _load_catalog() -> Catalog:
    drive = create_drive_client(dict(st.secrets["gcp_service_account"]))
    return read_drive_catalog(drive, st.secrets["drive"]["root_folder_id"])


def _load_contracts():
    sheets = create_sheets_client(dict(st.secrets["gcp_service_account"]))
    return read_verified_portfolio(sheets, st.secrets["storage"]["spreadsheet_id"])


def render_award_tests() -> None:
    st.title("Pruebas de adjudicación")
    st.caption(
        "Evaluaciones documentales automatizadas · Municipio de León, Guanajuato. "
        "Los resultados son preliminares y requieren cotejo por el auditor."
    )
    limits_tab, capital_tab, validity_tab = st.tabs([
        "Verificación de límites de adjudicación",
        "Verificación de capital contable",
        "Verificación de vigencia del PUC",
    ])
    with limits_tab:
        _render_limits_tab()
    with capital_tab:
        if not is_configured(st.secrets) or not storage_configured(st.secrets):
            st.error("Se requiere configurar Google Sheets y la cuenta de servicio.")
        else:
            render_capital_test()
    with validity_tab:
        if not is_configured(st.secrets) or not storage_configured(st.secrets):
            st.error("Se requiere configurar Google Sheets y la cuenta de servicio.")
        else:
            render_puc_validity_test()


def _render_limits_tab() -> None:
    st.caption(
        "Prueba AD-06 · Límites monetarios por modalidad y ejercicio fiscal "
        "(municipal o estatal, 2021–2026). Solo consulta contratos y Recursos."
    )
    st.info(
        "**Piloto municipal: León, Guanajuato (fijo).** Cuando corresponde "
        "la Base municipal, se usa automáticamente la fila de León y el grupo "
        "que le corresponda en el ejercicio evaluado. La Base estatal no depende "
        "del grupo municipal. Los importes se comparan sin IVA y el resultado "
        "no constituye por sí solo una conclusión jurídica definitiva."
    )
    if not is_configured(st.secrets) or not storage_configured(st.secrets):
        st.error("Se requiere configurar Drive, Google Sheets y la cuenta de servicio.")
        return
    if st.button("Actualizar contratos y límites de Drive", key="limits_reload"):
        st.session_state.pop("award_limits_catalog", None)
        st.session_state.pop("award_limits_contracts", None)

    if "award_limits_catalog" not in st.session_state:
        try:
            with st.spinner("Leyendo Recursos y sus dos tablas históricas..."):
                st.session_state["award_limits_catalog"] = _load_catalog()
        except LimitsError as exc:
            st.error("Catálogo de límites: " + str(exc))
            return
        except Exception:
            st.error(
                "No se pudo conectar con el catálogo de límites en Recursos. "
                "Comprueba el acceso de la cuenta de servicio a esa carpeta y archivo."
            )
            return
    if "award_limits_contracts" not in st.session_state:
        try:
            with st.spinner("Consultando los contratos previamente analizados..."):
                st.session_state["award_limits_contracts"] = _load_contracts()
        except Exception:
            st.error("No se pudo leer el registro de contratos de Google Sheets.")
            return

    catalog = st.session_state["award_limits_catalog"]
    portfolio = st.session_state["award_limits_contracts"]
    st.caption(
        "Fuente: Recursos / ADJUDICACION_LIM_2021_2026.xlsx · "
        "Hojas: Base municipal (276 registros) y Base estatal (6 registros). "
        "Este módulo no vuelve a analizar PDF con Gemini."
    )
    if not portfolio.records:
        st.warning("Todavía no hay contratos analizados para ejecutar la prueba.")
        return

    evaluations = [
        (record, evaluate(record, catalog))
        for record in portfolio.records
    ]
    st.markdown("### Evaluación automática de los contratos")
    st.caption(
        "Los resultados sin confirmación de IVA, régimen o año "
        "aparecen como «Requiere revisión»; el municipio se fija a León."
    )
    rows = []
    for record, result in evaluations:
        limit = result.row
        normalized,_=normalized_values(record)
        selected_iva = identify_record_iva(record).basis
        review=record.verification or {}
        source_iva = (
            "Revisión guardada" if "iva" in verified_fields(record)
            else "Supuesto 16% incluido" if selected_iva=="Por confirmar"
            else "Texto del contrato"
        )
        rows.append({
            "Carpeta": record.nombre_carpeta,
            "Contrato": record.values.get("numero_contrato") or record.documento,
            "Año": result.year or "—",
            "Régimen": result.regime,
            "Municipio / Grupo": (
                f"{PILOT_MUNICIPALITY} / {limit.group}"
                if limit and limit.regime == "Municipal"
                else f"{PILOT_MUNICIPALITY} / No aplica"
                if limit else f"{PILOT_MUNICIPALITY} / —"
            ),
            "Modalidad": result.method,
            "Fecha de firma": normalized.get("fecha_firma_contrato") or "—",
            "Anticipo": normalized.get("anticipo") or "—",
            "Monto contractual": money(result.gross),
            "IVA del importe": result.iva,
            "Origen del IVA": source_iva,
            "Monto comparable sin IVA": money(result.net),
            "Límite AD": money(limit.ad_max) if limit else "—",
            "Límite LS": money(limit.ls_max) if limit else "—",
            "Hoja utilizada": limit.sheet if limit else "Sin determinar",
            "Decreto": limit.decree if limit else "—",
            "Resultado": result.state,
            "Estado de verificación": review.get("estado_revision") or "Sin guardar",
        })
    df = pd.DataFrame(rows)
    totals = df["Resultado"].value_counts()
    a,b,c = st.columns(3)
    a.metric("Contratos",len(df))
    b.metric("Dentro de límite o rango",int(totals.get("Dentro del límite",0) + totals.get("Dentro del rango de LP",0)))
    c.metric("Requieren revisión",int(totals.get("Requiere revisión",0)))
    st.caption(
        "Selecciona una fila de esta tabla para mostrar abajo la obra, "
        "el cálculo aplicado, la evidencia y la verificación correspondiente."
    )
    table_event = st.dataframe(
        df, hide_index=True, use_container_width=True,
        height=min(520, 85 + len(df) * 38),
        selection_mode="single-row", on_select="rerun",
        key="award_limits_selectable_work_table",
    )
    selected_rows = table_event.selection.rows
    chosen = selected_rows[0] if selected_rows else 0
    if not 0 <= chosen < len(evaluations):
        chosen = 0
    st.download_button(
        "Exportar resultados de la prueba (CSV)",
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name="AuditorIA_AD06_Limites_Adjudicacion.csv",
        mime="text/csv", key="award_limits_csv",
    )

    st.markdown("### Cotejo de la obra seleccionada")
    record, automatic=evaluations[chosen]
    values=record.full_values or {}
    normalized,notes=normalized_values(record)
    original_iva=identify_record_iva(record)
    st.caption(
        "Carpeta: "+record.nombre_carpeta+" · Municipio fijo de este piloto: "
        +PILOT_MUNICIPALITY
    )
    render_verification_form(record,prefix="ad06")
    st.markdown("#### Resultado detallado vigente")
    if automatic.state=="Excede el límite":
        st.error(automatic.state+" · "+automatic.message)
    elif automatic.state=="Requiere revisión":
        st.warning(automatic.state+" · "+automatic.message)
    else:
        st.success(automatic.state+" · "+automatic.message)
    st.caption(
        "Modalidad normalizada: "+automatic.method+
        " · Anticipo: "+str(normalized.get("anticipo") or "—")+
        " · IVA considerado: "+automatic.iva
    )
    if original_iva.basis=="Por confirmar" and "iva" not in verified_fields(record):
        st.warning(
            "IVA aplicado por SUPUESTO: 16 % incluido. No consta una "
            "aclaración fiscal inequívoca. Usa el formulario de verificación "
            "para confirmar o corregir el tratamiento y guarda tu sustento."
        )
    if automatic.row:
        r=automatic.row
        st.table({
            "Dato": ["Tabla aplicada","Ejercicio","Municipio","Grupo","Modalidad",
                     "Anticipo normalizado","Importe contractual",
                     "Importe comparable SIN IVA","AD hasta","LS desde","LS hasta",
                     "LP desde","Decreto","Artículo","Referencia poblacional",
                     "Clave normativa"],
            "Valor": [
                r.sheet,str(r.year),r.municipality or PILOT_MUNICIPALITY,
                r.group or "No aplica",automatic.method,
                normalized.get("anticipo") or "—",
                money(automatic.gross),money(automatic.net),
                money(r.ad_max),money(r.ls_min),money(r.ls_max),money(r.lp_min),
                r.decree,r.article or "—",r.population or "—",r.key,
            ],
        })
        if automatic.margin is not None:
            st.caption("Margen respecto del máximo aplicable: "+money(automatic.margin))
        _source_link(r.url)
    if automatic.warnings:
        st.caption("Advertencias: "+" · ".join(automatic.warnings))
    with st.expander("Datos literales de la extracción (sin normalizar)"):
        for label,key in (
            ("Legislación citada","legislacion_citada"),
            ("Fuente de recursos","fuente_financiamiento"),
            ("Fecha de firma","fecha_firma_contrato"),
            ("Monto contractual","monto_contrato"),
            ("Anticipo","anticipo"),
            ("Objeto","obra_servicio"),
        ):
            st.write(f"**{label}:** {values.get(key) or 'No localizado'}")
        st.caption(
            "IVA según la evidencia literal: "+original_iva.basis+
            " · "+original_iva.source
        )
    st.caption(
        "Las verificaciones se guardan por versión de contrato y están "
        "disponibles en Resultados y AD-06. El texto literal original y "
        "las evidencias del PDF no se sustituyen."
    )
    st.divider()
    with st.expander("Otras pruebas de adjudicación (planeadas)"):
        st.table({
            "Prueba": [
                "Especialidad del contratista", "Responsable técnico",
                "Dictamen, notificación y firma del contrato",
            ],
            "Estado": ["Por implementar"] * 3,
        })
