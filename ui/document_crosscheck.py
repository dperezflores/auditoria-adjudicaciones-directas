"""Visualización documental por obra: contrato ↔ PUC y demás PDFs.

El cotejo es comparativo, no una prueba jurídica de cumplimiento.
Todo proviene de Google Sheets, sin enviar documentos a IA.
"""
from __future__ import annotations

import re

import pandas as pd
import streamlit as st

from services.document_links import (
    SupportingDocument, candidate_puc_documents, compare_puc,
    documents_for_contract, identification_note, puc_values,
)


def _valid_drive_id(document_id: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{10,}", document_id))


def _puc_view(contract, documents: tuple[SupportingDocument, ...]) -> None:
    candidates = candidate_puc_documents(contract, documents)
    if not candidates:
        st.info(
            "Todavía no hay una extracción PUC disponible para esta obra. "
            "Los archivos pendientes aparecen en «Otros documentos»."
        )
        return
    if len(candidates) > 1:
        st.warning(
            "Hay varios documentos PUC analizados. Selecciona el correspondiente; "
            "estar en la misma carpeta no acredita que pertenezcan al mismo contratista."
        )
        options = {doc.documento_id: doc for doc in candidates}
        selected_id = st.selectbox(
            "PUC para comparar",
            list(options),
            format_func=lambda key: options[key].nombre,
            key=f"linked_puc_{contract.documento_id}",
        )
        puc = options[selected_id]
    else:
        puc = candidates[0]

    st.markdown(f"**PUC consultado:** {puc.nombre}")
    st.caption(identification_note(contract, puc))
    comparison = compare_puc(contract, puc)
    matches = sum(row.resultado == "Coincide" for row in comparison[:5])
    differences = sum(row.resultado == "Diferente" for row in comparison[:5])
    unresolved = sum(row.resultado in ("Sin dato para comparar", "Posible correspondencia") for row in comparison[:5])

    a, b, c = st.columns(3)
    a.metric("Datos que coinciden", matches)
    b.metric("Diferencias detectadas", differences)
    c.metric("Por verificar", unresolved)
    st.caption(
        "Comparación de cinco datos de identidad y representación entre las "
        "extracciones. La vigencia se revisa por separado."
    )
    st.dataframe(
        pd.DataFrame([
            {
                "Dato comparado": row.dato,
                "Contrato": row.contrato,
                "PUC": row.documento,
                "Resultado": row.resultado,
                "Página PUC": row.pagina if row.pagina is not None else "—",
            }
            for row in comparison
        ]),
        hide_index=True,
        use_container_width=True,
        column_config={
            "Contrato": st.column_config.TextColumn(width="large"),
            "PUC": st.column_config.TextColumn(width="large"),
            "Resultado": st.column_config.TextColumn(width="medium"),
        },
    )

    st.markdown("#### Información adicional del PUC")
    fields = puc_values(puc)
    facts = [
        ("Capital contable", "capital_contable"),
        ("Especialidad registrada", "especialidad"),
        ("Vigencia hasta", "vigencia_hasta"),
        ("Representación técnica", "representante_tecnico"),
    ]
    left, right = st.columns(2)
    for i, (label, key) in enumerate(facts):
        field = fields.get(key) or {}
        with (left if i % 2 == 0 else right):
            with st.container(border=True):
                st.caption(label)
                st.write(field.get("valor") or "No localizado en la extracción")
                if field.get("pagina"):
                    st.caption(f"PUC, página {field['pagina']}")

    expiry = comparison[-1]
    st.caption(
        f"**Vencimiento frente a la firma:** {expiry.resultado}. "
        f"{expiry.detalle}"
    )
    if differences:
        st.warning(
            "Existen diferencias de identificación que deben revisarse con "
            "ambos documentos originales. No se califican como incumplimiento."
        )
    if puc.alertas:
        with st.expander("Asuntos señalados por la extracción del PUC"):
            for alert in puc.alertas:
                st.write("• " + alert)

    with st.expander("Ver todos los datos y evidencias del PUC"):
        if puc.resumen:
            st.write(puc.resumen)
        st.dataframe(
            pd.DataFrame([
                {
                    "Dato extraído": fact.get("campo") or "",
                    "Texto del PUC": fact.get("valor") or "No localizado",
                    "Página": fact.get("pagina") if fact.get("pagina") is not None else "—",
                    "Fragmento de evidencia": fact.get("evidencia") or "Sin evidencia",
                }
                for fact in puc.campos
            ]),
            use_container_width=True, hide_index=True,
        )
    if _valid_drive_id(puc.documento_id):
        st.link_button(
            "Abrir PUC original en Drive",
            f"https://drive.google.com/file/d/{puc.documento_id}/view",
        )
    st.caption(
        "Coincidencia textual significa que los datos extraídos se parecen o son "
        "iguales tras ignorar variaciones de formato; NO sustituye la verificación "
        "documental ni acredita capital suficiente, vigencia integral o especialidad."
    )


def _other_documents(contract, docs: tuple[SupportingDocument, ...]) -> None:
    if not docs:
        st.info("Este expediente no tiene otros PDF registrados en Google Sheets.")
        return
    st.caption(
        "Los documentos se vinculan por expediente. Sus análisis aparecen solo "
        "si el resultado de IA corresponde a la versión activa registrada."
    )
    st.dataframe(
        pd.DataFrame([
            {
                "Documento": d.nombre,
                "Tipo identificado": d.tipo,
                "Estado": d.estado,
                "Datos extraídos": len(d.campos),
            }
            for d in docs
        ]),
        hide_index=True, use_container_width=True,
    )
    options = {doc.documento_id: doc for doc in docs}
    selected = st.selectbox(
        "Consultar documento del expediente",
        list(options),
        format_func=lambda key: options[key].nombre,
        key=f"linked_docs_{contract.documento_id}",
    )
    doc = options[selected]
    st.markdown(f"**{doc.nombre}** · {doc.estado}")
    if not doc.analysed:
        st.info(
            "Todavía no existe un análisis completo y vigente de este archivo. "
            "No se utilizarán valores de extracciones anteriores."
        )
    else:
        st.caption("Tipo de documento identificado: " + doc.tipo)
        if doc.resumen:
            st.write(doc.resumen)
        if doc.campos:
            st.dataframe(
                pd.DataFrame([
                    {
                        "Dato": f.get("campo") or "",
                        "Valor": f.get("valor") or "No localizado",
                        "Página": f.get("pagina") if f.get("pagina") is not None else "—",
                        "Evidencia": f.get("evidencia") or "Sin evidencia",
                    }
                    for f in doc.campos
                ]),
                hide_index=True, use_container_width=True,
                column_config={"Evidencia": st.column_config.TextColumn(width="large")},
            )
        else:
            st.info("No hay campos estructurados conservados en este esquema.")
        if doc.alertas:
            st.markdown("**Asuntos por verificar extraídos del documento**")
            for note in doc.alertas:
                st.write("• " + note)
        st.caption("Último análisis (UTC): " + (doc.extraido_utc or "No disponible"))
    if _valid_drive_id(doc.documento_id):
        st.link_button(
            "Abrir documento original en Drive",
            f"https://drive.google.com/file/d/{doc.documento_id}/view",
        )


def render_document_crosscheck(contract, documents: tuple[SupportingDocument, ...]) -> None:
    """El contrato seleccionado controla qué documentos y cruces se muestran."""
    linked = documents_for_contract(contract, documents)
    st.markdown("### Cruce documental de la obra seleccionada")
    if not linked:
        st.info("Todavía no hay documentos complementarios registrados para esta obra.")
        return
    analysed = sum(d.analysed for d in linked)
    a, b, c = st.columns(3)
    a.metric("Documentos complementarios", len(linked))
    b.metric("Con análisis disponible", analysed)
    c.metric("Pendientes o desactualizados", len(linked) - analysed)
    st.caption(
        "Vínculo por ID de obra en Google Sheets; la coincidencia de identidad "
        "y las conclusiones legales requieren comprobaciones adicionales."
    )
    tab_puc, tab_docs = st.tabs([
        "Contrato ↔ PUC",
        "Otros documentos y análisis",
    ])
    with tab_puc:
        _puc_view(contract, linked)
    with tab_docs:
        _other_documents(contract, linked)
