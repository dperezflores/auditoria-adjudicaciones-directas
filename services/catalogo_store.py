"""Persistencia y caché del catálogo contratado desde XLSX, sin usar Gemini.

DatosCatalogo conserva una fila por concepto original. Extracciones conserva
solo un resumen compacto; nunca se guarda el Excel completo en una celda.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from services.catalogo_xlsx import (
    CATALOGO_HEADERS, CATALOGO_PARSER_VERSION, CATALOGO_SCHEMA_VERSION,
    CatalogoFormatError, CatalogoResult, parse_catalogo_xlsx,
)
from services.document_classifier import XLSX_MIME, code_from_filename
from services.drive_service import DocumentRecord
from services.extraction_cache import CacheKey
from services.extraction_store import (
    COMPLETE, IN_PROGRESS, UNCERTAIN, ExtractionStateError,
    _batch_write, _find_unique, _sheet_rows, _write_regions,
)

TABLE = "DatosCatalogo"
MODEL = "lector-local-xlsx"


@dataclass(frozen=True)
class CatalogoOutcome:
    report: CatalogoResult
    cache: CacheKey
    cached: bool


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _key(raw: bytes) -> CacheKey:
    digest = hashlib.sha256(raw).hexdigest()
    descriptor = [digest, MODEL, CATALOGO_PARSER_VERSION, CATALOGO_SCHEMA_VERSION, "CATALOGO"]
    key = hashlib.sha256(
        json.dumps(descriptor, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return CacheKey(
        clave=key, contenido_sha256=digest, modelo=MODEL,
        version_prompt=CATALOGO_PARSER_VERSION,
        version_esquema=CATALOGO_SCHEMA_VERSION, tipo_documento="CATALOGO",
    )


def ensure_catalog_table(sheets: Any, sheet_id: str, *, min_rows: int = 1000) -> None:
    """Crear la pestaña dedicada al importarse el primer Excel (no al navegar)."""
    api = sheets.spreadsheets()
    meta = api.get(
        spreadsheetId=sheet_id,
        fields="sheets(properties(sheetId,title,gridProperties(columnCount,rowCount)))",
    ).execute()
    found = [
        (obj.get("properties") or {})
        for obj in meta.get("sheets") or []
        if (obj.get("properties") or {}).get("title") == TABLE
    ]
    if len(found) > 1:
        raise ExtractionStateError("Hay pestañas DatosCatalogo duplicadas.")
    if not found:
        response = api.batchUpdate(spreadsheetId=sheet_id, body={"requests": [
            {"addSheet": {"properties": {"title": TABLE, "gridProperties": {
                "rowCount": max(1000, min_rows), "columnCount": len(CATALOGO_HEADERS),
            }}}}
        ]}).execute()
        if not response.get("replies"):
            raise ExtractionStateError("No se confirmó la creación de DatosCatalogo.")
        api.values().update(
            spreadsheetId=sheet_id, range=f"'{TABLE}'!A1:M1",
            valueInputOption="RAW",
            body={"values": [list(CATALOGO_HEADERS)]},
        ).execute()
    else:
        props = found[0].get("gridProperties") or {}
        if int(props.get("columnCount", 0)) < len(CATALOGO_HEADERS):
            raise ExtractionStateError("DatosCatalogo no tiene las columnas necesarias.")
        if int(props.get("rowCount", 0)) < min_rows:
            response = api.batchUpdate(spreadsheetId=sheet_id, body={"requests": [{
                "updateSheetProperties": {
                    "properties": {"sheetId": found[0]["sheetId"],
                                   "gridProperties": {"rowCount": min_rows}},
                    "fields": "gridProperties.rowCount",
                }
            }]}).execute()
            if not response.get("replies"):
                raise ExtractionStateError("No se confirmó la ampliación de DatosCatalogo.")


def load_catalog_rows(sheets: Any, sheet_id: str) -> list[list[str]]:
    response = sheets.spreadsheets().values().get(
        spreadsheetId=sheet_id, range=f"'{TABLE}'!A1:M",
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    values = response.get("values") or []
    if not values or tuple(map(str, values[0][:len(CATALOGO_HEADERS)])) != CATALOGO_HEADERS:
        raise ExtractionStateError("Falta DatosCatalogo o sus encabezados son incompatibles.")
    rows = []
    for item in values[1:]:
        row = ["" if x is None else str(x) for x in item[:len(CATALOGO_HEADERS)]]
        row += [""] * (len(CATALOGO_HEADERS) - len(row))
        rows.append(row)
    return rows


def _summary(result: CatalogoResult) -> dict[str, object]:
    return {
        "tipo": "CATALOGO",
        "version": CATALOGO_SCHEMA_VERSION,
        "conceptos_originales": len(result.conceptos),
        "excluidos_fuera_catalogo": result.excluidos_fuera_catalogo,
        "excluidos_cantidad_inicial_cero": result.excluidos_sin_cantidad_inicial,
        "conceptos_con_excedentes_no_incluidos": result.originales_con_excedente,
        "importe_original_calculado_sin_iva": result.total_original,
        "hojas": list(result.hojas),
        "nota": ("La cantidad de contrato corresponde a Inicial, NO a Total Aut. "
                 "Los conceptos fuera de catálogo y excedentes no integran el importe original. "
                 "Este cálculo no sustituye el presupuesto contractual firmado."),
    }


def _result_from_rows(rows: list[list[str]], summary: dict[str, object]) -> CatalogoResult:
    from services.catalogo_xlsx import ConceptoCatalogo
    return CatalogoResult(
        conceptos=tuple(ConceptoCatalogo(*row[3:12]) for row in rows),
        excluidos_fuera_catalogo=int(summary["excluidos_fuera_catalogo"]),
        excluidos_sin_cantidad_inicial=int(summary["excluidos_cantidad_inicial_cero"]),
        originales_con_excedente=int(summary["conceptos_con_excedentes_no_incluidos"]),
        total_original=str(summary["importe_original_calculado_sin_iva"]),
        hojas=tuple(str(x) for x in summary["hojas"]),
    )


def import_or_reuse_catalogo(
    sheets: Any, sheet_id: str, raw: bytes,
    doc: DocumentRecord, obra_id: str,
) -> CatalogoOutcome:
    """Sólo procesa a petición del auditor, sin clave API ni llamadas IA."""
    if code_from_filename(doc.name, doc.mime_type) != "CATALOGO" or doc.mime_type != XLSX_MIME:
        raise ExtractionStateError("El archivo debe llamarse CATALOGO.xlsx.")
    if not raw.startswith(b"PK"):
        raise ExtractionStateError("El contenido descargado no es un XLSX.")
    cache = _key(raw)
    tables = _sheet_rows(sheets, sheet_id)
    registered = _find_unique(tables["Documentos"], 0, doc.id)
    if not registered:
        raise ExtractionStateError("Registra primero CATALOGO.xlsx mediante Actualizar Google Drive.")
    doc_number, row = registered
    if (
        row[1] != obra_id or row[3] != "CATALOGO" or row[4] != XLSX_MIME
        or row[11] != "SI" or not doc.md5_checksum
        or row[5] != doc.md5_checksum
    ):
        raise ExtractionStateError("La obra, tipo o huella del Excel no coincide con Drive.")
    prior = _find_unique(tables["Extracciones"], 0, cache.clave)
    if prior and prior[1][2:4] != [doc.id, obra_id]:
        raise ExtractionStateError("La caché está vinculada a otro documento.")

    if prior:
        _, saved = prior
        if saved[1] != COMPLETE or not saved[10]:
            raise ExtractionStateError(
                "Existe una importación Excel incompleta. Revisa o elimina ese intento; "
                "no se reintentará automáticamente."
            )
        try:
            summary = json.loads(saved[10])
            # La tabla debe existir y contener exactamente todas las filas.
            stored = [r for r in load_catalog_rows(sheets, sheet_id) if r[0] == cache.clave]
            if len(stored) != int(summary["conceptos_originales"]):
                raise ExtractionStateError(
                    "La caché del catálogo no coincide con las filas guardadas."
                )
            _write_regions(sheets, sheet_id, [
                {"range": f"'Documentos'!I{doc_number}", "values": [["Analizado"]]},
                {"range": f"'Documentos'!M{doc_number}:O{doc_number}",
                 "values": [[f"{MODEL}:{CATALOGO_PARSER_VERSION}", cache.clave, ""]]},
            ])
            return CatalogoOutcome(_result_from_rows(stored, summary), cache, True)
        except (KeyError, ValueError, TypeError) as exc:
            raise ExtractionStateError("El resumen anterior del catálogo es incompatible.") from exc

    # Comprobar formato y coherencia ANTES de reservar una importación.
    try:
        parsed = parse_catalogo_xlsx(raw)
    except CatalogoFormatError as exc:
        raise ExtractionStateError(str(exc)) from None
    ensure_catalog_table(sheets, sheet_id, min_rows=len(parsed.conceptos) + 2)
    existing = load_catalog_rows(sheets, sheet_id)
    ensure_catalog_table(sheets, sheet_id, min_rows=len(existing) + len(parsed.conceptos) + 2)
    if any(r[0] == cache.clave for r in existing):
        raise ExtractionStateError(
            "Existen filas de catálogo sin una importación confirmada. Revisar antes de duplicar."
        )

    now = _now()
    idx = len(tables["Extracciones"]) + 2
    reservation = [
        cache.clave, IN_PROGRESS, doc.id, obra_id, cache.contenido_sha256,
        MODEL, CATALOGO_PARSER_VERSION, CATALOGO_SCHEMA_VERSION,
        now, now, "", "", "", "",
    ]
    _batch_write(sheets, sheet_id, [("Extracciones", idx, reservation)])
    try:
        # Trocear las escrituras; ante cualquier incertidumbre bloquear reintentos.
        records = [[
            cache.clave, obra_id, doc.id, c.hoja, str(c.fila), c.capitulo,
            c.clave, c.descripcion, c.unidad, c.cantidad_original,
            c.precio_unitario, c.importe_original, now,
        ] for c in parsed.conceptos]
        for start in range(0, len(records), 250):
            chunk = records[start:start + 250]
            initial_row = len(existing) + 2 + start
            last_row = initial_row + len(chunk) - 1
            _write_regions(sheets, sheet_id, [{
                "range": f"'{TABLE}'!A{initial_row}:M{last_row}",
                "values": chunk,
            }])
        summary = json.dumps(_summary(parsed), ensure_ascii=False, separators=(",", ":"))
        complete = [
            cache.clave, COMPLETE, doc.id, obra_id, cache.contenido_sha256,
            MODEL, CATALOGO_PARSER_VERSION, CATALOGO_SCHEMA_VERSION,
            now, _now(), summary, "", "", "",
        ]
        _write_regions(sheets, sheet_id, [
            {"range": f"'Extracciones'!A{idx}:N{idx}", "values": [complete]},
            {"range": f"'Documentos'!I{doc_number}", "values": [["Analizado"]]},
            {"range": f"'Documentos'!M{doc_number}:O{doc_number}",
             "values": [[f"{MODEL}:{CATALOGO_PARSER_VERSION}", cache.clave, ""]]},
        ])
        return CatalogoOutcome(parsed, cache, False)
    except Exception:
        # Una llamada a Sheets puede haber funcionado pese a un error de red.
        # No repetir hasta comprobar la tabla; impedir duplicación.
        reservation[1] = UNCERTAIN
        reservation[9] = _now()
        reservation[13] = "GUARDADO_NO_CONFIRMADO"
        try:
            _batch_write(sheets, sheet_id, [("Extracciones", idx, reservation)])
        except Exception:
            pass
        raise ExtractionStateError(
            "La escritura del catálogo no quedó confirmada. Revisa DatosCatalogo "
            "y Extracciones antes de repetir; no se usó Gemini."
        ) from None
