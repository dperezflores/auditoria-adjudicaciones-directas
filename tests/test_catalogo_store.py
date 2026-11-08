"""Regresión del almacenamiento XLSX sin Gemini con cliente Sheets simulado."""
from __future__ import annotations

from unittest.mock import patch
import unittest

from services.catalogo_store import import_or_reuse_catalogo, MODEL
from services.catalogo_xlsx import CATALOGO_SCHEMA_VERSION
from services.document_classifier import XLSX_MIME
from services.drive_service import DocumentRecord
from services.extraction_store import DOCUMENT_HEADERS, EXTRACTION_HEADERS, ExtractionStateError
from test_catalogo_xlsx import sample, workbook

DOC = "fileXLSX00001"
WORK = "workFOLDERXLSX"


class CatalogoStoreTests(unittest.TestCase):
    def setUp(self):
        self.raw = workbook(sample())
        self.doc = DocumentRecord(
            id=DOC, name="CATALOGO.xlsx", mime_type=XLSX_MIME,
            md5_checksum="fake-drive-md5", size_bytes=len(self.raw),
        )
        self.tables = {
            "Documentos": [[
                DOC, WORK, "CATALOGO.xlsx", "CATALOGO", XLSX_MIME,
                "fake-drive-md5", "2026", str(len(self.raw)), "Pendiente",
                "2026", "2026", "SI", "", "", "", "1",
            ]],
            "Extracciones": [],
            "DatosContrato": [],
        }
        self.saved_catalog = []
        self.writes = []

    def _batch_write(self, sheets, sheet_id, writes):
        self.writes.extend(writes)
        for name, number, cells in writes:
            if name == "Extracciones":
                if len(self.tables["Extracciones"]) < number - 1:
                    self.tables["Extracciones"].append(list(cells))
                else:
                    self.tables["Extracciones"][number - 2] = list(cells)

    def _write_regions(self, sheets, sheet_id, writes):
        self.writes.extend(writes)
        for write in writes:
            target = write["range"]
            if target.startswith("'Extracciones'!"):
                self.tables["Extracciones"][0] = list(write["values"][0])
            elif target.startswith("'DatosCatalogo'!"):
                self.saved_catalog.extend([list(row) for row in write["values"]])

    def _process(self, *, invalid=False):
        with (
            patch("services.catalogo_store._sheet_rows", return_value=self.tables),
            patch("services.catalogo_store.ensure_catalog_table"),
            patch("services.catalogo_store.load_catalog_rows", side_effect=lambda *args: self.saved_catalog),
            patch("services.catalogo_store._batch_write", side_effect=self._batch_write),
            patch("services.catalogo_store._write_regions", side_effect=self._write_regions),
        ):
            return import_or_reuse_catalogo(None, "sheet", b"broken" if invalid else self.raw,
                                           self.doc, WORK)

    def test_original_rows_saved_once_then_cache_reused(self):
        first = self._process()
        self.assertFalse(first.cached)
        self.assertEqual(MODEL, "lector-local-xlsx")
        self.assertEqual(len(self.saved_catalog), 2)
        self.assertEqual(self.saved_catalog[0][9], "10")
        self.assertEqual(self.saved_catalog[0][11], "1205.00")
        self.assertEqual(self.tables["Extracciones"][0][1], "COMPLETADO")
        self.assertEqual(self.tables["Extracciones"][0][7], CATALOGO_SCHEMA_VERSION)
        second = self._process()
        self.assertTrue(second.cached)
        self.assertEqual(len(self.saved_catalog), 2)
        self.assertEqual(len(self.tables["Extracciones"]), 1)

    def test_invalid_xlsx_does_not_create_pending_extraction(self):
        with self.assertRaises(ExtractionStateError):
            self._process(invalid=True)
        self.assertFalse(self.tables["Extracciones"])
        self.assertFalse(self.saved_catalog)

    def test_mismatched_drive_registration_is_blocked(self):
        self.tables["Documentos"][0][5] = "changed-hash"
        with self.assertRaises(ExtractionStateError):
            self._process()
        self.assertFalse(self.saved_catalog)


if __name__ == "__main__":
    unittest.main()
