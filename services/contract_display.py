"""Presentación normalizada del contrato, sin modificar el texto literal guardado.

El lector nunca actualiza Extracciones/DatosContratoV2 ni invoca Gemini.
Toda transformación incierta se deja sin clasificar para cotejo documental.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import re
import unicodedata

from services.contract_portfolio import ContractRecord, money_text, parse_amount

IVA_ESTANDAR = Decimal("0.16")
_CENT = Decimal("0.01")
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


def _iva_basis(text: str) -> str | None:
    s = _fold(text)
    without = bool(re.search(
        r"\bsin\s+(?:el\s+)?iva\b|\bno\s+incluye\s+(?:el\s+)?iva\b|"
        r"\biva\s+no\s+incluid[oa]\b|\bantes\s+de(?:l)?\s+iva\b|"
        r"\bmas\s+(?:el\s+)?iva\b|\biva\s+por\s+separado\b|"
        r"\bexcluye\s+(?:el\s+)?iva\b|\bsubtotal\s+sin\s+iva\b", s
    ))
    with_tax = bool(re.search(
        r"\bcon\s+iva\b|\biva\s+incluid[oa]\b|"
        r"\bincluye\s+(?:el\s+)?iva\b|\bincluid[oa]\s+(?:el\s+)?iva\b|"
        r"\bincluyendo\s+(?:el\s+)?iva\b|\bincluye\s+(?:el\s+)?impuesto\s+al\s+valor\s+agregado\b|"
        r"\biva\s+comprendido\b", s
    ))
    if without == with_tax:
        return None
    return "sin" if without else "con"


def _amount_reference_present(raw: str, evidence: str) -> bool:
    """No asociar una mención de IVA a un importe distinto del consultado."""
    if not raw or not evidence:
        return False
    # Elegir el fragmento numérico más largo, que suele ser el monto monetario.
    matches = re.findall(r"\d[\d.,]*", raw)
    amounts = [x.rstrip(".,") for x in matches if len(re.sub(r"\D", "", x)) >= 4]
    if not amounts:
        return False
    reference = max(amounts, key=lambda x: len(re.sub(r"\D", "", x)))
    if reference in evidence:
        return True
    digits = re.sub(r"\D", "", reference)
    return len(digits) >= 5 and digits in re.sub(r"\D", "", evidence)


def _rate_from_context(text: str) -> tuple[Decimal | None, bool]:
    """Detectar tasas porcentuales explícitas adyacentes al término IVA."""
    s = _fold(text)
    found: set[Decimal] = set()
    for raw in re.findall(r"\biva\s*(?:del?\s+)?(\d{1,2}(?:[.,]\d+)?)\s*%", s):
        found.add(Decimal(raw.replace(",", ".")) / 100)
    for raw in re.findall(r"\b(\d{1,2}(?:[.,]\d+)?)\s*%\s*(?:de\s*)?iva\b", s):
        found.add(Decimal(raw.replace(",", ".")) / 100)
    if len(found) > 1:
        return None, True
    return (next(iter(found)), False) if found else (None, False)


def financial_cells(record: ContractRecord, raw: str) -> dict[str, str]:
    """Columnas con y sin IVA; no asume si el importe lo incluye o excluye.

    Cuando sí consta la base pero no la tasa, calcula al 16% como SUPUESTO
    explícitamente etiquetado. El auditor debe cotejarlo con el contrato.
    """
    cells = {
        "Monto del contrato con IVA": "—",
        "Monto del contrato sin IVA": "—",
        "Monto del contrato (IVA no indicado)": "—",
        "IVA utilizado en el cálculo": "—",
    }
    if not raw or raw == "—":
        return cells
    amount = parse_amount(raw)
    if amount is None:
        # Cuando el importe incluye una tasa explícita, removerla solo para
        # interpretar la cantidad monetaria; no eliminar otros números.
        cleaned = re.sub(
            r"\b(?:i\s*\.?\s*v\s*\.?\s*a|iva)\s*(?:del?\s*)?\d{1,2}(?:[.,]\d+)?\s*%",
            "", raw, flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"\b\d{1,2}(?:[.,]\d+)?\s*%\s*(?:de\s*)?(?:i\s*\.?\s*v\s*\.?\s*a|iva)\b",
            "", cleaned, flags=re.IGNORECASE,
        )
        amount = parse_amount(cleaned)
    if amount is None:
        return cells
    formatted = money_text(amount, record.currency)
    evidence = record.evidence.get("monto_contrato") or record.evidence.get("monto_con_iva") or {}
    quote = str(evidence.get("evidencia") or "")
    basis = _iva_basis(raw)
    context = raw
    if not basis and _amount_reference_present(raw, quote):
        basis = _iva_basis(quote)
        context = quote
    # En el esquema de contrato anterior el campo monto_con_iva tiene
    # significado explícito y no se amplía a contratos v2 ambiguos.
    if not basis and record.source_schema == "contrato-v1":
        basis = "con"
    if basis is None:
        cells["Monto del contrato (IVA no indicado)"] = formatted
        return cells
    rate, ambiguous = _rate_from_context(context)
    if ambiguous:
        if basis == "con":
            cells["Monto del contrato con IVA"] = formatted
        else:
            cells["Monto del contrato sin IVA"] = formatted
        cells["IVA utilizado en el cálculo"] = "Tasa contradictoria: verificar"
        return cells
    explicit = rate is not None
    if not explicit:
        rate = IVA_ESTANDAR
    cells["IVA utilizado en el cálculo"] = (
        f"{(rate * 100).normalize():f}% (documentado)" if explicit
        else "16% (supuesto; verificar)"
    )
    if basis == "con":
        cells["Monto del contrato con IVA"] = formatted
        if rate > Decimal("-1"):
            base = (amount / (Decimal("1") + rate)).quantize(_CENT, rounding=ROUND_HALF_UP)
            cells["Monto del contrato sin IVA"] = money_text(base, record.currency)
    else:
        cells["Monto del contrato sin IVA"] = formatted
        total = (amount * (Decimal("1") + rate)).quantize(_CENT, rounding=ROUND_HALF_UP)
        cells["Monto del contrato con IVA"] = money_text(total, record.currency)
    return cells
