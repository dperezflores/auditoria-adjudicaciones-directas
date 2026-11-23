"""AD-03: vigencia histórica del PUC independiente del capital contable.

La fecha de impresión/validación no se interpreta como inicio de vigencia.
Un periodo aportado que no cubre una fecha obliga a localizar el refrendo
histórico: no demuestra por sí solo que nunca existió otro registro vigente.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.capital_contable import (
    CapitalSources, PucEntry, _identity, _puc_date,
)
from services.contract_display import normalize_award_method
from services.contract_normalization import normalized_values
from services.puc_history import PucReview


@dataclass(frozen=True)
class ValidityResult:
    state: str
    assignment_result: str
    contract_result: str
    assignment_date: str
    signature_date: str
    period_from: str
    period_to: str
    period_source: str
    assignment_source: str
    puc: PucEntry | None
    notes: tuple[str, ...]


def _check_date(check_date: Any, start: Any, end: Any) -> str:
    if check_date is None:
        return "Fecha no acreditada"
    if start and end and start <= check_date <= end:
        return "Dentro del periodo aportado"
    if end and check_date > end:
        return "Posterior al periodo aportado"
    if start and check_date < start:
        return "Anterior al periodo aportado"
    return "Periodo insuficiente"


def evaluate_puc_validity(
    record: Any, sources: CapitalSources,
    review: PucReview | None = None,
) -> ValidityResult:
    norm, notes_raw = normalized_values(record)
    notes = list(notes_raw)
    method = normalize_award_method(norm.get("modalidad_adjudicacion", ""))
    if method != "ADJUDICACIÓN DIRECTA":
        status = "No aplica al piloto AD" if method in (
            "LICITACIÓN SIMPLIFICADA", "LICITACIÓN PÚBLICA",
            "INVITACIÓN RESTRINGIDA", "CONCURSO SIMPLIFICADO",
        ) else "Requiere revisión de modalidad"
        return ValidityResult(status, "—", "—", "", "", "", "", "", "", None,
                              tuple(notes))

    puc = sources.puc_by_work.get(record.obra_id)
    if not puc:
        return ValidityResult(
            "Pendiente de PUC", "Sin PUC", "Sin PUC", "", "", "", "", "", "",
            None, tuple(notes + [
                sources.issues_by_work.get(
                    record.obra_id, "Falta un PUC activo y analizado de esta obra."
                )
            ]),
        )
    if review and (review.obra_id != record.obra_id
                   or review.puc_cache_key != puc.cache_key
                   or review.puc_documento_id != puc.documento_id
                   or review.contrato_cache_key != record.cache_key
                   or review.contrato_documento_id != record.documento_id):
        review = None  # Nunca reutilizar un cotejo de otro archivo o versión.
        notes.append("Se ignoró una revisión de otra versión documental.")

    source = sources.assignments.get(record.obra_id)
    manual_assignment = bool(review and review.fecha_asignacion)
    assignment_raw = (
        review.fecha_asignacion if manual_assignment else
        source.fecha if source else ""
    )
    assignment_source = (
        "Fecha documentada por el auditor en RevisionesPUC" if manual_assignment
        else source.fuente if source else "No acreditada"
    )
    if not manual_assignment and source:
        notes.append(
            "La fecha de emisión del dictamen es preliminar; confirmar la fecha "
            "efectiva de asignación con evidencia documental."
        )
    a_date = _puc_date(assignment_raw)
    signature_raw = norm.get("fecha_firma_contrato", "")
    s_date = _puc_date(signature_raw)
    if not a_date:
        notes.append("Falta fecha efectiva de asignación para cerrar la primera comparación.")
    if not s_date:
        notes.append("Falta fecha verificable de firma del contrato.")
    if a_date and s_date and a_date > s_date:
        notes.append(
            "Fecha de asignación posterior a la firma: comprobar la secuencia documental."
        )

    historical_interval = bool(review and review.vigencia_desde and review.vigencia_hasta)
    start_raw = review.vigencia_desde if historical_interval else puc.vigencia_desde
    end_raw = review.vigencia_hasta if historical_interval else puc.vigencia_hasta
    period_source = (
        "Constancia histórica asentada por auditor: " + review.referencia
        if historical_interval and review else "Datos literales del PUC analizado"
    )
    begin, finish = _puc_date(start_raw), _puc_date(end_raw)
    a_result = _check_date(a_date, begin, finish)
    s_result = _check_date(s_date, begin, finish)
    if begin and finish and begin > finish:
        a_result = s_result = "Periodo contradictorio"
    if not begin or not finish:
        notes.append(
            "No se acreditó el intervalo completo del registro/refrendo. "
            "No utilizar fecha de validación o impresión como inicio supuesto."
        )
    if any(r in ("Anterior al periodo aportado", "Posterior al periodo aportado")
           for r in (a_result, s_result)):
        notes.append(
            "El periodo disponible no cubre la fecha señalada; buscar refrendos "
            "históricos y excepciones legales antes de concluir incumplimiento."
        )

    observed_state = (
        review.estado_registro_historico
        if review and review.estado_registro_historico
        else puc.estado_registro
    ).casefold()
    state_risk = any(k in observed_state for k in (
        "suspendido", "cancelado", "vencido", "no vigente",
    ))
    if state_risk:
        notes.append(
            "Se reporta suspensión, cancelación o no vigencia; verificar "
            "desde qué fecha surtió efecto, sin extrapolar el estado actual."
        )
    if puc.fecha_impresion:
        notes.append(
            "La fecha de impresión es informativa: no determina la vigencia histórica."
        )
    if puc.fecha_validacion:
        notes.append(
            "La validación documental no equivale al inicio del registro."
        )

    norm_rfc, norm_reg = norm.get("rfc", ""), norm.get("registro_puc", "")
    mismatch = bool(
        (norm_rfc and puc.rfc and _identity(norm_rfc) != _identity(puc.rfc))
        or (norm_reg and puc.registro
            and _identity(norm_reg) != _identity(puc.registro))
    )
    if mismatch:
        notes.append("La identidad RFC/registro entre contrato y PUC requiere cotejo.")

    both_in_range = (a_result == "Dentro del periodo aportado"
                     and s_result == "Dentro del periodo aportado")
    if mismatch:
        result_state = "Requiere revisión de identidad"
    elif state_risk:
        result_state = "Requiere revisión del estado del registro"
    elif a_date and s_date and a_date > s_date:
        result_state = "Requiere revisión de fechas"
    elif not a_date or not manual_assignment:
        result_state = "Pendiente de fecha efectiva de asignación"
    elif both_in_range:
        result_state = "Vigencia documental compatible (preliminar)"
    elif any("periodo aportado" in r for r in (a_result, s_result)):
        result_state = "Periodo aportado no acredita vigencia"
    else:
        result_state = "Pendiente de vigencia histórica"

    return ValidityResult(
        result_state, a_result, s_result, assignment_raw, signature_raw,
        start_raw, end_raw, period_source, assignment_source, puc, tuple(notes),
    )
