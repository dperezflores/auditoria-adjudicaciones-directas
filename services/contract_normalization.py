"""Capa única de normalización para Resultados y prueba AD-06.

La extracción literal jamás se reescribe. Las verificaciones se superponen
en memoria únicamente al presentar/evaluar cada contrato.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
import unicodedata
from typing import Any, Mapping

from services.contract_display import (
    format_contract_amount, normalize_award_method, normalize_contract_type,
    short_date,
)
from services.amount_iva import identify_record_iva
from services.contract_role_rules import (
    record_representation_fields, suggested_display_type,
)
from services.contract_portfolio import parse_amount


EDITABLE_FIELDS = (
    "numero_contrato", "obra_servicio", "tipo_contrato", "contratista",
    "registro_puc", "rfc", "representante_legal",
    "modalidad_adjudicacion", "monto_contrato",
    "fecha_inicio_contractual", "fecha_termino_contractual",
    "fecha_firma_contrato", "anticipo", "fuente_financiamiento",
    "legislacion_citada",
)
EXTRA_FIELDS = ("iva", "regimen", "ejercicio")
IVA_VALUES = ("Con IVA (16%)", "Sin IVA", "Por confirmar")
REGIMES = ("Municipal", "Estatal", "Por confirmar")
CATEGORIES = {
    "tipo_contrato": ("Precios Unitarios", "Precio Alzado",
                      "Mixto (precios unitarios y precio alzado)", "Sin determinar"),
    "modalidad_adjudicacion": (
        "ADJUDICACIÓN DIRECTA", "LICITACIÓN SIMPLIFICADA",
        "LICITACIÓN PÚBLICA", "INVITACIÓN RESTRINGIDA",
        "CONCURSO SIMPLIFICADO", "Sin determinar",
    ),
}
PERCENT_PATTERN = re.compile(r"(?<!\d)(\d{1,3}(?:[.,]\d{1,2})?)\s*%")
WORD_PERCENTS = {
    "cero":0, "cinco":5, "diez":10, "quince":15, "veinte":20,
    "veinticinco":25, "treinta":30, "cuarenta":40, "cincuenta":50,
    "sesenta":60, "setenta":70, "ochenta":80, "noventa":90, "cien":100,
}


def _fold(s: Any) -> str:
    t = unicodedata.normalize("NFKD", str(s or "").casefold())
    return " ".join(re.sub(r"[^a-z0-9%]+", " ", "".join(
        c for c in t if not unicodedata.combining(c)
    )).split())


@dataclass(frozen=True)
class Advance:
    percent: str
    note: str = ""


def normalize_advance(raw: str | None) -> Advance:
    text = _fold(raw)
    if not text:
        return Advance("—", "Anticipo: el contrato no contiene un dato verificable.")
    negatives = (
        r"\bno se otorgara (?:porcentaje alguno de |ningun |un )?anticipo\b",
        r"\bno se otorgara porcentaje alguno de anticipo\b",
        r"\bno habra anticipo\b",
        r"\bno se concedera anticipo\b",
        r"\bno se otorgaran anticipos\b",
        r"\bsin anticipo\b",
        r"\bno se contempla anticipo\b",
        r"\banticipo de 0(?:[.,]0+)?\s*%\b",
    )
    percentages: set[Decimal] = set()
    for match in PERCENT_PATTERN.finditer(text):
        try:
            n=Decimal(match.group(1).replace(",","."))
        except InvalidOperation:
            continue
        if 0 <= n <= 100:
            percentages.add(n)
    if any(re.search(pattern, text) for pattern in negatives):
        note = (
            "Anticipo: la cláusula indica expresamente que no se "
            "otorgará; se presenta 0%."
        )
        if percentages - {Decimal(0)}:
            note += (
                " También aparece otro porcentaje en el texto; "
                "prevaleció la negación expresa. Cotejar la condición."
            )
        return Advance("0%", note)
    if len(percentages) > 1:
        return Advance("—", "Anticipo: existen porcentajes distintos; requiere revisión.")
    if len(percentages) == 1:
        n = next(iter(percentages))
        return Advance(f"{n.normalize():f}%", "")
    matches = set()
    for word, percent in WORD_PERCENTS.items():
        if re.search(r"\b"+word+r"\s+por\s+ciento\b",text):
            matches.add(percent)
    if len(matches)==1:
        return Advance(f"{next(iter(matches))}%", "Anticipo: porcentaje expresado en letras; conversión para presentación.")
    return Advance("—", "Anticipo: no se pudo aislar un porcentaje; revisar el texto literal.")


def _manual(record: Any) -> dict[str,str]:
    review = getattr(record, "verification", None) or {}
    if not isinstance(review, Mapping):
        return {}
    raw = review.get("campos", {})
    return {str(k):str(v) for k,v in raw.items() if
            (k in EDITABLE_FIELDS or k in EXTRA_FIELDS)
            and isinstance(v,(str,int)) and str(v).strip()}


def normalized_values(record: Any) -> tuple[dict[str,str], tuple[str,...]]:
    """Retorna datos normalizados para TODAS las vistas, con notas auditables."""
    raw = getattr(record,"full_values",None) or {}
    if not raw:
        legacy = getattr(record,"values",{}) or {}
        raw = {
            "numero_contrato":legacy.get("numero_contrato",""),
            "obra_servicio":legacy.get("nombre_obra",""),
            "contratista":legacy.get("contratista",""),
            "fecha_firma_contrato":legacy.get("fecha_firma",""),
            "fecha_inicio_contractual":legacy.get("fecha_inicio",""),
            "fecha_termino_contractual":legacy.get("fecha_termino",""),
            "monto_contrato":legacy.get("monto_con_iva",""),
            "anticipo":legacy.get("porcentaje_anticipo",""),
        }
    values = {name:str(raw.get(name) or "") for name in EDITABLE_FIELDS}
    notes=[]
    legal,technical=record_representation_fields(record)
    amount_quote=(getattr(record,"evidence",{}) or {}).get("monto_contrato") or {}
    amount_evidence = amount_quote.get("evidencia","") if isinstance(amount_quote,dict) else ""
    values["tipo_contrato"] = suggested_display_type(
        values.get("tipo_contrato"), values.get("monto_contrato"), amount_evidence,
    )
    values["modalidad_adjudicacion"] = normalize_award_method(
        values.get("modalidad_adjudicacion",""),
    )
    values["representante_legal"] = legal or "—"
    values["representante_tecnico"] = ""  # fuera del alcance del extractor nuevo
    for name in ("fecha_inicio_contractual","fecha_termino_contractual","fecha_firma_contrato"):
        values[name] = short_date(values.get(name,""))
    values["monto_contrato"] = format_contract_amount(
        values.get("monto_contrato",""), getattr(record,"currency",""),
    )
    advanced = normalize_advance(values.get("anticipo"))
    values["anticipo"] = advanced.percent
    if advanced.note:
        notes.append(advanced.note)
    iva_recognized = identify_record_iva(record).basis
    if iva_recognized == "Por confirmar":
        values["iva"]="Con IVA (16%)"
        notes.append(
            "IVA: SUPUESTO PROVISIONAL de la prueba; la cláusula del "
            "monto no acredita si incluye IVA. Se considera incluido "
            "al 16 % hasta que el auditor lo confirme o corrija."
        )
    else:
        values["iva"]=iva_recognized
    values["regimen"]=""
    values["ejercicio"]=""
    verified = _manual(record)
    for key, value in verified.items():
        values[key] = value
    if "iva" in verified:
        notes = [n for n in notes if not n.startswith("IVA: SUPUESTO")]
    if "anticipo" in verified:
        notes = [n for n in notes if not n.startswith("Anticipo:")]
    if getattr(record,"verification",None):
        notes.append(
            "Revisión manual: se aplicaron los valores confirmados o "
            "corregidos por el auditor; el texto literal sigue intacto."
        )
    return values,tuple(notes)


def verified_fields(record: Any) -> dict[str,str]:
    return _manual(record)
