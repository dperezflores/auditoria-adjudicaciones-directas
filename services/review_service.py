"""Cotejo manual auditable de campos contractuales (sin Gemini).

La pestaña RevisionesContrato es un libro de eventos append-only.
El revisor confirma o corrige el valor aportando página y evidencia,
o registra No localizado con justificación. Nunca altera DatosContrato.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any, Sequence
from uuid import uuid4

from services.gemini_compact_schema import CAMPOS_CONTRATO
from services.extraction_store import DOCUMENT_HEADERS, CONTRACT_HEADERS

REVIEW_HEADERS = (
    "revision_id", "fecha_utc", "obra_id", "documento_id", "cache_key",
    "campo", "decision", "valor_extraido", "valor_cotejado",
    "pagina", "evidencia", "justificacion", "revisor_email",
)
DECISIONS = ("Confirmado", "Corregido", "No localizado")
_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class ReviewError(ValueError):
    """Un cotejo no es consistente o carece de evidencia suficiente."""


@dataclass(frozen=True)
class ReviewRecord:
    revision_id: str
    fecha_utc: str
    obra_id: str
    documento_id: str
    cache_key: str
    campo: str
    decision: str
    valor_extraido: str
    valor_cotejado: str
    pagina: str
    evidencia: str
    justificacion: str
    revisor_email: str

    def values(self) -> list[str]:
        return [str(getattr(self, key)) for key in REVIEW_HEADERS]


def _normalize_rows(raw: Sequence[Sequence[Any]]) -> list[ReviewRecord]:
    if not raw or tuple(str(x) for x in raw[0]) != REVIEW_HEADERS:
        raise ReviewError("Encabezados incompatibles en RevisionesContrato.")
    reviews = []
    identifiers: set[str] = set()
    for items in raw[1:]:
        cells = [str(x) if x is not None else "" for x in items[:len(REVIEW_HEADERS)]]
        cells += [""] * (len(REVIEW_HEADERS) - len(cells))
        if not any(cells):
            continue
        entry = ReviewRecord(*cells)
        if not entry.revision_id or entry.revision_id in identifiers:
            raise ReviewError("Hay revisiones con ID vacío o repetido.")
        if entry.campo not in CAMPOS_CONTRATO or entry.decision not in DECISIONS:
            raise ReviewError("Hay registros de cotejo con campos o decisiones desconocidos.")
        identifiers.add(entry.revision_id)
        reviews.append(entry)
    return reviews


def read_reviews(client: Any, spreadsheet_id: str) -> list[ReviewRecord]:
    response = client.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range="'RevisionesContrato'!A1:M",
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    return _normalize_rows(response.get("values") or [])


def latest_reviews(
    records: Sequence[ReviewRecord], obra_id: str,
    documento_id: str, cache_key: str
) -> dict[str, ReviewRecord]:
    """La última fila por campo refleja la última corrección (trazabilidad intacta)."""
    latest = {}
    for row in records:
        if (row.obra_id, row.documento_id, row.cache_key) == (
            obra_id, documento_id, cache_key
        ):
            latest[row.campo] = row
    return latest


def validate_review(
    *, obra_id: str, documento_id: str, cache_key: str,
    campo: str, decision: str, valor_extraido: str, valor_cotejado: str,
    pagina: str, evidencia: str, justificacion: str,
    revisor_email: str, revision_id: str | None = None,
) -> ReviewRecord:
    if campo not in CAMPOS_CONTRATO or decision not in DECISIONS:
        raise ReviewError("El campo o la decisión no están admitidos.")
    if not all(isinstance(x, str) and x.strip() for x in (obra_id, documento_id, cache_key)):
        raise ReviewError("No se identificó la versión de contrato.")
    if not isinstance(revisor_email, str) or not _EMAIL.fullmatch(revisor_email.strip()):
        raise ReviewError("No se pudo verificar el correo del revisor autenticado.")
    extracted = valor_extraido.strip()
    corrected = valor_cotejado.strip()
    page = pagina.strip()
    quote = evidencia.strip()
    reason = justificacion.strip()
    if any(len(v) > limit for v, limit in (
        (extracted, 6000), (corrected, 6000), (quote, 1000), (reason, 2000),
    )):
        raise ReviewError("Un campo excede la longitud permitida.")

    if decision == "Confirmado":
        if not extracted or corrected != extracted:
            raise ReviewError("Para confirmar, el valor debe coincidir con el extraído.")
    elif decision == "Corregido":
        if not corrected or corrected == extracted:
            raise ReviewError("Indica el valor corregido, diferente del extraído.")
        if not reason:
            raise ReviewError("Explica por qué se corrigió el valor.")
    else:
        if corrected or page or quote:
            raise ReviewError("No localizado exige valor, página y evidencia vacíos.")
        if not reason:
            raise ReviewError("Justifica por qué el dato no fue localizado.")

    if decision != "No localizado":
        if not page.isdecimal() or not 1 <= int(page) <= 9999:
            raise ReviewError("Indica la página del PDF con un entero mayor que cero.")
        if not quote:
            raise ReviewError("Transcribe el fragmento visible que respalda el dato.")

    return ReviewRecord(
        revision_id=revision_id or uuid4().hex,
        fecha_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        obra_id=obra_id.strip(), documento_id=documento_id.strip(),
        cache_key=cache_key.strip(), campo=campo, decision=decision,
        valor_extraido=extracted, valor_cotejado=corrected,
        pagina=page, evidencia=quote, justificacion=reason,
        revisor_email=revisor_email.strip().casefold(),
    )


def _read_current_context(client: Any, spreadsheet_id: str) -> dict[str, list[list[str]]]:
    tabs = (
        ("Documentos", DOCUMENT_HEADERS),
        ("DatosContrato", CONTRACT_HEADERS),
    )
    result = client.spreadsheets().values().batchGet(
        spreadsheetId=spreadsheet_id,
        ranges=[
            f"'{name}'!A1:{chr(64 + len(headers))}"
            for name, headers in tabs
        ],
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    parts = result.get("valueRanges") or []
    if len(parts) != len(tabs):
        raise ReviewError("No se pudieron consultar los datos de origen.")
    out = {}
    for i, (name, headers) in enumerate(tabs):
        values = parts[i].get("values") or []
        if not values or tuple(str(x) for x in values[0]) != headers:
            raise ReviewError(f"Se modificaron encabezados de {name}.")
        out[name] = [
            [str(x) if x is not None else "" for x in row]
            for row in values[1:]
        ]
    return out


def save_review(
    client: Any, spreadsheet_id: str, event: ReviewRecord
) -> tuple[bool, ReviewRecord]:
    """Una sola fila por evento, con control del origen y del ID de solicitud.

    Debe ejecutarse detrás del mismo cerrojo local que usa la sincronización.
    Es idempotente por revision_id mientras Sheets permanezca disponible.
    """
    old = read_reviews(client, spreadsheet_id)
    matches = [row for row in old if row.revision_id == event.revision_id]
    if matches:
        previous = matches[0]
        # Identificador de envío reutilizado: confirmar misma intención.
        if any(
            getattr(previous, key) != getattr(event, key)
            for key in REVIEW_HEADERS if key != "fecha_utc"
        ):
            raise ReviewError("La revisión ya existe con otro contenido.")
        return False, previous

    current = _read_current_context(client, spreadsheet_id)
    def as_record(headers: tuple[str, ...], row: list[str]) -> dict[str, str]:
        values = row[:len(headers)] + [""] * max(0, len(headers) - len(row))
        return dict(zip(headers, values))

    docs = [as_record(DOCUMENT_HEADERS, row) for row in current["Documentos"]]
    contracts = [as_record(CONTRACT_HEADERS, row) for row in current["DatosContrato"]]
    matching_docs = [d for d in docs if d["documento_id"] == event.documento_id]
    matching_data = [
        d for d in contracts
        if d["documento_id"] == event.documento_id
        and d["obra_id"] == event.obra_id
        and d["cache_key"] == event.cache_key
    ]
    if len(matching_docs) != 1 or len(matching_data) != 1:
        raise ReviewError("No existe un contrato único asociado al PDF vigente.")
    doc, data = matching_docs[0], matching_data[0]
    if (
        doc["activo"] != "SI"
        or doc["obra_id"] != event.obra_id
        or doc["resultado_id"] != event.cache_key
        or doc["estado_procesamiento"] == "Modificado desde el último análisis"
    ):
        raise ReviewError("El PDF ya no corresponde a la versión que se quiere revisar.")
    if data[event.campo] != event.valor_extraido:
        raise ReviewError("El valor de origen cambió desde que abriste el formulario.")

    saved = client.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range="'RevisionesContrato'!A1:M",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [event.values()]},
    ).execute()
    updates = saved.get("updates") or {}
    if int(updates.get("updatedRows") or 0) != 1:
        raise ReviewError(
            "Sheets no confirmó el cotejo. Antes de repetir, actualiza el historial."
        )
    return True, event
