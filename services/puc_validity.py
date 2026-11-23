"""AD-03: verificar vigencia del PUC exclusivamente a la firma contractual.

Regla operativa del piloto: si la constancia indica 'vigencia hasta' y
no 'vigencia desde', el inicio del intervalo se calcula un año calendario
antes. La fecha deducida se identifica claramente como CALCULADA, sin
sobrescribir datos literales del PUC ni la extracción IA.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from services.capital_contable import CapitalSources, PucEntry, _identity, _puc_date
from services.contract_display import normalize_award_method
from services.contract_normalization import normalized_values
from services.puc_history import PucReview


@dataclass(frozen=True)
class ValidityResult:
    state: str
    signature_date: str
    period_from: str
    period_to: str
    period_source: str
    inferred_start: bool
    puc: PucEntry | None
    notes: tuple[str, ...]


def _one_year_before(expiration: date) -> date:
    """Resta un año calendario, conservando día/mes cuando es posible.

    29/02 de un año bisiesto se interpreta como 28/02 del año anterior.
    No se resta 365 días para no desplazar aniversarios por años bisiestos.
    """
    try:
        return expiration.replace(year=expiration.year - 1)
    except ValueError:
        return expiration.replace(year=expiration.year - 1, day=28)


def _display_date(value: date | None) -> str:
    return value.strftime("%d/%m/%Y") if value else ""


def evaluate_puc_validity(
    record: Any, sources: CapitalSources,
    review: PucReview | None = None,
) -> ValidityResult:
    norm, initial_notes = normalized_values(record)
    notes = list(initial_notes)
    method = normalize_award_method(norm.get("modalidad_adjudicacion", ""))
    if method != "ADJUDICACIÓN DIRECTA":
        state = "No aplica al piloto AD" if method in (
            "LICITACIÓN SIMPLIFICADA", "LICITACIÓN PÚBLICA",
            "INVITACIÓN RESTRINGIDA", "CONCURSO SIMPLIFICADO",
        ) else "Requiere revisión de modalidad"
        return ValidityResult(state, "", "", "", "", False, None, tuple(notes))

    puc = sources.puc_by_work.get(record.obra_id)
    if puc is None:
        notes.append(sources.issues_by_work.get(
            record.obra_id, "Falta un PUC activo y analizado de esta obra."
        ))
        return ValidityResult(
            "Pendiente de PUC", norm.get("fecha_firma_contrato", ""),
            "", "", "", False, None, tuple(notes),
        )

    if review and (
        review.obra_id != record.obra_id
        or review.contrato_documento_id != record.documento_id
        or review.contrato_cache_key != record.cache_key
        or review.puc_documento_id != puc.documento_id
        or review.puc_cache_key != puc.cache_key
    ):
        notes.append("Revisión de otra versión documental ignorada.")
        review = None

    # AD-03 solo usa la firma contractual, nunca la fecha del dictamen o asignación.
    signed = _puc_date(norm.get("fecha_firma_contrato", ""))
    signature_date = _display_date(signed)

    historical = bool(review and review.vigencia_desde and review.vigencia_hasta)
    raw_start = review.vigencia_desde if historical else puc.vigencia_desde
    raw_end = review.vigencia_hasta if historical else puc.vigencia_hasta
    start = _puc_date(raw_start)
    end = _puc_date(raw_end)
    inferred = False

    if not start and end:
        start = _one_year_before(end)
        inferred = True
        notes.append(
            "Inicio calculado restando exactamente un año calendario a "
            "'vigencia hasta', según el criterio anual del piloto."
        )

    period_source = (
        "Periodo histórico cotejado por auditor: " + review.referencia
        if historical and review
        else "Datos del PUC; inicio calculado (un año antes del vencimiento)"
        if inferred
        else "Fechas expresas del PUC analizado"
    )
    if puc.fecha_validacion or puc.fecha_impresion:
        notes.append(
            "Ni la fecha de validación ni la de impresión sustituyen "
            "el cálculo de vigencia del registro."
        )
    if not signed:
        state = "Pendiente de fecha de firma"
        notes.append("No se identificó una fecha válida de firma del contrato.")
    elif not start or not end:
        state = "Pendiente de vigencia del PUC"
        notes.append("No hay 'vigencia hasta' verificable para comparar el periodo.")
    elif start > end:
        state = "Requiere revisión de fechas PUC"
        notes.append("El inicio del periodo es posterior a la fecha de vencimiento.")
    elif start <= signed <= end:
        state = "Vigente en fecha de firma"
    else:
        state = "Fuera del periodo PUC en fecha de firma"
        notes.append(
            "La fecha de firma no cae dentro del periodo de esta cédula. "
            "Antes de concluir incumplimiento, revisar si existe otro refrendo aplicable."
        )

    rfc = norm.get("rfc", "")
    registro = norm.get("registro_puc", "")
    wrong_identity = bool(
        (rfc and puc.rfc and _identity(rfc) != _identity(puc.rfc))
        or (registro and puc.registro and _identity(registro) != _identity(puc.registro))
    )
    if wrong_identity:
        notes.append("RFC o número de registro no coincide entre contrato y PUC.")
        state = "Requiere revisión de identidad"

    # Una cancelación/suspensión sin fecha no se proyecta retrospectivamente.
    historical_status = (
        review.estado_registro_historico
        if review and review.estado_registro_historico
        else puc.estado_registro
    ).casefold()
    if any(word in historical_status for word in ("suspendido", "cancelado")):
        notes.append(
            "La constancia reporta suspensión/cancelación: verificar la fecha "
            "en que surtió efectos antes de concluir vigencia."
        )
        if state == "Vigente en fecha de firma":
            state = "Requiere revisión del estado del registro"

    return ValidityResult(
        state, signature_date, _display_date(start), _display_date(end),
        period_source, inferred, puc, tuple(notes),
    )
