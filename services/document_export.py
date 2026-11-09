"""Exportación relacional de resultados PDF a un Excel generado al descargar.

Nunca lee CATALOGO.xlsx/DatosCatalogo ni invoca Gemini. El ID_OBRA numérico
sigue el orden del registro persistente Obras; ID_OBRA_DRIVE es la llave
canónica inmutable para sistemas externos. Solo usa extracciones confirmadas
vinculadas a la versión vigente del documento.
"""
from __future__ import annotations

from io import BytesIO
import json
import re
from typing import Any, Mapping, Sequence
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from services.contract_portfolio import ContractRecord
from services.contract_v2 import CONTRACT_V2_FIELDS
from services.puc_schema import PUC_FIELDS, PucExtractionV1
from services.dictamen_schema import DICTAMEN_FIELDS, DictamenAdV1
from services.notificacion_schema import NOTIFICACION_FIELDS, NotificacionAdV1
from services.orden_schema import ORDEN_FIELDS, OrdenAdV1
from services.document_analysis import GeneralAnalysis
from services.document_classifier import PDF_MIME
from services.sync_engine import HEADERS as INVENTORY_HEADERS


COLUMNS = {
    "OBRAS": (
        "ID_OBRA", "ID_OBRA_DRIVE", "CARPETA", "ESTADO_EXPEDIENTE",
    ),
    "DOCUMENTOS": (
        "ID_OBRA", "ID_OBRA_DRIVE", "ID_DOCUMENTO", "ARCHIVO",
        "TIPO_DOCUMENTAL", "ESTADO_PROCESAMIENTO", "ESTADO_EXPORTACION",
        "ESQUEMA_EXTRACCION", "EXTRAIDO_UTC",
    ),
}
_COMMON = ("ID_OBRA", "ID_OBRA_DRIVE", "ID_DOCUMENTO", "ARCHIVO", "ESQUEMA_EXTRACCION", "EXTRAIDO_UTC")
for _name, _fields in (
    ("CONTRATOS", CONTRACT_V2_FIELDS),
    ("PUC", PUC_FIELDS),
    ("DICTAMEN_AD", DICTAMEN_FIELDS),
    ("NOTIFICACION_AD", NOTIFICACION_FIELDS),
    ("ORDEN_AD", ORDEN_FIELDS),
):
    COLUMNS[_name] = (*_COMMON, *_fields)
COLUMNS["ESPECIALIDADES"] = (
    "ID_OBRA", "ID_OBRA_DRIVE", "ID_DOCUMENTO", "N", "CATEGORIA",
    "ACTIVIDAD", "TIPO_MARCADO", "APORTADA_POR", "PAGINA", "EVIDENCIA",
)
COLUMNS["EVIDENCIAS"] = (
    "ID_OBRA", "ID_OBRA_DRIVE", "ID_DOCUMENTO", "ESQUEMA",
    "CAMPO", "VALOR_LITERAL", "PAGINA", "EVIDENCIA",
)
COLUMNS["DETALLES"] = (
    "ID_OBRA", "ID_OBRA_DRIVE", "ID_DOCUMENTO", "ESQUEMA",
    "SECCION", "N", "DATOS_JSON",
)
COLUMNS["OTROS_PDF"] = (
    "ID_OBRA", "ID_OBRA_DRIVE", "ID_DOCUMENTO", "ARCHIVO",
    "ESQUEMA_EXTRACCION", "TIPO_IDENTIFICADO", "RESUMEN",
)

SCHEMAS = {
    "puc-v1": ("PUC", PucExtractionV1, PUC_FIELDS),
    "dictamen-ad-v1": ("DICTAMEN_AD", DictamenAdV1, DICTAMEN_FIELDS),
    "notificacion-ad-v1": ("NOTIFICACION_AD", NotificacionAdV1, NOTIFICACION_FIELDS),
    "orden-ad-v1": ("ORDEN_AD", OrdenAdV1, ORDEN_FIELDS),
}
_LEGACY_MAP = {
    "numero_contrato": "numero_contrato",
    "obra_servicio": "nombre_obra",
    "contratista": "contratista",
    "monto_contrato": "monto_con_iva",
    "fecha_inicio_contractual": "fecha_inicio",
    "fecha_termino_contractual": "fecha_termino",
    "fecha_firma_contrato": "fecha_firma",
    "anticipo": "porcentaje_anticipo",
}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def read_registered_works(sheets: Any, spreadsheet_id: str) -> list[dict[str, str]]:
    """Lee TODAS las obras, incluso históricas, para no renumerar IDs al crecer."""
    response = sheets.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range="'Obras'!A1:I",
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    raw = response.get("values") or []
    headers = INVENTORY_HEADERS["Obras"]
    if not raw or tuple(map(str, raw[0][:len(headers)])) != headers:
        raise ValueError("No se pudo validar la tabla Obras para exportación.")
    result = []
    seen = set()
    for row in raw[1:]:
        if not any(str(v) for v in row):
            continue
        vals = [str(v) if v is not None else "" for v in row[:len(headers)]]
        vals += [""] * (len(headers) - len(vals))
        obj = dict(zip(headers, vals))
        if not obj["obra_id"] or obj["obra_id"] in seen:
            raise ValueError("Existen identificadores de obra vacíos o duplicados.")
        seen.add(obj["obra_id"])
        result.append(obj)
    return result


def export_document_tables(
    works: Sequence[Mapping[str, str]],
    documents: Sequence[Mapping[str, str]],
    extractions: Sequence[Mapping[str, str]],
    contracts: Sequence[ContractRecord],
) -> dict[str, list[list[Any]]]:
    """Construye tablas relacionales; cada ID_OBRA conserva su folio entre descargas."""
    result = {name: [] for name in COLUMNS}
    # La asignación ordinal procede del orden persistido en Obras, no de los
    # filtros de la interfaz ni de los archivos que estén analizados hoy.
    ids = {w["obra_id"]: index for index, w in enumerate(works, start=1)}
    active = {w["obra_id"]: w for w in works if w["activo"] == "SI"}
    pdfs = [
        d for d in documents
        if d["activo"] == "SI" and d["obra_id"] in active
        and d["mime_type"] == PDF_MIME
    ]
    included = {d["obra_id"] for d in pdfs}
    for w in works:
        if w["obra_id"] in included and w["activo"] == "SI":
            result["OBRAS"].append([
                ids[w["obra_id"]], w["obra_id"], w["nombre_carpeta"],
                w["estado_expediente"],
            ])
    analyses = {a["cache_key"]: a for a in extractions}
    contract_map = {r.documento_id: r for r in contracts}
    for doc in pdfs:
        work_id, document_id = doc["obra_id"], doc["documento_id"]
        id_obra = ids[work_id]
        id_fields = [id_obra, work_id, document_id]
        filename = doc["nombre_archivo"]
        candidate = analyses.get(doc["resultado_id"])
        valid = bool(
            candidate
            and candidate["documento_id"] == document_id
            and candidate["obra_id"] == work_id
            and candidate["estado"] == "COMPLETADO"
            and candidate["resultado_json"]
            and doc["estado_procesamiento"] != "Modificado desde el último análisis"
        )
        schema = candidate["version_esquema"] if valid else ""
        extracted = candidate["actualizado_utc"] if valid else ""
        status = "Sin análisis vigente"
        payload: Any = None
        if valid:
            try:
                if schema in SCHEMAS:
                    _, cls, _ = SCHEMAS[schema]
                    payload = cls.model_validate_json(candidate["resultado_json"])
                elif schema == "contrato-v2":
                    # La validación por esquema completo y su identidad se
                    # materializan en el portafolio contractual.
                    payload = contract_map.get(document_id)
                    if payload is None or payload.source_schema != "contrato-v2":
                        raise ValueError("Contrato no validado en el portafolio.")
                elif schema == "documento-schema-v1":
                    payload = GeneralAnalysis.model_validate_json(candidate["resultado_json"])
                elif schema == "contrato-v1":
                    payload = contract_map.get(document_id)
                    if payload is None:
                        raise ValueError("Contrato histórico no validado.")
                else:
                    payload = json.loads(candidate["resultado_json"])
                status = "Analizado"
            except (ValueError, TypeError, KeyError):
                status = "Extracción ilegible o inconsistente"
                payload = None
        result["DOCUMENTOS"].append([
            *id_fields, filename, doc["tipo_documental"],
            doc["estado_procesamiento"], status, schema, extracted,
        ])
        if payload is None:
            continue
        common = [*id_fields, filename, schema, extracted]

        if schema in SCHEMAS:
            tab, _, fields = SCHEMAS[schema]
            result[tab].append([
                *common, *(getattr(payload, f).valor or "" for f in fields),
            ])
            for field in fields:
                fact = getattr(payload, field)
                if fact.valor is not None:
                    result["EVIDENCIAS"].append([
                        *id_fields, schema, field, fact.valor,
                        fact.pagina if fact.pagina is not None else "",
                        fact.evidencia or "",
                    ])
            # Toda información anidada se conserva, aun si no es una columna
            # escalar: soportes, firmas, instrucciones, personas, etc.
            flat = set(fields)
            for section, nested in payload.model_dump(mode="json").items():
                if section in flat:
                    continue
                if section == "especialidades" and schema == "puc-v1":
                    for number, specialty in enumerate(nested, start=1):
                        result["ESPECIALIDADES"].append([
                            *id_fields, number, specialty.get("categoria") or "",
                            specialty.get("actividad") or "",
                            specialty.get("tipo_marcado") or "",
                            specialty.get("aportada_por") or "",
                            specialty.get("pagina") or "",
                            specialty.get("evidencia") or "",
                        ])
                    continue
                items = nested if isinstance(nested, list) else [nested]
                for number, item in enumerate(items, start=1):
                    result["DETALLES"].append([
                        *id_fields, schema, section, number, _json(item),
                    ])
            continue

        if schema in ("contrato-v2", "contrato-v1"):
            record = payload
            if schema == "contrato-v2":
                values = record.full_values or {}
            else:
                values = {f: record.values.get(_LEGACY_MAP.get(f, ""), "") for f in CONTRACT_V2_FIELDS}
            result["CONTRATOS"].append([
                *common, *(values.get(f, "") for f in CONTRACT_V2_FIELDS),
            ])
            for field, ref in record.evidence.items():
                if isinstance(ref, Mapping) and ref.get("valor") is not None:
                    result["EVIDENCIAS"].append([
                        *id_fields, schema, field, ref.get("valor") or "",
                        ref.get("pagina") or "", ref.get("evidencia") or "",
                    ])
            for section, values_ in (
                ("personas_participantes", record.participants),
                ("observaciones", record.observations),
            ):
                for number, item in enumerate(values_, start=1):
                    result["DETALLES"].append([
                        *id_fields, schema, section, number, _json(item),
                    ])
            continue

        if schema == "documento-schema-v1":
            result["OTROS_PDF"].append([
                *id_fields, filename, schema, payload.tipo_documental, payload.resumen,
            ])
            for field in payload.campos:
                fact = field.model_dump(mode="json")
                result["EVIDENCIAS"].append([
                    *id_fields, schema, fact.get("campo") or "",
                    fact.get("valor") or "", fact.get("pagina") or "",
                    fact.get("evidencia") or "",
                ])
            for number, note in enumerate(payload.alertas, start=1):
                result["DETALLES"].append([
                    *id_fields, schema, "alertas", number, _json(note),
                ])
            continue

        # Desconocidos completos: conservar JSON como detalle sin inventar
        # un tipo documental, ni convertirlo en contrato por accidente.
        result["OTROS_PDF"].append([*id_fields, filename, schema, "Otro esquema", ""])
        result["DETALLES"].append([
            *id_fields, schema, "resultado_json", 1, _json(payload),
        ])
    return result


def _excel_text(value: Any) -> str:
    text = "" if value is None else str(value)
    # Excel rechaza controles y limita cada celda a 32 767 caracteres.
    text = "".join(ch for ch in text if ord(ch) >= 32 or ch in "\t\n\r")
    if len(text) > 32767:
        text = text[:32736] + " [TRUNCADO; VER PDF ORIGINAL]"
    return text


def _column_name(index: int) -> str:
    letters = ""
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _sheet_xml(headers: tuple[str, ...], rows: Sequence[Sequence[Any]]) -> str:
    if len(rows) + 1 > 1048576:
        raise ValueError("La exportación supera el máximo de filas de Excel.")
    width = len(headers)
    cols = []
    for i, name in enumerate(headers, start=1):
        long = (
            name in ("CARPETA", "ARCHIVO", "ESQUEMA", "DATOS_JSON",
                     "EVIDENCIA", "VALOR_LITERAL", "ACTIVIDAD")
            or "observaciones" in name or "legislacion" in name
        )
        colwidth = 46 if long else 24 if name.startswith("ID_") else 26
        cols.append(f'<col min="{i}" max="{i}" width="{colwidth}" customWidth="1"/>')
    output = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
        '<sheetViews><sheetView workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        '</sheetView></sheetViews>',
        '<cols>', *cols, '</cols>',
        '<sheetData>',
    ]
    for row_no, row in enumerate((headers, *rows), start=1):
        cells = []
        for col, value in enumerate(row, start=1):
            tag = _column_name(col) + str(row_no)
            if isinstance(value, int) and not isinstance(value, bool):
                cells.append(f'<c r="{tag}" s="{1 if row_no == 1 else 0}"><v>{value}</v></c>')
            else:
                txt = escape(_excel_text(value), {'"': "&quot;", "'": "&apos;"})
                cells.append(
                    f'<c r="{tag}" s="{1 if row_no == 1 else 0}" t="inlineStr">'
                    f'<is><t xml:space="preserve">{txt}</t></is></c>'
                )
        output.append(
            f'<row r="{row_no}" ht="{26 if row_no == 1 else 20}" customHeight="1">'
            + "".join(cells) + '</row>'
        )
    output += [
        '</sheetData>',
        f'<autoFilter ref="A1:{_column_name(width)}{len(rows)+1}"/>',
        '</worksheet>',
    ]
    return "".join(output)


def workbook_bytes(data: Mapping[str, Sequence[Sequence[Any]]]) -> bytes:
    """XLSX ISO/IEC 29500 mínimo, con encabezados, filtros y filas congeladas.

    Inline strings evitan ejecutar fórmulas contenidas accidentalmente en
    documentos de terceros (CSV/Excel formula injection).
    """
    sheets = list(COLUMNS)
    ns = "http://schemas.openxmlformats.org/package/2006"
    content_types = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        f'<Types xmlns="{ns}/content-types">',
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
    ]
    content_types.extend(
        f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for i in range(1, len(sheets)+1)
    )
    content_types.append("</Types>")
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets>' +
        "".join(f'<sheet name="{name}" sheetId="{i}" r:id="rId{i}"/>'
                for i, name in enumerate(sheets, start=1)) +
        '</sheets></workbook>'
    )
    relations = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{ns}/relationships">'
        + "".join(
            f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{i}.xml"/>'
            for i in range(1, len(sheets)+1)
        )
        + f'<Relationship Id="rId{len(sheets)+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        + '</Relationships>'
    )
    styles = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="2"><font><sz val="10"/><name val="Aptos"/></font>'
        '<font><b/><color rgb="FFFFFFFF"/><sz val="10"/><name val="Aptos"/></font></fonts>'
        '<fills count="3"><fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FF17324F"/><bgColor indexed="64"/></patternFill></fill></fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFill="1" applyFont="1"/></cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        '</styleSheet>'
    )
    blob = BytesIO()
    with ZipFile(blob, "w", ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("[Content_Types].xml", "".join(content_types))
        archive.writestr("_rels/.rels", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<Relationships xmlns="{ns}/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>'
        ))
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relations)
        archive.writestr("xl/styles.xml", styles)
        for i, name in enumerate(sheets, start=1):
            archive.writestr(
                f"xl/worksheets/sheet{i}.xml",
                _sheet_xml(COLUMNS[name], data.get(name, [])),
            )
    return blob.getvalue()
