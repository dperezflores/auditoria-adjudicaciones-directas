"""Validación relacional y OOXML del Excel generado desde PDFs sin IA."""
from __future__ import annotations

from io import BytesIO
from xml.etree import ElementTree as ET
from zipfile import ZipFile
import unittest

from services.contract_portfolio import prepare_contract_portfolio
from services.document_export import COLUMNS, export_document_tables, workbook_bytes
from tests.test_document_links_specialized import base_fixture


class DocumentExportTests(unittest.TestCase):
    def _tables(self, dataset=None):
        source = dataset if dataset is not None else base_fixture()
        portfolio = prepare_contract_portfolio(source)
        fields = {
            "Obras": (
                "obra_id", "nombre_carpeta", "estado_expediente", "total_pdf",
                "pdf_pendientes", "pdf_modificados", "ultima_vista_utc", "activo", "revision",
            ),
            "Documentos": (
                "documento_id", "obra_id", "nombre_archivo", "tipo_documental",
                "mime_type", "md5_checksum", "fecha_modificacion_drive",
                "tamano_bytes", "estado_procesamiento", "primera_deteccion_utc",
                "ultima_deteccion_utc", "activo", "version_extractor",
                "resultado_id", "ultimo_error", "revision",
            ),
            "Extracciones": (
                "cache_key", "estado", "documento_id", "obra_id", "sha256_pdf",
                "modelo", "version_prompt", "version_esquema", "creado_utc",
                "actualizado_utc", "resultado_json", "tokens_entrada",
                "tokens_salida", "ultimo_error",
            ),
        }
        def items(name):
            return [dict(zip(fields[name], row)) for row in source[name][1:]]
        return export_document_tables(
            items("Obras"), items("Documentos"), items("Extracciones"),
            portfolio.records,
        )

    def test_pdf_only_and_same_id_relates_every_sheet(self):
        result = self._tables()
        self.assertEqual(len(result["OBRAS"]), 1)
        self.assertEqual(len(result["DOCUMENTOS"]), 5)
        self.assertEqual(len(result["CONTRATOS"]), 1)
        self.assertEqual(len(result["PUC"]), 1)
        self.assertEqual(len(result["DICTAMEN_AD"]), 1)
        self.assertEqual(len(result["NOTIFICACION_AD"]), 1)
        self.assertEqual(len(result["ORDEN_AD"]), 1)
        self.assertEqual(len(result["ESPECIALIDADES"]), 1)
        self.assertGreater(len(result["EVIDENCIAS"]), 4)
        self.assertGreater(len(result["DETALLES"]), 0)
        all_ids = [row[0] for table in result.values() for row in table]
        self.assertEqual(set(all_ids), {1})
        all_docs = [row[2] for table in result.values() for row in table if len(row)>2]
        self.assertNotIn("catalogDocTest", all_docs)
        self.assertFalse(any("CATALOGO" in key for key in COLUMNS))

    def test_new_document_does_not_change_existing_obra_id(self):
        data = base_fixture()
        first = self._tables(data)
        record_id = first["OBRAS"][0][0]
        data["Obras"].append(["laterFolder", "Nueva obra", "", "1", "1", "0", "", "SI", "1"])
        data["Documentos"].append([
            "docLater", "laterFolder", "PUC.pdf", "PUC",
            "application/pdf", "md5", "2026", "1000", "Pendiente",
            "2026", "2026", "SI", "", "", "", "1",
        ])
        second = self._tables(data)
        self.assertEqual(second["OBRAS"][0][0], record_id)
        # El fixture ya contiene otra obra registrada sin PDF (ID 2).
        # No renumerarla mantiene las relaciones históricas.
        self.assertEqual(second["OBRAS"][1][0], 3)
        self.assertIn([3, "laterFolder", "docLater", "PUC.pdf", "PUC",
                       "Pendiente", "Sin análisis vigente", "", ""], second["DOCUMENTOS"])

    def test_stale_or_cross_work_cache_not_exported_as_current(self):
        data = base_fixture()
        puc = next(row for row in data["Documentos"] if row[3] == "PUC")
        puc[8] = "Modificado desde el último análisis"
        rows = self._tables(data)
        self.assertFalse(rows["PUC"])
        target = next(row for row in rows["DOCUMENTOS"] if row[2] == puc[0])
        self.assertEqual(target[6], "Sin análisis vigente")

    def test_excel_contains_all_tabs_and_spreadsheet_metadata(self):
        data = self._tables()
        raw = workbook_bytes(data)
        self.assertTrue(raw.startswith(b"PK"))
        with ZipFile(BytesIO(raw)) as archive:
            self.assertEqual(archive.testzip(), None)
            self.assertIn("xl/workbook.xml", archive.namelist())
            book = ET.fromstring(archive.read("xl/workbook.xml"))
            namespace = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            names = [item.attrib["name"] for item in book.findall("m:sheets/m:sheet", namespace)]
            self.assertEqual(names, list(COLUMNS))
            sheet = ET.fromstring(archive.read("xl/worksheets/sheet2.xml"))
            xml = archive.read("xl/worksheets/sheet2.xml").decode("utf-8")
            self.assertIn("autoFilter", xml)
            self.assertIn("state=\"frozen\"", xml)
            self.assertIn("PUC", xml)
            self.assertNotIn("CATALOGO.xlsx", xml)
            self.assertEqual(len(sheet.findall("m:sheetData/m:row", namespace)), 6)

    def test_external_text_is_inline_not_a_formula(self):
        content = {name: [] for name in COLUMNS}
        content["OBRAS"] = [[1, "folder", "='HYPERLINK(\"https://bad\")", "Activo"]]
        raw = workbook_bytes(content)
        with ZipFile(BytesIO(raw)) as archive:
            xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
            self.assertNotIn("<f>", xml)
            self.assertIn('t="inlineStr"', xml)
            self.assertIn("HYPERLINK", xml)


if __name__ == "__main__":
    unittest.main()
