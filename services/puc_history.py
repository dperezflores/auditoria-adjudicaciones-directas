"""Cotejos históricos del PUC, independientes de las extracciones originales.

Libro de eventos en Google Sheets. Una revisión corresponde a las versiones
exactas de CONTRATO y PUC y nunca se hereda a un PDF sustituido.
La declaración del auditor es evidencia por cotejar, no un dictamen automático.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import re
from typing import Any
from uuid import uuid4

from services.contract_portfolio import parse_amount, read_contract_portfolio
from services.sheets_service import _last_column

SHEET = "RevisionesPUC"
HEADERS = (
    "revision_id", "fecha_utc", "obra_id", "contrato_documento_id",
    "contrato_cache_key", "puc_documento_id", "puc_cache_key",
    "fecha_asignacion", "vigencia_desde", "vigencia_hasta",
    "estado_registro_historico", "capital_historico", "fecha_registro_capital",
    "alcance_capital", "fuente", "referencia", "conclusion_capital",
    "conclusion_vigencia", "observaciones", "auditor",
)
CONCLUSIONS = ("Pendiente", "Acreditado", "No acreditado", "No concluyente")
ALCANCES_CAPITAL = (
    "", "Historial completo hasta asignación",
    "Certificación oficial del capital a fecha",
    "Movimiento aislado: último valor sin acreditar",
)
STATES = ("", "VIGENTE", "REFRENDADO", "SUSPENDIDO", "CANCELADO", "NO DETERMINADO")
_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class PucHistoryError(ValueError):
    """Error de identidad, vigencia documental o evidencia del cotejo."""


@dataclass(frozen=True)
class PucReview:
    revision_id: str
    fecha_utc: str
    obra_id: str
    contrato_documento_id: str
    contrato_cache_key: str
    puc_documento_id: str
    puc_cache_key: str
    fecha_asignacion: str
    vigencia_desde: str
    vigencia_hasta: str
    estado_registro_historico: str
    capital_historico: str
    fecha_registro_capital: str
    alcance_capital: str
    fuente: str
    referencia: str
    conclusion_capital: str
    conclusion_vigencia: str
    observaciones: str
    auditor: str

    def values(self) -> list[str]:
        return [getattr(self, key) for key in HEADERS]


def parse_review_date(value: str):
    if not value:
        return None
    if not re.fullmatch(r"\d{2}/\d{2}/\d{4}", value):
        raise PucHistoryError("Las fechas revisadas deben tener formato DD/MM/AAAA.")
    try:
        return datetime.strptime(value, "%d/%m/%Y").date()
    except ValueError as exc:
        raise PucHistoryError("La fecha revisada no existe en el calendario.") from exc


def make_puc_review(
    *, obra_id: str, contrato_documento_id: str, contrato_cache_key: str,
    puc_documento_id: str, puc_cache_key: str, auditor: str,
    fecha_asignacion: str = "", vigencia_desde: str = "",
    vigencia_hasta: str = "", estado_registro_historico: str = "",
    capital_historico: str = "", fecha_registro_capital: str = "",
    alcance_capital: str = "", fuente: str = "", referencia: str = "",
    conclusion_capital: str = "Pendiente", conclusion_vigencia: str = "Pendiente",
    observaciones: str = "", revision_id: str | None = None,
) -> PucReview:
    ids = (obra_id, contrato_documento_id, contrato_cache_key,
           puc_documento_id, puc_cache_key)
    if any(not isinstance(x, str) or not x.strip() for x in ids):
        raise PucHistoryError("Falta la identidad de contrato o PUC para guardar la revisión.")
    if not _EMAIL.fullmatch(str(auditor or "").strip()):
        raise PucHistoryError("Se requiere una sesión con correo de auditor verificado.")
    if (conclusion_capital not in CONCLUSIONS
            or conclusion_vigencia not in CONCLUSIONS
            or estado_registro_historico not in STATES
            or alcance_capital not in ALCANCES_CAPITAL):
        raise PucHistoryError("Conclusión, alcance de capital o estado PUC no permitido.")
    fields = dict(
        fecha_asignacion=fecha_asignacion.strip(), vigencia_desde=vigencia_desde.strip(),
        vigencia_hasta=vigencia_hasta.strip(),
        fecha_registro_capital=fecha_registro_capital.strip(),
    )
    parsed = {key: parse_review_date(val) for key, val in fields.items()}
    if bool(parsed["vigencia_desde"]) != bool(parsed["vigencia_hasta"]):
        raise PucHistoryError("Para acreditar un periodo histórico indica ambas fechas de vigencia.")
    if (parsed["vigencia_desde"] and parsed["vigencia_hasta"]
            and parsed["vigencia_desde"] > parsed["vigencia_hasta"]):
        raise PucHistoryError("El inicio de vigencia es posterior al vencimiento.")
    if bool(capital_historico.strip()) != bool(parsed["fecha_registro_capital"]):
        raise PucHistoryError("El capital histórico requiere importe y fecha de registro ante el PUC.")
    if capital_historico.strip() and not alcance_capital:
        raise PucHistoryError("Indica si el soporte acredita el último capital aplicable a la asignación.")
    if alcance_capital and not capital_historico.strip():
        raise PucHistoryError("El alcance del historial de capital requiere importe acreditado.")
    if capital_historico.strip():
        amount = parse_amount(capital_historico.strip())
        if (amount is None or amount < Decimal("0")
                or any(x in capital_historico.upper() for x in ("USD", "EUR", "€"))):
            raise PucHistoryError("Capital histórico: importe único en MXN y no negativo.")
        capital_historico = str(amount.quantize(Decimal("0.01")))
    if not (parsed["fecha_asignacion"] or parsed["vigencia_desde"]
            or capital_historico or estado_registro_historico):
        raise PucHistoryError("Indica al menos un hecho histórico que deseas cotejar.")
    if not fuente.strip() or not referencia.strip() or not observaciones.strip():
        raise PucHistoryError(
            "Son obligatorios fuente, referencia verificable y explicación del cotejo."
        )
    limits = (("fuente", fuente, 300), ("referencia", referencia, 800),
              ("observaciones", observaciones, 1800))
    if any(len(text.strip()) > limit for _, text, limit in limits):
        raise PucHistoryError("La referencia o explicación excede la longitud permitida.")
    return PucReview(
        revision_id=revision_id or uuid4().hex,
        fecha_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        obra_id=obra_id.strip(),
        contrato_documento_id=contrato_documento_id.strip(),
        contrato_cache_key=contrato_cache_key.strip(),
        puc_documento_id=puc_documento_id.strip(),
        puc_cache_key=puc_cache_key.strip(),
        fecha_asignacion=fields["fecha_asignacion"],
        vigencia_desde=fields["vigencia_desde"],
        vigencia_hasta=fields["vigencia_hasta"],
        estado_registro_historico=estado_registro_historico,
        capital_historico=capital_historico.strip(),
        fecha_registro_capital=fields["fecha_registro_capital"],
        alcance_capital=alcance_capital,
        fuente=fuente.strip(), referencia=referencia.strip(),
        conclusion_capital=conclusion_capital,
        conclusion_vigencia=conclusion_vigencia,
        observaciones=observaciones.strip(), auditor=auditor.strip().casefold(),
    )


def _titles(client: Any, spreadsheet_id: str) -> set[str]:
    response = client.spreadsheets().get(
        spreadsheetId=spreadsheet_id, fields="sheets.properties.title",
    ).execute()
    return {
        row.get("properties", {}).get("title", "")
        for row in response.get("sheets") or []
    }


def read_puc_reviews(client: Any, spreadsheet_id: str) -> list[PucReview]:
    """Devuelve todos los eventos. Si aún no existe la pestaña no modifica Sheets."""
    if SHEET not in _titles(client, spreadsheet_id):
        return []
    last = _last_column(len(HEADERS))
    response = client.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"'{SHEET}'!A1:{last}",
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    rows = response.get("values") or []
    if not rows or tuple(str(x) for x in rows[0]) != HEADERS:
        raise PucHistoryError("Encabezados incompatibles en RevisionesPUC.")
    reviews, seen = [], set()
    for line in rows[1:]:
        values = [str(x) if x is not None else "" for x in line[:len(HEADERS)]]
        values += [""] * (len(HEADERS) - len(values))
        if not any(values):
            continue
        item = PucReview(*values)
        if not item.revision_id or item.revision_id in seen:
            raise PucHistoryError("Historial PUC: revisión duplicada o sin identificador.")
        seen.add(item.revision_id)
        reviews.append(item)
    return reviews


def latest_puc_review(records: list[PucReview], contract: Any, puc: Any) -> PucReview | None:
    """El último evento solo aplica a la misma obra y dos versiones documentales."""
    if puc is None:
        return None
    identity = (contract.obra_id, contract.documento_id, contract.cache_key,
                puc.documento_id, puc.cache_key)
    for review in reversed(records):
        if (review.obra_id, review.contrato_documento_id, review.contrato_cache_key,
                review.puc_documento_id, review.puc_cache_key) == identity:
            return review
    return None


def save_puc_review(client: Any, spreadsheet_id: str, review: PucReview) -> str:
    """Guardar bajo get_writer_lock; revisar antes las dos versiones activas."""
    # Validar de nuevo incluso si el llamador creó PucReview directamente.
    make_puc_review(**{
        key: getattr(review, key) for key in (
            "obra_id", "contrato_documento_id", "contrato_cache_key",
            "puc_documento_id", "puc_cache_key", "auditor", "fecha_asignacion",
            "vigencia_desde", "vigencia_hasta", "estado_registro_historico",
            "capital_historico", "fecha_registro_capital", "alcance_capital",
            "fuente", "referencia", "conclusion_capital", "conclusion_vigencia",
            "observaciones",
        )
    })
    from services.capital_contable import read_capital_sources
    contracts = read_contract_portfolio(client, spreadsheet_id).records
    sources = read_capital_sources(client, spreadsheet_id)
    matches = [
        x for x in contracts
        if (x.obra_id, x.documento_id, x.cache_key) == (
            review.obra_id, review.contrato_documento_id, review.contrato_cache_key
        )
    ]
    puc = sources.puc_by_work.get(review.obra_id)
    if (len(matches) != 1 or puc is None
            or (puc.documento_id, puc.cache_key) != (
                review.puc_documento_id, review.puc_cache_key
            )):
        raise PucHistoryError(
            "Contrato o PUC sustituidos/no analizados. Actualiza antes de guardar."
        )
    existing = read_puc_reviews(client, spreadsheet_id)
    for previous in existing:
        if previous.revision_id == review.revision_id:
            if previous != review:
                raise PucHistoryError("El identificador de revisión ya tiene otro contenido.")
            return previous.revision_id
    if SHEET not in _titles(client, spreadsheet_id):
        client.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": SHEET}}}]},
        ).execute()
        client.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id, range=f"'{SHEET}'!A1:T1",
            valueInputOption="RAW", body={"values": [list(HEADERS)]},
        ).execute()
    result = client.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id, range=f"'{SHEET}'!A:T",
        valueInputOption="RAW", insertDataOption="INSERT_ROWS",
        body={"values": [review.values()]},
    ).execute()
    if int((result.get("updates") or {}).get("updatedRows") or 0) != 1:
        raise PucHistoryError(
            "Sheets no confirmó el guardado; consulta RevisionesPUC antes de repetir."
        )
    return review.revision_id
