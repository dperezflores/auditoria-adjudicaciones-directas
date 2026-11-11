"""Identificación conservadora del IVA asociado al IMPORTE CONTRACTUAL.

Utiliza el texto literal y, si éste no basta, la evidencia de ese mismo
campo. Nunca lee legislación o anticipo para deducir el impuesto del contrato.
No cambia lo extraído por Gemini ni modifica la base de datos.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re
import unicodedata

from services.contract_portfolio import parse_amount


@dataclass(frozen=True)
class IvaAmountEvidence:
    basis: str
    source: str
    quote: str
    page: int | None


def _plain(text: str) -> str:
    s = unicodedata.normalize("NFKD", str(text or "").casefold())
    s = "".join(c for c in s if not unicodedata.combining(c))
    normalized = " ".join(re.sub(r"[^a-z0-9%]+", " ", s).split())
    # «I.V.A.» y «I. V. A.» son grafías frecuentes en los contratos.
    return re.sub(r"\bi\s+v\s+a\b", "iva", normalized)


_INCLUDES = (
    r"\biva\s+incluid[oa]s?\b",
    r"\bcon\s+(?:el\s+)?iva\b",
    r"(?<!no )\bincluye\s+(?:el\s+)?iva\b",
    r"\bincluido\s+(?:el\s+)?iva\b",
    r"\biva\s+(?:ya\s+)?comprendido\b",
    r"\bimpuesto\s+al\s+valor\s+agregado\s+incluid[oa]\b",
    r"(?<!no )\bincluye\s+(?:el\s+)?impuesto\s+al\s+valor\s+agregado\b",
)
_EXCLUDES = (
    r"\bsin\s+iva\b",
    r"\biva\s+no\s+incluid[oa]\b",
    r"\bno\s+incluye\s+(?:el\s+)?iva\b",
    r"\bno\s+incluye\s+(?:el\s+)?impuesto\s+al\s+valor\s+agregado\b",
    r"\bmas\s+(?:el\s+)?iva\b",
    r"\biva\s+por\s+separado\b",
    r"\bantes\s+(?:de|del)\s+iva\b",
    r"\bsin\s+incluir\s+(?:el\s+)?iva\b",
    r"\b(?:mas|adicionalmente)\s+el\s+impuesto\s+al\s+valor\s+agregado\b",
)


def _classify(text: str) -> str:
    s = _plain(text)
    included = any(re.search(pattern, s) for pattern in _INCLUDES)
    excluded = any(re.search(pattern, s) for pattern in _EXCLUDES)
    if included == excluded:
        return "Por confirmar"
    return "Con IVA (16%)" if included else "Sin IVA"


def _same_amount_in_quote(amount_text: str, quote: str) -> bool:
    """La cita debe contener el mismo IMPORTE, no solo la palabra IVA.

    El fragmento puede contener centavos en letras (55/100) y otros números,
    pero al menos un token monetario tiene que coincidir exactamente.
    """
    amount = parse_amount(amount_text)
    if amount is None or not quote:
        return False
    for token in re.findall(r"(?<!\d)\d[\d,.]*", quote):
        candidate = parse_amount(token)
        if candidate is not None and candidate == amount:
            return True
    return False


def identify_contract_amount_iva(
    amount_text: str, *, evidence: str = "", page: int | None = None,
) -> IvaAmountEvidence:
    """Devuelve clasificación, fuente de la clasificación y cita rastreable.

    - El valor conserva prioridad cuando expresa claramente el tratamiento.
    - La evidencia se considera SOLO si cita el mismo importe.
    - Indicaciones contradictorias => Por confirmar, no sobreescribir datos.
    - Un texto que solamente contiene «IVA 16 %» no significa «IVA incluido».
    """
    amount_result = _classify(amount_text)
    quote_result = (
        _classify(evidence) if _same_amount_in_quote(amount_text, evidence)
        else "Por confirmar"
    )
    if (
        amount_result != "Por confirmar"
        and quote_result != "Por confirmar"
        and amount_result != quote_result
    ):
        return IvaAmountEvidence(
            "Por confirmar", "Indicaciones contradictorias en monto y evidencia",
            evidence, page,
        )
    if amount_result != "Por confirmar":
        return IvaAmountEvidence(
            amount_result, "Texto literal del importe",
            evidence or amount_text, page,
        )
    if quote_result != "Por confirmar":
        return IvaAmountEvidence(
            quote_result, "Evidencia de la cláusula del monto",
            evidence, page,
        )
    return IvaAmountEvidence("Por confirmar", "No acreditado", "", None)



def identify_record_iva(record: object) -> IvaAmountEvidence:
    """Acceso único a los campos ya guardados de contrato-v2; sin llamadas externas."""
    fields = getattr(record, "full_values", None) or {}
    evidence = getattr(record, "evidence", None) or {}
    literal = str(fields.get("monto_contrato") or "")
    detail = evidence.get("monto_contrato") or {}
    if not isinstance(detail, dict):
        detail = {}
    page = detail.get("pagina")
    if not isinstance(page, int) or page <= 0:
        page = None
    return identify_contract_amount_iva(
        literal,
        evidence=str(detail.get("evidencia") or ""),
        page=page,
    )
