"""Nueva prueba independiente: verificación de límites por importe 2021–2026.

No ejecuta Gemini ni modifica los datos guardados, y no afecta AD-01…AD-05.
"""
from __future__ import annotations

from urllib.parse import urlparse

import pandas as pd
import streamlit as st

from services.award_limits import (
    Catalog, LimitsError, PILOT_MUNICIPALITY, evaluate, infer_iva,
    infer_regime, money, read_drive_catalog, year_from_date,
)
from services.contract_portfolio import read_contract_portfolio
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
    return read_contract_portfolio(sheets, st.secrets["storage"]["spreadsheet_id"])


def render_award_tests() -> None:
    st.title("Pruebas de adjudicación")
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
        rows.append({
            "Obra": record.nombre_carpeta,
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
            "Monto extraído": money(result.gross),
            "IVA del importe": identify_record_iva(record).basis,
            "Monto comparable sin IVA": money(result.net),
            "Límite AD": money(limit.ad_max) if limit else "—",
            "Límite LS": money(limit.ls_max) if limit else "—",
            "Hoja utilizada": limit.sheet if limit else "Sin determinar",
            "Decreto": limit.decree if limit else "—",
            "Resultado": result.state,
        })
    df = pd.DataFrame(rows)
    totals = df["Resultado"].value_counts()
    a,b,c = st.columns(3)
    a.metric("Contratos",len(df))
    b.metric("Dentro de límite o rango",int(totals.get("Dentro del límite",0) + totals.get("Dentro del rango de LP",0)))
    c.metric("Requieren revisión",int(totals.get("Requiere revisión",0)))
    st.dataframe(df, hide_index=True, use_container_width=True)
    st.download_button(
        "Exportar resultados de la prueba (CSV)",
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name="AuditorIA_AD06_Limites_Adjudicacion.csv",
        mime="text/csv", key="award_limits_csv",
    )

    st.markdown("### Revisar un contrato y confirmar sus datos")
    positions = list(range(len(evaluations)))
    chosen = st.selectbox(
        "Contrato", positions, key="award_limits_selected_contract",
        format_func=lambda pos: (
            evaluations[pos][0].nombre_carpeta + " · "
            + (evaluations[pos][0].values.get("numero_contrato") or
               evaluations[pos][0].documento)
        ),
    )
    record, automatic = evaluations[chosen]
    values = record.full_values or {}
    if not values:
        st.warning(
            "La extracción es anterior a contrato-v2: no contiene todos los datos "
            "para determinar legislación y fuente de financiamiento. "
            "El resultado se mantiene pendiente de revisión."
        )
    detected = infer_regime(values.get("legislacion_citada",""),
                            values.get("fuente_financiamiento",""))
    default_regime = detected if detected in ("Municipal","Estatal") else "Por confirmar"
    options = ["Por confirmar","Municipal","Estatal"]
    left, middle, right = st.columns(3)
    with left:
        regime = st.selectbox(
            "Régimen normativo para cotejo", options,
            index=options.index(default_regime),
            key=f"limits_regime_{record.documento_id}",
            help="Confirmar contra la legislación citada, origen del recurso y expediente.",
        )
        actual_year = year_from_date(values.get("fecha_firma_contrato",""))
        years = ["Sin identificar", *range(2021,2027)]
        year = st.selectbox(
            "Ejercicio aplicable", years,
            index=years.index(actual_year) if actual_year in years else 0,
            key=f"limits_year_{record.documento_id}",
            help="Por defecto usa el año de firma. Verifica el ejercicio normativo "
                 "del procedimiento, especialmente si la adjudicación y firma difieren.",
        )
    with middle:
        st.markdown(f"**Municipio de revisión:** {PILOT_MUNICIPALITY}, Guanajuato")
        st.caption(
            "Fijo para todos los contratos de este piloto. "
            "Su grupo A/B/C se obtiene del catálogo en el año seleccionado "
            "cuando el régimen es municipal."
        )
        raw_amount = values.get("monto_contrato","")
        iva_status = identify_record_iva(record)
        iva_detected = iva_status.basis
        iva_options = ["Por confirmar", "Con IVA (16%)", "Sin IVA"]
        iva = st.selectbox(
            "Tratamiento del monto extraído", iva_options,
            index=iva_options.index(iva_detected), key=f"limits_iva_{record.documento_id}",
            help="Los umbrales del XLSX están sin IVA; confirma este dato con el contrato.",
        )
    with right:
        st.write("**Datos literales del contrato**")
        st.caption("Legislación citada: " + (values.get("legislacion_citada") or "No localizada"))
        st.caption("Recurso: " + (values.get("fuente_financiamiento") or "No localizado"))
        st.caption("Firma: " + (values.get("fecha_firma_contrato") or "No localizada"))
        st.caption("Monto: " + (values.get("monto_contrato") or "No localizado"))
        st.markdown("**IVA del importe contractual (detección documental)**")
        st.caption(
            f"{iva_status.basis} · {iva_status.source}"
            + (f" · Página {iva_status.page}" if iva_status.page else "")
        )
        if iva_status.quote and iva_status.source == "Evidencia de la cláusula del monto":
            st.caption("Cita textual del monto: " + iva_status.quote)
        st.caption("Objeto: " + (values.get("obra_servicio") or "No localizado"))

    manual = evaluate(
        record, catalog, regime=regime,
        iva=iva, year=year if isinstance(year,int) else None,
    )
    st.markdown("#### Resultado detallado")
    if manual.state == "Excede el límite":
        st.error(manual.state + " · " + manual.message)
    elif manual.state == "Requiere revisión":
        st.warning(manual.state + " · " + manual.message)
    else:
        st.success(manual.state + " · " + manual.message)
    if manual.row:
        r = manual.row
        st.table({
            "Dato": ["Tabla aplicada","Ejercicio","Municipio","Grupo","Modalidad",
                     "Importe comparado SIN IVA","AD hasta","LS desde","LS hasta",
                     "LP desde","Decreto","Artículo","Referencia poblacional","Clave normativa"],
            "Valor": [r.sheet,str(r.year),r.municipality or "No aplica",r.group or "No aplica",
                      manual.method,money(manual.net),money(r.ad_max),money(r.ls_min),
                      money(r.ls_max),money(r.lp_min),r.decree,r.article or "—",
                      r.population or "—",r.key],
        })
        if manual.margin is not None:
            st.caption("Margen respecto del máximo aplicable: " + money(manual.margin))
        _source_link(r.url)
    if manual.warnings:
        st.caption("Aspectos pendientes de confirmar: " + " · ".join(manual.warnings))
    st.caption(
        "Las selecciones de revisión son temporales y NO modifican los documentos "
        "ni los campos extraídos en la base. La tabla general aprovecha el "
        "IVA detectado en el valor o en la evidencia de la cláusula contractual "
        "sin necesidad de volver a analizar PDF."
    )
    st.divider()
    with st.expander("Otras cinco pruebas de adjudicación (planeadas)"):
        st.table({
            "Prueba": [
                "Capital contable", "Especialidad del contratista",
                "Vigencia del PUC", "Responsable técnico",
                "Dictamen, notificación y firma del contrato",
            ],
            "Estado": ["Por implementar"] * 5,
        })
