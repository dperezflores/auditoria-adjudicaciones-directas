"""Pruebas de la lectura local del prefiniquito, sin Gemini ni archivos externos."""
from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile
from xml.sax.saxutils import escape
import unittest

from services.catalogo_xlsx import (
    CATALOGO_HEADERS, CATALOGO_SCHEMA_VERSION, CatalogoFormatError,
    parse_catalogo_xlsx,
)

N = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
P = "http://schemas.openxmlformats.org/package/2006/relationships"


def workbook(rows):
    """XLSX real mínimo con columnas A:H, sin depender de openpyxl ni de IA."""
    def cell(addr, value):
        if value is None:
            return ""
        if isinstance(value, (int, float)):
            return f'<c r="{addr}"><v>{value}</v></c>'
        return f'<c r="{addr}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'

    body = []
    for n, row in enumerate(rows, 1):
        cells = "".join(cell(chr(65 + k) + str(n), x) for k, x in enumerate(row))
        body.append(f'<row r="{n}">{cells}</row>')
    xml = f'<worksheet xmlns="{N}"><sheetData>{"".join(body)}</sheetData></worksheet>'
    book = (f'<workbook xmlns="{N}" xmlns:r="{R}"><sheets>'
            '<sheet name="PRE FINIQUITO" sheetId="1" r:id="rId1"/>'
            '</sheets></workbook>')
    rel = (f'<Relationships xmlns="{P}"><Relationship Id="rId1" '
           'Target="worksheets/sheet1.xml"/></Relationships>')
    blob = BytesIO()
    with ZipFile(blob, "w") as z:
        z.writestr("xl/workbook.xml", book)
        z.writestr("xl/_rels/workbook.xml.rels", rel)
        z.writestr("xl/worksheets/sheet1.xml", xml)
    return blob.getvalue()


def sample():
    return [
        ["Contrato A-001"],
        ["Clave", "Descripción", "Unidad", "Inicial",
         "Excedente", "Total Aut.", "Precio U.", "Contrato"],
        ["PRESUPUESTO: 0 CONTRATO ORIGINAL"],
        ["CAPÍTULO: 1 OBRA CIVIL"],
        ["C.00.0001", "Excavación", "M3", 10, 4, 14, 120.50, 1687.0],
        ["C.00.0002", "Relleno", "M3", 3, 0, 3, 75, 225],
        ["CAPÍTULO: 2 FUERA DE CATALOGO"],
        ["F.00.0001", "Extraordinario", "M3", 0, 8, 8, 1000, 8000],
        ["", "", "", "", "", "", "", ""],
    ]


class CatalogoXlsxTests(unittest.TestCase):
    def test_original_uses_inicial_and_price_never_total_authorized(self):
        result = parse_catalogo_xlsx(workbook(sample()))
        self.assertEqual(CATALOGO_SCHEMA_VERSION, "catalogo-xlsx-v1")
        self.assertEqual(len(CATALOGO_HEADERS), 13)
        self.assertEqual(len(result.conceptos), 2)
        self.assertEqual(result.conceptos[0].clave, "C.00.0001")
        self.assertEqual(result.conceptos[0].cantidad_original, "10")
        self.assertEqual(result.conceptos[0].importe_original, "1205.00")
        self.assertEqual(result.total_original, "1430.00")
        self.assertEqual(result.originales_con_excedente, 1)
        self.assertEqual(result.excluidos_fuera_catalogo, 1)

    def test_same_clave_in_same_and_other_chapters_preserves_all_rows(self):
        rows = sample()
        rows.insert(5, [
            "C.00.0001", "Excavación", "M3", 2, 0, 2, 120.50, 241,
        ])
        rows.insert(7, ["CAPÍTULO: 2 ANDADOR"])
        rows.insert(8, [
            "C.00.0001", "Excavación", "M3", 5, 0, 5, 120.50, 602.50,
        ])
        result = parse_catalogo_xlsx(workbook(rows))
        self.assertEqual(len(result.conceptos), 4)
        reused = [c for c in result.conceptos if c.clave == "C.00.0001"]
        self.assertEqual(len(reused), 3)
        self.assertEqual([c.cantidad_original for c in reused], ["10", "2", "5"])
        self.assertEqual([c.importe_original for c in reused],
                         ["1205.00", "241.00", "602.50"])
        self.assertEqual(len({(c.hoja, c.fila) for c in reused}), 3)
        self.assertNotEqual(reused[0].capitulo, reused[2].capitulo)
        self.assertEqual(result.total_original, "2273.50")
        self.assertEqual(result.excluidos_fuera_catalogo, 1)

    def test_does_not_import_additional_budget_even_when_initial_is_positive(self):
        rows = sample()[:-1] + [
            ["PRESUPUESTO: 1 ADICIONAL"],
            ["CAPÍTULO: 1 OBRAS EXTRAORDINARIAS"],
            ["F.00.0002", "Adicional", "PZA", 4, 0, 4, 300, 1200],
        ]
        result = parse_catalogo_xlsx(workbook(rows))
        self.assertEqual(len(result.conceptos), 2)
        self.assertEqual(result.excluidos_fuera_catalogo, 2)

    def test_ambiguous_quantity_does_not_silently_overwrite_original(self):
        rows = sample()
        rows[1][3] = "Cantidad"
        with self.assertRaises(CatalogoFormatError):
            parse_catalogo_xlsx(workbook(rows))

    def test_missing_price_causes_no_partial_import(self):
        rows = sample()
        rows[4][6] = None
        with self.assertRaisesRegex(CatalogoFormatError, "Precio"):
            parse_catalogo_xlsx(workbook(rows))

    def test_zero_original_is_excluded_even_if_excess_authorized(self):
        rows = sample()
        rows.insert(6, ["C.00.0003", "Solo excedente", "M3", 0, 2, 2, 300, 600])
        result = parse_catalogo_xlsx(workbook(rows))
        self.assertEqual(len(result.conceptos), 2)
        self.assertEqual(result.excluidos_sin_cantidad_inicial, 1)

    def test_invalid_xlsx_fails_closed(self):
        with self.assertRaises(CatalogoFormatError):
            parse_catalogo_xlsx(b"NOT_XLSX")


if __name__ == "__main__":
    unittest.main()
