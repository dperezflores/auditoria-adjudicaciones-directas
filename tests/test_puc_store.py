"""PUC-v1: guardado único en Sheets, caché y bloqueo de cargos duplicados."""
from __future__ import annotations

import unittest

from services.drive_service import DocumentRecord
from services.extraction_store import (
    CONTRACT_HEADERS, DOCUMENT_HEADERS, EXTRACTION_HEADERS,
    ExtractionStateError,
)
from services.puc_gemini import PucGeminiResult
from services.puc_schema import PUC_HEADERS, PUC_SCHEMA_VERSION, parse_puc
from services.puc_store import extract_or_reuse_puc
from tests.test_puc_schema import sample_puc

WORK = "folderPucTest001"
DOC = "documentPucTest001"
PDF = b"%PDF-1.7 simulated PUC bytes"
MODEL = "model-test"


class Request:
    def __init__(self, value):
        self.value = value

    def execute(self):
        return self.value


class Values:
    def __init__(self):
        self.ex = [list(EXTRACTION_HEADERS)]
        self.contracts = [list(CONTRACT_HEADERS)]
        self.puc = [list(PUC_HEADERS)]
        self.docs = [list(DOCUMENT_HEADERS), [
            DOC, WORK, "PUC.pdf", "PUC", "application/pdf", "abc",
            "2026", "43000", "Pendiente", "2026", "2026", "SI", "", "", "", "1",
        ]]
        self.writes = 0

    def batchGet(self, **kwargs):
        return Request({"valueRanges": [
            {"values": self.ex}, {"values": self.contracts}, {"values": self.docs},
        ]})

    def get(self, **kwargs):
        if "DatosPUC" not in kwargs["range"]:
            raise AssertionError("La lectura adicional debe ser solo DatosPUC.")
        return Request({"values": self.puc})

    def batchUpdate(self, **kwargs):
        self.writes += 1
        data = kwargs["body"]["data"]
        for item in data:
            value = item["values"][0]
            region = item["range"]
            if region.startswith("'Extracciones'!"):
                if len(self.ex) == 1:
                    self.ex.append([""] * len(EXTRACTION_HEADERS))
                self.ex[1] = list(value)
            elif region.startswith("'DatosPUC'!"):
                if len(self.puc) == 1:
                    self.puc.append([""] * len(PUC_HEADERS))
                self.puc[1] = list(value)
            elif region.startswith("'Documentos'!I2"):
                self.docs[1][8] = value[0]
            elif region.startswith("'Documentos'!M2"):
                self.docs[1][12:15] = value
            else:
                raise AssertionError("Unexpected write: " + region)
        return Request({"responses": [{"updatedRows": 1} for _ in data]})


class Sheets:
    def __init__(self):
        self.v = Values()

    def spreadsheets(self):
        return self

    def values(self):
        return self.v


class PucStoreTests(unittest.TestCase):
    def setUp(self):
        self.sheets = Sheets()
        self.doc = DocumentRecord(id=DOC, name="PUC.pdf", md5_checksum="abc")
        self.calls = 0

    def do_extract(self, doc=None, invoke=None):
        if invoke is None:
            def invoke(pdf, key, *, model):
                self.calls += 1
                return PucGeminiResult(parse_puc(sample_puc()), 170, 90)
        return extract_or_reuse_puc(
            self.sheets, "sheet", PDF, doc or self.doc, WORK,
            "private-key", model=MODEL, invoke=invoke,
        )

    def test_new_puc_saved_in_both_tables_without_touching_contract_data(self):
        outcome = self.do_extract()
        self.assertFalse(outcome.cached)
        self.assertEqual(self.calls, 1)
        self.assertEqual(self.sheets.v.ex[1][7], PUC_SCHEMA_VERSION)
        self.assertEqual(self.sheets.v.ex[1][1], "COMPLETADO")
        self.assertEqual(self.sheets.v.puc[1][3], "GUTIERREZ GUTIERREZ DE VELASCO ALEJANDRO")
        self.assertEqual(self.sheets.v.puc[1][12], "$352,203.00")
        self.assertIn("PAVIMENTACION URBANA", self.sheets.v.puc[1][21])
        self.assertEqual(len(self.sheets.v.contracts), 1)
        self.assertEqual(self.sheets.v.docs[1][13], outcome.cache.clave)

    def test_reuse_same_pdf_never_calls_gemini_again(self):
        self.do_extract()
        output = self.do_extract()
        self.assertTrue(output.cached)
        self.assertEqual(self.calls, 1)
        self.assertEqual(len(self.sheets.v.puc), 2)

    def test_failed_request_blocks_automatic_retry(self):
        def unavailable(*args, **kwargs):
            self.calls += 1
            raise RuntimeError("test")
        with self.assertRaises(ExtractionStateError):
            self.do_extract(invoke=unavailable)
        self.assertEqual(self.sheets.v.ex[1][1], "REQUIERE_REVISION")
        with self.assertRaises(ExtractionStateError):
            self.do_extract()
        self.assertEqual(self.calls, 1)

    def test_non_puc_pdf_never_calls_provider(self):
        bad = DocumentRecord(id=DOC, name="CONTRATO.pdf", md5_checksum="abc")
        with self.assertRaises(ExtractionStateError):
            self.do_extract(doc=bad)
        self.assertEqual(self.calls, 0)
        self.assertEqual(self.sheets.v.writes, 0)

    def test_wrong_registered_type_and_hash_rejected_before_reservation(self):
        self.sheets.v.docs[1][3] = "CONTRATO"
        with self.assertRaises(ExtractionStateError):
            self.do_extract()
        self.sheets.v.docs[1][3] = "PUC"
        self.sheets.v.docs[1][5] = "changed"
        with self.assertRaises(ExtractionStateError):
            self.do_extract()
        self.assertEqual(self.calls, 0)
        self.assertEqual(self.sheets.v.writes, 0)

    def test_wrong_sheet_header_rejected_before_spending(self):
        self.sheets.v.puc[0][3] = "no_es_contratista"
        with self.assertRaises(ExtractionStateError):
            self.do_extract()
        self.assertEqual(self.calls, 0)

    def test_no_automatic_retry_if_sheets_does_not_confirm(self):
        # La primera reserva no llega a confirmarse en Sheets.
        original = self.sheets.v.batchUpdate
        def no_confirmation(**kwargs):
            response = original(**kwargs).execute()
            return Request({"responses": []})
        self.sheets.v.batchUpdate = no_confirmation
        with self.assertRaises(ExtractionStateError):
            self.do_extract()
        self.assertEqual(self.calls, 0)


if __name__ == "__main__":
    unittest.main()
