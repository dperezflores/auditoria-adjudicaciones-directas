"""Lectura local de CATALOGO.xlsx, sin IA ni fórmulas inventadas.

El prefiniquito contiene Inicial, Excedente y Total Aut.: para el catálogo
contratado se usa exclusivamente Inicial * Precio U. y se excluyen capítulos
FUERA DE CATALOGO. No se admiten formatos ambiguos de forma silenciosa.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from io import BytesIO
import posixpath
import re
import unicodedata
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from services.document_classifier import XLSX_MIME, code_from_filename

CATALOGO_SCHEMA_VERSION = "catalogo-xlsx-v1"
CATALOGO_PARSER_VERSION = "catalogo-parser-v1"
CATALOGO_HEADERS = (
    "cache_key", "obra_id", "documento_id", "hoja", "fila", "capitulo",
    "clave", "descripcion", "unidad", "cantidad_original",
    "precio_unitario", "importe_original", "extraido_utc",
)

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
       "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
       "p": "http://schemas.openxmlformats.org/package/2006/relationships"}
_MAX_UNCOMPRESSED = 85_000_000
_MAX_ROWS = 25000
_MAX_CONCEPTS = 15000


class CatalogoFormatError(ValueError):
    """Formato o datos insuficientes para identificar el catálogo original."""


@dataclass(frozen=True)
class ConceptoCatalogo:
    hoja: str
    fila: int
    capitulo: str
    clave: str
    descripcion: str
    unidad: str
    cantidad_original: str
    precio_unitario: str
    importe_original: str


@dataclass(frozen=True)
class CatalogoResult:
    conceptos: tuple[ConceptoCatalogo, ...]
    excluidos_fuera_catalogo: int
    excluidos_sin_cantidad_inicial: int
    originales_con_excedente: int
    total_original: str
    hojas: tuple[str, ...]


def _norm(value: object) -> str:
    value = unicodedata.normalize("NFKD", str(value or "").casefold())
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value)).strip()


def _number(value: str, *, positive: bool = False) -> Decimal:
    raw = str(value or "").strip().replace("$", "").replace(" ", "")
    if "," in raw and "." in raw:
        raw = raw.replace(",", "")
    elif "," in raw:
        raw = raw.replace(",", "") if re.search(r",\d{3}(?:,|$)", raw) else raw.replace(",", ".")
    try:
        amount = Decimal(raw)
    except (InvalidOperation, ValueError):
        raise CatalogoFormatError(f"Cantidad o precio no numérico: {str(value)[:60]}") from None
    if not amount.is_finite() or (positive and amount <= 0):
        raise CatalogoFormatError("Cantidad o precio inválido en una fila contractual.")
    return amount


def _str_value(cell: ET.Element, shared: list[str]) -> str:
    kind = cell.get("t")
    if kind in ("inlineStr", "str"):
        parts = [e.text or "" for e in cell.findall(".//m:is//m:t", _NS)]
        if parts:
            return "".join(parts)
    raw = cell.find("m:v", _NS)
    if raw is None:
        return ""
    value = raw.text or ""
    if kind == "s":
        try:
            return shared[int(value)]
        except (IndexError, ValueError):
            raise CatalogoFormatError("Índice de texto compartido inválido.") from None
    return value


def _load_sheets(raw: bytes):
    if not isinstance(raw, bytes) or not raw.startswith(b"PK"):
        raise CatalogoFormatError("Se requiere un archivo XLSX válido.")
    try:
        with ZipFile(BytesIO(raw)) as archive:
            members = archive.namelist()
            total_bytes = sum(info.file_size for info in archive.infolist())
            if total_bytes > _MAX_UNCOMPRESSED or len(members) > 300:
                raise CatalogoFormatError("El archivo Excel excede los límites de lectura segura.")
            if "xl/workbook.xml" not in members or "xl/_rels/workbook.xml.rels" not in members:
                raise CatalogoFormatError("El libro no tiene las estructuras XLSX esperadas.")
            shared: list[str] = []
            if "xl/sharedStrings.xml" in members:
                root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                shared = ["".join(e.text or "" for e in si.findall(".//m:t", _NS))
                          for si in root.findall("m:si", _NS)]
            book = ET.fromstring(archive.read("xl/workbook.xml"))
            links = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            rels = {r.get("Id"): r.get("Target") for r in links}
            for sheet in book.findall("m:sheets/m:sheet", _NS):
                name = sheet.get("name") or ""
                target = rels.get(sheet.get("{" + _NS["r"] + "}id"))
                if not target:
                    continue
                path = (target.lstrip("/") if target.startswith("/")
                        else posixpath.normpath(posixpath.join("xl", target)))
                if not path.startswith("xl/worksheets/") or path not in members:
                    continue
                root = ET.fromstring(archive.read(path))
                rows = []
                for row in root.findall("m:sheetData/m:row", _NS):
                    if len(rows) >= _MAX_ROWS:
                        raise CatalogoFormatError("La hoja excede el máximo de 25 000 filas.")
                    row_number = int(row.get("r") or len(rows) + 1)
                    fields: dict[int, str] = {}
                    for cell in row.findall("m:c", _NS):
                        match = re.match(r"([A-Z]+)", cell.get("r") or "")
                        if not match:
                            continue
                        index = 0
                        for letter in match.group(1):
                            index = 26 * index + (ord(letter) - 64)
                        if index > 90:
                            continue
                        fields[index - 1] = _str_value(cell, shared)
                    rows.append((row_number, fields))
                yield name, rows
    except (BadZipFile, ET.ParseError, KeyError) as exc:
        raise CatalogoFormatError("El archivo XLSX está dañado o no se puede interpretar.") from exc


def _headers(row: dict[int, str]) -> dict[str, int] | None:
    values = {index: _norm(value) for index, value in row.items()}
    aliases = {
        "clave": ("clave", "codigo", "codigo concepto"),
        "descripcion": ("descripcion", "concepto", "descripcion concepto"),
        "unidad": ("unidad", "unidad medida", "u m"),
        "cantidad_original": ("inicial", "cantidad contratada", "cantidad original",
                              "cantidad de contrato", "cantidad"),
        "precio_unitario": ("precio u", "precio unitario", "p u"),
    }
    mapping: dict[str, int] = {}
    for key, choices in aliases.items():
        choices_found = [idx for idx, val in values.items() if val in choices]
        if not choices_found:
            return None
        mapping[key] = min(choices_found)
    # Si existe Excedente o Total Aut., una columna genérica Cantidad es
    # ambigua: debe existir Inicial o Cantidad contratada explícita.
    count_header = values[mapping["cantidad_original"]]
    if count_header == "cantidad" and any(
        "excedente" in text or "total aut" in text for text in values.values()
    ):
        raise CatalogoFormatError(
            "La cantidad original no está identificada: se requiere columna Inicial."
        )
    return mapping


def _outside(label: str) -> bool:
    normalized = _norm(label)
    return ("fuera de catalogo" in normalized or "fuera del catalogo" in normalized
            or "conceptos extraordinarios" in normalized)


def parse_catalogo_xlsx(raw: bytes) -> CatalogoResult:
    """Devuelve solo conceptos del catálogo contratado, nunca excedentes ni extras."""
    concepts: list[ConceptoCatalogo] = []
    outside_count = zero_count = with_excess = 0
    matched: list[str] = []
    used_keys: set[str] = set()
    for name, rows in _load_sheets(raw):
        headers = next(((idx, mapping) for idx, (number, cells) in enumerate(rows[:100])
                        if (mapping := _headers(cells)) is not None), None)
        if headers is None:
            continue
        header_idx, columns = headers
        sheet_concepts = 0
        budget_is_original = True
        section_is_outside = False
        chapter = ""
        for number, cells in rows[header_idx + 1:]:
            first = str(cells.get(columns["clave"], "")).strip()
            section = _norm(first)
            if section.startswith("presupuesto"):
                # El prefiniquito separa contratos originales y adicionales.
                budget_is_original = ("contrato original" in section or
                    re.search(r"^presupuesto 0(?: |$)", section) is not None)
                section_is_outside = False
                chapter = ""
                continue
            if section.startswith(("capitulo", "sub capitulo")):
                if section.startswith("capitulo"):
                    chapter = first[:450]
                    section_is_outside = _outside(first)
                continue
            if not first or section in ("clave", "total", "subtotal"):
                continue
            description = str(cells.get(columns["descripcion"], "")).strip()
            unit = str(cells.get(columns["unidad"], "")).strip()
            if not description or not unit or not re.match(r"^[\w.-][\w./ -]{0,79}$", first):
                continue
            if not budget_is_original or section_is_outside or _outside(first):
                outside_count += 1
                continue
            quantity_text = str(cells.get(columns["cantidad_original"], "")).strip()
            if not quantity_text:
                raise CatalogoFormatError(f"Falta cantidad Inicial en {name}, fila {number}.")
            quantity = _number(quantity_text)
            if quantity < 0:
                raise CatalogoFormatError(f"Cantidad Inicial negativa en {name}, fila {number}.")
            if quantity == 0:
                zero_count += 1
                continue
            unit_price_text = str(cells.get(columns["precio_unitario"], "")).strip()
            if not unit_price_text:
                raise CatalogoFormatError(f"Falta Precio U. en {name}, fila {number}.")
            unit_price = _number(unit_price_text, positive=True)
            key = first.casefold()
            if key in used_keys:
                raise CatalogoFormatError(f"Clave contractual duplicada: {first}.")
            used_keys.add(key)
            # Leer el excedente solo para el resumen; NO incorporarlo al importe.
            extra_idx = next((i for i, value in rows[header_idx][1].items()
                              if _norm(value) == "excedente"), None)
            if extra_idx is not None and str(cells.get(extra_idx, "")).strip():
                try:
                    if _number(cells[extra_idx]) > 0:
                        with_excess += 1
                except CatalogoFormatError:
                    pass
            amount = (quantity * unit_price).quantize(Decimal("0.01"))
            concepts.append(ConceptoCatalogo(
                hoja=name, fila=number, capitulo=chapter, clave=first,
                descripcion=description, unidad=unit,
                cantidad_original=str(quantity), precio_unitario=str(unit_price),
                importe_original=str(amount),
            ))
            sheet_concepts += 1
            if len(concepts) > _MAX_CONCEPTS:
                raise CatalogoFormatError("El catálogo supera 15 000 conceptos; no se importó parcialmente.")
        if sheet_concepts:
            matched.append(name)
    if not concepts:
        raise CatalogoFormatError(
            "No se identificaron conceptos originales con Clave, Descripción, "
            "Unidad, Inicial y Precio U.; no se guardaron datos."
        )
    total = sum((Decimal(c.importe_original) for c in concepts), Decimal("0"))
    return CatalogoResult(
        tuple(concepts), outside_count, zero_count, with_excess,
        str(total.quantize(Decimal("0.01"))), tuple(matched),
    )
