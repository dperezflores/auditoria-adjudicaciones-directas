"""Consulta de solo lectura para el dashboard de AuditorIA.

Se separan registros operativos y evidencia validada. Los datos de Gemini
sin cotejo humano NUNCA son presentados como hechos auditados.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from services.sync_engine import HEADERS as INVENTORY_HEADERS
from services.extraction_store import CONTRACT_HEADERS, EXTRACTION_HEADERS
from services.review_service import REVIEW_HEADERS, DECISIONS, ReviewRecord, latest_reviews
from services.gemini_compact_schema import CAMPOS_CONTRATO


class DashboardDataError(RuntimeError):
    """No fue posible preparar un resumen coherente y verificable."""


@dataclass(frozen=True)
class ContractDashboardRow:
    obra_id: str
    documento_id: str
    nombre_documento: str
    estado: str
    datos: Mapping[str, str]
    detalle: str
    cache_key: str
    revisiones: Mapping[str, ReviewRecord]

    @property
    def campos_cotejados(self) -> int:
        return len(self.revisiones)


@dataclass(frozen=True)
class WorkDashboardRow:
    obra_id: str
    nombre: str
    pdf_activos: int
    contratos_recuperados: int
    pendientes_cotejo: int


@dataclass(frozen=True)
class DashboardSnapshot:
    obras: tuple[WorkDashboardRow, ...]
    contratos: tuple[ContractDashboardRow, ...]
    pdf_activos: int
    documentos_pendientes: int
    contratos_pendientes_cotejo: int

    @property
    def contratos_con_datos(self) -> int:
        return len(self.contratos)


_HEADERS = {
    "Obras": INVENTORY_HEADERS["Obras"],
    "Documentos": INVENTORY_HEADERS["Documentos"],
    "Extracciones": EXTRACTION_HEADERS,
    "DatosContrato": CONTRACT_HEADERS,
    "RevisionesContrato": REVIEW_HEADERS,
}
_DATA_FIELDS = CONTRACT_HEADERS[3:11]
_VALID_EXTRACTION_STATES = {"COMPLETADO", "REQUIERE_REVISION"}


def _parse_table(
    name: str, values: Sequence[Sequence[Any]]
) -> list[dict[str, str]]:
    expected = _HEADERS[name]
    if not values or tuple(str(x) for x in values[0][:len(expected)]) != tuple(expected):
        raise DashboardDataError(f"Encabezados incompatibles en {name}.")
    seen: set[str] = set()
    parsed = []
    for raw in values[1:]:
        row = [str(value) if value is not None else "" for value in raw[:len(expected)]]
        row.extend([""] * (len(expected) - len(row)))
        if not any(row):
            continue
        data = dict(zip(expected, row))
        key = data[expected[0]]
        if not key:
            raise DashboardDataError(f"Encontré una fila sin identificador en {name}.")
        # DatosContrato puede contener el mismo caché si sirve a más de
        # un documento; se valida por clave compuesta más adelante.
        if name != "DatosContrato":
            if key in seen:
                raise DashboardDataError(f"ID duplicado en {name}.")
            seen.add(key)
        parsed.append(data)
    return parsed


def prepare_dashboard(
    tables: Mapping[str, Sequence[Sequence[Any]]]
) -> DashboardSnapshot:
    """Producir indicadores comprobables sin realizar análisis de IA."""
    try:
        parsed = {name: _parse_table(name, tables[name]) for name in _HEADERS}
    except KeyError as exc:
        raise DashboardDataError("Falta una pestaña de almacenamiento.") from exc

    works = {
        record["obra_id"]: record
        for record in parsed["Obras"] if record["activo"] == "SI"
    }
    documents = {
        record["documento_id"]: record
        for record in parsed["Documentos"]
        if record["activo"] == "SI" and record["obra_id"] in works
    }
    extraction_by_key = {record["cache_key"]: record for record in parsed["Extracciones"]}
    reviews = []
    for item in parsed["RevisionesContrato"]:
        if item["campo"] not in CAMPOS_CONTRATO or item["decision"] not in DECISIONS:
            raise DashboardDataError("El historial de cotejos contiene valores no admitidos.")
        reviews.append(ReviewRecord(**item))

    contract_rows = []
    seen_contracts: set[tuple[str, str]] = set()
    for record in parsed["DatosContrato"]:
        doc_id = record["documento_id"]
        key = record["cache_key"]
        doc = documents.get(doc_id)
        if doc is None:
            continue
        if doc["obra_id"] != record["obra_id"]:
            raise DashboardDataError("Contrato asociado a una carpeta distinta.")
        if doc["resultado_id"] != key:
            # El registro puede ser de una versión histórica del documento:
            # no mostrarla como resultado actual.
            continue
        pair = (key, doc_id)
        if pair in seen_contracts:
            raise DashboardDataError("Encontré el mismo contrato duplicado.")
        seen_contracts.add(pair)

        analysis = extraction_by_key.get(key)
        if analysis is None or analysis["estado"] not in _VALID_EXTRACTION_STATES:
            continue
        if analysis["documento_id"] != doc_id or analysis["obra_id"] != doc["obra_id"]:
            raise DashboardDataError("La extracción no corresponde al PDF registrado.")
        if doc["estado_procesamiento"] == "Modificado desde el último análisis":
            # Datos del PDF anterior: se requieren de nuevo, no aparecen
            # como información actual.
            continue
        datos = {name: record[name] for name in _DATA_FIELDS}
        if not any(value.strip() for value in datos.values()):
            continue

        if analysis["estado"] == "REQUIERE_REVISION":
            state = "Recuperado parcialmente · pendiente de cotejo"
            detail = (
                "Solo se conservaron los valores; las páginas y evidencias "
                "del análisis no están disponibles."
            )
        else:
            state = "Extracción guardada · pendiente de cotejo humano"
            detail = (
                "La extracción está guardada, pero aún necesita "
                "verificación documental por un auditor."
            )

        reviewed = latest_reviews(reviews, doc["obra_id"], doc_id, key)
        if len(reviewed) == len(CAMPOS_CONTRATO):
            state = "Cotejo manual completo · requiere revisión final"
            detail = (
                "Los ocho campos tienen un cotejo humano registrado. "
                "No implica aprobación de auditoría ni cumplimiento legal."
            )

        contract_rows.append(ContractDashboardRow(
            obra_id=doc["obra_id"],
            documento_id=doc_id,
            nombre_documento=doc["nombre_archivo"],
            estado=state,
            datos=datos,
            detalle=detail,
            cache_key=key,
            revisiones=reviewed,
        ))

    work_rows = []
    for obra_id, obra in sorted(works.items(), key=lambda x: x[1]["nombre_carpeta"].casefold()):
        doc_items = [x for x in documents.values() if x["obra_id"] == obra_id]
        contract_items = [x for x in contract_rows if x.obra_id == obra_id]
        work_rows.append(WorkDashboardRow(
            obra_id=obra_id,
            nombre=obra["nombre_carpeta"],
            pdf_activos=len(doc_items),
            contratos_recuperados=len(contract_items),
            pendientes_cotejo=sum(
                item.campos_cotejados < len(CAMPOS_CONTRATO)
                for item in contract_items
            ),
        ))
    return DashboardSnapshot(
        obras=tuple(work_rows),
        contratos=tuple(contract_rows),
        pdf_activos=len(documents),
        documentos_pendientes=sum(
            item["estado_procesamiento"] not in ("Analizado",)
            for item in documents.values()
        ),
        contratos_pendientes_cotejo=sum(
            item.campos_cotejados < len(CAMPOS_CONTRATO)
            for item in contract_rows
        ),
    )


def read_dashboard(client: Any, spreadsheet_id: str) -> DashboardSnapshot:
    """Google Sheets read-only batchGet, sin llamar a Gemini o Drive."""
    ranges = [
        f"'{name}'!A1:{chr(64 + len(_HEADERS[name]))}"
        for name in _HEADERS
    ]
    response = client.spreadsheets().values().batchGet(
        spreadsheetId=spreadsheet_id,
        ranges=ranges,
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    parts = response.get("valueRanges") or []
    if len(parts) != len(ranges):
        raise DashboardDataError("No se obtuvieron todas las pestañas requeridas.")
    return prepare_dashboard({
        name: parts[i].get("values", [])
        for i, name in enumerate(_HEADERS)
    })
