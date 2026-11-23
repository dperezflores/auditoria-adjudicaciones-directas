"""Ranking reproducible de contratistas sobre los contratos filtrados.

No hace peticiones externas ni altera las extracciones. La identidad se
agrupa por RFC válido cuando existe, y por nombre normalizado cuando no.
Una variante de razón social sin RFC solo se vincula a un RFC si el nombre
coincide de forma inequívoca. No se agrupan homónimos con RFC distintos.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import re
from typing import Sequence

from services.contract_normalization import normalized_values
from services.contract_portfolio import ContractRecord
from services.contract_role_rules import fold


_RFC = re.compile(r"^[A-Z&Ñ]{3,4}\d{6}[A-Z0-9]{3}$")
_MISSING = frozenset({
    "", "sin identificar", "no localizado", "sin dato",
    "no identificado", "por identificar", "no aplica",
})


@dataclass(frozen=True)
class ContractorCount:
    name: str
    count: int
    identity: str
    rfc: str


@dataclass(frozen=True)
class ContractorRanking:
    top: tuple[ContractorCount, ...]
    unique_contractors: int
    contracts_without_contractor: int


def _name_key(raw: str) -> str:
    name = fold(raw)
    # Normalización conservadora de abreviaturas societarias: no realiza
    # coincidencias difusas que puedan mezclar empresas distintas.
    name = re.sub(r"\bs\s+a\b", "sa", name)
    name = re.sub(r"\bc\s+v\b", "cv", name)
    return name if name not in _MISSING else ""


def _rfc_key(raw: str) -> str:
    compact = re.sub(r"[^A-Z0-9&Ñ]", "", str(raw or "").upper())
    return compact if _RFC.fullmatch(compact) else ""


def rank_contractors(
    records: Sequence[ContractRecord], limit: int = 10,
) -> ContractorRanking:
    """Cuenta un contrato activo por documento, ya sujeto a los filtros.

    Para la ficha de contratista se utilizan correcciones humanas guardadas
    en `VerificacionesContrato`, si las hay, sin reescribir el PDF original.
    """
    if limit < 1:
        raise ValueError("El límite del ranking debe ser mayor que cero.")

    pending: list[tuple[str, str, str]] = []
    name_to_rfcs: dict[str, set[str]] = defaultdict(set)
    seen_docs: set[tuple[str, str]] = set()
    for record in records:
        doc_id = (record.obra_id, record.documento_id)
        if doc_id in seen_docs:
            continue
        seen_docs.add(doc_id)
        values, _ = normalized_values(record)
        name = str(values.get("contratista") or "").strip()
        name_key = _name_key(name)
        rfc = _rfc_key(values.get("rfc") or "")
        if name_key and rfc:
            name_to_rfcs[name_key].add(rfc)
        pending.append((name if name_key else "", name_key, rfc))

    buckets: dict[str, Counter[str]] = defaultdict(Counter)
    rfc_by_bucket: dict[str, str] = {}
    unidentified = 0
    for name, name_key, rfc in pending:
        if not name_key and not rfc:
            unidentified += 1
            continue
        unique_rfc = name_to_rfcs.get(name_key, set()) if name_key else set()
        resolved_rfc = rfc or (next(iter(unique_rfc)) if len(unique_rfc) == 1 else "")
        bucket = f"RFC:{resolved_rfc}" if resolved_rfc else f"NOMBRE:{name_key}"
        buckets[bucket][name or f"RFC {resolved_rfc}"] += 1
        if resolved_rfc:
            rfc_by_bucket[bucket] = resolved_rfc

    counts = []
    for bucket, names in buckets.items():
        # Denominación visible tomada del expediente, nunca inventada.
        name = sorted(names, key=lambda n: (-names[n], -len(n), n.casefold()))[0]
        counts.append(ContractorCount(
            name=name,
            count=sum(names.values()),
            identity=bucket,
            rfc=rfc_by_bucket.get(bucket, ""),
        ))

    counts.sort(key=lambda item: (-item.count, fold(item.name), item.identity))
    return ContractorRanking(
        top=tuple(counts[:limit]),
        unique_contractors=len(counts),
        contracts_without_contractor=unidentified,
    )
