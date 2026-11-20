"""Formulario compartido para confirmar o corregir datos por contrato.

Las correcciones viven en VerificacionesContrato, NO en la extracción fuente.
"""
from __future__ import annotations

import streamlit as st

from services.contract_normalization import (
    EDITABLE_FIELDS, CATEGORIES, normalized_values, IVA_VALUES, REGIMES,
)
from services.contract_verifications import save_verification,VerificationError
from services.sheets_service import create_sheets_client
from services.writer_lock import get_writer_lock
from services.contract_v2 import FIELD_LABELS_V2


def _choice(title: str, options: tuple[str,...], current: str, key: str) -> str:
    items=("Sin cambio",*options)
    active=current if current in options else "Sin cambio"
    value=st.selectbox(title,items,index=items.index(active),key=key)
    return "" if value=="Sin cambio" else value


def render_verification_form(record: object, *, prefix: str) -> None:
    """Mismo formulario en Resultados y AD-06; una revisión activa por versión."""
    review=getattr(record,"verification",None) or {}
    previous=review.get("campos") or {}
    display, notes=normalized_values(record)
    record_key=f"{prefix}_{record.documento_id}_{record.cache_key[:12]}"
    with st.expander("Verificar, corregir y GUARDAR los datos de este contrato",expanded=False):
        st.caption(
            "Una revisión guardada se aplica a Resultados y a AD-06 para "
            "este contrato. Los valores literales y el PDF NO cambian. "
            "Cada guardado agrega una entrada al historial."
        )
        if review:
            st.info(
                f"Revisión vigente: {review.get('estado_revision','Pendiente')} · "
                f"{review.get('auditor','')} · {review.get('revision_utc','')}. "
                f"Nota: {review.get('observaciones','')}"
            )
        with st.form(key=f"contract_verify_{record_key}"):
            st.markdown("**Clasificaciones y datos para las pruebas**")
            a,b,c=st.columns(3)
            with a:
                typ=_choice("Tipo económico", CATEGORIES["tipo_contrato"],
                    previous.get("tipo_contrato",""),f"rev_type_{record_key}")
                method=_choice("Modalidad de adjudicación",CATEGORIES["modalidad_adjudicacion"],
                    previous.get("modalidad_adjudicacion",""),f"rev_method_{record_key}")
            with b:
                iva=_choice("IVA del monto contractual",IVA_VALUES,
                    previous.get("iva",""),f"rev_iva_{record_key}")
                regime=_choice("Tabla normativa",REGIMES,
                    previous.get("regimen",""),f"rev_regime_{record_key}")
            with c:
                exercise=_choice("Año del procedimiento",tuple(str(x) for x in range(2021,2027)),
                    previous.get("ejercicio",""),f"rev_exercise_{record_key}")
                advance=st.text_input(
                    f"Anticipo (actual: {display.get('anticipo','—')})",
                    value=previous.get("anticipo",""),
                    placeholder="30%, 0%, 12.5%",
                    key=f"rev_advance_{record_key}",
                    help="Vacío conserva la normalización automática; 0% se usa cuando no se otorga.",
                )

            st.markdown("**Correcciones documentales adicionales (opcionales)**")
            st.caption(
                "Solo rellena los datos que hayas cotejado con el expediente. "
                "Deja vacíos los demás para mantener los valores normalizados."
            )
            available=(
                "numero_contrato","obra_servicio","contratista",
                "registro_puc","rfc","representante_legal",
                "monto_contrato","fecha_inicio_contractual",
                "fecha_termino_contractual","fecha_firma_contrato",
                "fuente_financiamiento","legislacion_citada",
            )
            labels=dict(FIELD_LABELS_V2)
            fields={}
            for name in available:
                fields[name]=st.text_input(
                    f"{labels[name]} · actual: {str(display.get(name,'—'))[:100]}",
                    value=previous.get(name,""),
                    key=f"rev_input_{name}_{record_key}",
                )
            status=st.selectbox(
                "Estado de la revisión",
                ["Pendiente","Confirmado"],
                index=1 if review.get("estado_revision")=="Confirmado" else 0,
                key=f"rev_status_{record_key}",
            )
            note=st.text_area(
                "Fundamento o explicación del cotejo (obligatorio)",
                value=review.get("observaciones",""),
                placeholder="Documento, cláusula, página o criterio revisado...",
                max_chars=1800,
                key=f"rev_note_{record_key}",
            )
            submitted=st.form_submit_button(
                "Guardar verificación de este contrato",type="primary",
            )

        if not submitted:
            return

        changes={
            "tipo_contrato":typ,"modalidad_adjudicacion":method,
            "iva":iva,"regimen":regime,"ejercicio":exercise,
            "anticipo":advance,**fields,
        }
        changes={k:v for k,v in changes.items() if v and v.strip()}
        try:
            email=str(getattr(st.user,"email","") or "")
            client=create_sheets_client(dict(st.secrets["gcp_service_account"]))
            with get_writer_lock():
                save_verification(
                    client,str(st.secrets["storage"]["spreadsheet_id"]),
                    obra_id=record.obra_id,documento_id=record.documento_id,
                    cache_key=record.cache_key,auditor=email,
                    estado=status,campos=changes,observaciones=note,
                )
        except VerificationError as exc:
            st.error(str(exc))
            return
        except Exception:
            st.error(
                "No se confirmó el guardado de la revisión en Sheets. "
                "Comprueba VerificacionesContrato antes de repetir."
            )
            return
        st.session_state.pop("results_portfolio",None)
        st.session_state.pop("award_limits_contracts",None)
        st.session_state["verification_saved_notice"]=(
            "Se guardó la verificación, con historial de usuario y fecha."
        )
        st.rerun()
