"""Reglas documentales prudentes sobre tipo de contrato y roles de firmantes.

Las frases que aparezcan en evidencia deben corresponder a la parte
contractual y a la persona analizada. No derivar un representante a partir de
un nombre, profesión, RFC, posición de una firma o mera presencia en el PDF.
"""
from __future__ import annotations

import re
import unicodedata


NO_APLICA_FISICA = "No aplica – Contratista persona física"


def fold(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def _person_name(value: str | None) -> str:
    name = fold(value)
    return re.sub(
        r"^(?:(?:c|ciudadan[oa]|arq|arquitect[oa]|ing|ingenier[oa]"
        r"|lic|licenciad[oa]|dr|dra)\s+)+",
        "", name,
    ).strip()


def _name_in_evidence(name: str | None, evidence: str | None) -> bool:
    norm = _person_name(name)
    return bool(norm and len(norm) >= 9 and norm in fold(evidence))


def is_persona_fisica(
    contractor: str | None,
    contractor_evidence: str | None,
) -> bool:
    """Requiere declaración vinculada al CONTRATISTA; un RFC no es prueba."""
    entity = fold(contractor)
    citation = fold(contractor_evidence)
    if not entity or not citation or not _name_in_evidence(contractor, contractor_evidence):
        return False
    # Razón social y apoderado firmante no prueban persona física contratista.
    if re.search(
        r"\b(?:s a (?:de c v)?|s de r l|s a p i|sociedad anonima"
        r"|sociedad de responsabilidad limitada|asociacion civil)\b",
        entity,
    ):
        return False
    return bool(re.search(
        r"\bpersona fisica\b|\bpor su propio derecho\b"
        r"|\bpor derecho propio\b|\ben su propio nombre y derecho\b",
        citation,
    ))


def authorized_technical_role(
    name: str | None,
    evidence: str | None,
) -> bool:
    """Nombre y función técnica de la contratista deben estar explícitos."""
    citation = fold(evidence)
    if not _name_in_evidence(name, evidence):
        return False
    if not re.search(
        r"\b(?:representante tecnico|responsable tecnico|"
        r"superintendente de (?:construccion|obra))\b",
        citation,
    ):
        return False
    # Una persona técnica designada por la contratante no es representante
    # técnico de la empresa. Citas de ambas partes en una misma firma
    # son ambiguas y se remiten a revisión.
    if re.search(r"\b(?:de la contratante|por la contratante|del municipio"
                 r"|por el municipio|representante del municipio)\b", citation):
        return False
    if not re.search(
        r"\b(?:contratista|proyectista|empresa|prestador de servicios"
        r"|proveedor)\b",
        citation,
    ):
        # Aunque conste «responsable técnico», no necesariamente es de
        # la empresa contratista; no convertirlo en su representante.
        return False
    return True


def authorized_legal_role(name: str | None, evidence: str | None) -> bool:
    """No basta con aparecer como firmante en la última página."""
    citation = fold(evidence)
    if not _name_in_evidence(name, evidence):
        return False
    return bool(re.search(
        r"\b(?:representante legal|apoderad[oa] legal|apoderad[oa] general"
        r"|en representacion de|representante de la empresa)\b",
        citation,
    ))


# Frase contractual inequívoca de cálculo por PU, aun si la carátula omite
# la denominación del tipo de contrato. No se infiere por la simple mención
# de una tarjeta de PU o una cotización separada.
_PRICE_BASIS = re.compile(
    r"(?:(?:con\s+base\s+en\s+(?:los\s+)?)|(?:bajo\s+la\s+modalidad\s+de\s+)"
    r"|(?:contrato\s+a\s+)|(?:a\s+))?"
    r"(?:precios?\s+unitarios?)"
    r"(?:\s+y\s+(?:vol[uú]menes?|cantidades?)(?:\s+autorizad[ao]s?)?)?",
    re.IGNORECASE,
)


def literal_unit_price_basis(
    amount_value: str | None,
    amount_evidence: str | None,
) -> str:
    """Retorna un fragmento exacto de evidencia SI ES cláusula de precio."""
    text = str(amount_evidence or "")
    if not text or not amount_value:
        return ""
    match = _PRICE_BASIS.search(text)
    if not match:
        return ""
    # Menciones genéricas a precios unitarios fuera de la base de pago no
    # son suficientes para llenar tipo_contrato.
    context = fold(text)
    if not re.search(
        r"\b(?:monto del contrato|importe total|precio del contrato"
        r"|cantidad de|cantidad que|pagar|pago|volumenes autorizados"
        r"|cantidades autorizadas|con base en los precios unitarios)\b",
        context,
    ):
        return ""
    if re.search(r"\b(?:precio alzado|precios alzados|precio global)\b", context):
        return ""
    phrase = fold(match.group(0))
    if not re.search(r"\bprecios? unitarios?\b", phrase):
        return ""
    # El fragmento debe estar en la misma cita que el monto contractual.
    from services.amount_iva import _same_amount_in_quote
    if not _same_amount_in_quote(amount_value, text):
        return ""
    return match.group(0)


def suggested_display_type(
    raw_type: str | None,
    amount_value: str | None,
    amount_evidence: str | None,
) -> str:
    from services.contract_display import normalize_contract_type
    classified = normalize_contract_type(raw_type or "")
    if classified != "—":
        return classified
    evidence = literal_unit_price_basis(amount_value, amount_evidence)
    return "Precios Unitarios" if evidence else "—"


def record_representation_fields(record: object) -> tuple[str, str]:
    """Valores de presentación; JAMÁS reescribe extracciones históricas."""
    fields = getattr(record, "full_values", None)
    if fields is None:
        return "", ""
    evidence = getattr(record, "evidence", None) or {}
    contractor = fields.get("contratista") or ""
    contractor_quote = (evidence.get("contratista") or {}).get("evidencia") or ""
    legal = fields.get("representante_legal") or ""
    technical = fields.get("representante_tecnico") or ""
    legal_quote = (evidence.get("representante_legal") or {}).get("evidencia") or ""
    technical_quote = (evidence.get("representante_tecnico") or {}).get("evidencia") or ""

    physically = (
        is_persona_fisica(contractor, contractor_quote)
        or is_persona_fisica(contractor, legal_quote)
    )
    if physically and (
        not legal
        or fold(legal) == fold(NO_APLICA_FISICA)
        or _person_name(legal) == _person_name(contractor)
    ):
        legal = NO_APLICA_FISICA
    elif legal and fold(legal) == fold(NO_APLICA_FISICA):
        # Sin evidencia de PF, no se admite el marcador.
        legal = ""
    elif legal and not authorized_legal_role(legal, legal_quote):
        legal = ""

    if technical and not authorized_technical_role(technical, technical_quote):
        technical = ""
    return legal, technical
