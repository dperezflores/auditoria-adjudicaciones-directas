"""Presentación normalizada del contrato, sin modificar el texto literal guardado.

El lector nunca actualiza Extracciones/DatosContratoV2 ni invoca Gemini.
Toda transformación incierta se deja sin clasificar para cotejo documental.
"""
from __future__ import annotations

from datetime import date
import re
import unicodedata

from services.contract_portfolio import parse_amount

_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_MONTH_PATTERN = "|".join(_MONTHS)


def _fold(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or "").casefold())
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = re.sub(r"\bi\s*\.?\s*v\s*\.?\s*a\b", "iva", value)
    return " ".join(re.sub(r"[^a-z0-9%]+", " ", value).split())


def normalize_contract_type(raw: str) -> str:
    """Excluir 'tiempo determinado' y las fórmulas introductorias del contrato."""
    s = _fold(raw)
    if not s:
        return "—"
    unit = bool(re.search(r"\bprecios?\s+unitarios?\b", s))
    fixed = bool(re.search(r"\bprecios?\s+alzados?\b|\ba\s+precio\s+alzado\b|\bprecio\s+global\b", s))
    if unit and fixed:
        return "Mixto (precios unitarios y precio alzado)"
    if unit:
        return "Precios Unitarios"
    if fixed:
        return "Precio Alzado"
    return "—"


def normalize_award_method(raw: str) -> str:
    """Clasificar procedimientos expresos, sin inferir por número o monto."""
    s = _fold(raw)
    if not s:
        return "—"
    found: set[str] = set()
    if re.search(r"\badjudicacion\s+directa\b|\basignacion\s+directa\b|\badjudicad[ao]\s+(?:en\s+forma\s+)?directa\b", s):
        found.add("ADJUDICACIÓN DIRECTA")
    if re.search(r"\blicitacion\s+(?:publica\s+)?simplificad[ao]\b|\blicitacion\s+de\s+caracter\s+simplificad[ao]\b", s):
        found.add("LICITACIÓN SIMPLIFICADA")
    if re.search(r"\blicitacion\s+publica\b", s) and "LICITACIÓN SIMPLIFICADA" not in found:
        found.add("LICITACIÓN PÚBLICA")
    if re.search(r"\binvitacion\s+(?:restringida|a\s+cuando\s+menos\s+(?:tres|3)\s+(?:personas|contratistas|participantes)|a\s+(?:tres|3)\s+(?:personas|contratistas))\b", s):
        found.add("INVITACIÓN RESTRINGIDA")
    if re.search(r"\bconcurso\s+simplificad[ao]\b", s):
        found.add("CONCURSO SIMPLIFICADO")
    return next(iter(found)) if len(found) == 1 else "—"


def short_date(raw: str) -> str:
    """DD/MM/AAAA solo cuando la fecha es válida e inequívoca.

    En expresiones ilegibles, con varias fechas o con dos dígitos de año,
    conservamos el texto original para no ocultar información.
    """
    if not isinstance(raw, str) or not raw.strip():
        return "—"
    text = raw.strip()
    s = unicodedata.normalize("NFKD", text.casefold())
    s = "".join(c for c in s if not unicodedata.combining(c))
    candidates: list[date] = []
    patterns = (
        (r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)", "iso"),
        (r"(?<!\d)(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{4})(?!\d)", "numeric"),
        (r"(?<!\d)(\d{1,2})\s*(?:dias?\s*)?(?:de[l]?\s*)?"
         r"(?:mes\s+de\s+)?("+_MONTH_PATTERN+r")\s+"
         r"(?:de|del)\s+(?:ano\s+(?:de\s+)?)?(\d{4})(?!\d)", "month"),
    )
    for pattern, kind in patterns:
        for match in re.finditer(pattern, s):
            a, b, c = match.groups()
            try:
                if kind == "iso":
                    candidates.append(date(int(a), int(b), int(c)))
                elif kind == "numeric":
                    candidates.append(date(int(c), int(b), int(a)))
                else:
                    candidates.append(date(int(c), _MONTHS[b], int(a)))
            except ValueError:
                return text
    if not candidates or len(set(candidates)) != 1:
        return text
    return candidates[0].strftime("%d/%m/%Y")



def format_contract_amount(raw: str, currency: str = "") -> str:
    """Mostrar únicamente el importe literal numérico con formato monetario.

    No calcula impuestos, recargos ni importes complementarios. Si el texto
    contiene varios importes o no puede interpretarse sin ambigüedad, la
    tabla muestra un guion y conserva el texto original en la ficha.
    """
    amount = parse_amount(raw)
    if amount is None:
        return "—"
    if currency == "EUR":
        return f"€{amount:,.2f}"
    if currency == "USD":
        return f"US${amount:,.2f}"
    return f"${amount:,.2f}"
