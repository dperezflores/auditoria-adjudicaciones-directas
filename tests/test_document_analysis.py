"""Pruebas de ficha documental y caché, sin invocaciones reales a Gemini."""
from __future__ import annotations
import unittest

from services.document_analysis import (
    GENERAL_KIND, GENERAL_PROMPT_VERSION, GENERAL_SCHEMA,
    GeneralAnalysis, analyze_document,
)
from services.drive_service import DocumentRecord
from services.extraction_store import DOCUMENT_HEADERS, EXTRACTION_HEADERS, CONTRACT_HEADERS, ExtractionStateError

DOC = "pdfFILE0001234"
WORK = "workFOLDER1234"
PDF = b"%PDF-1.5 fake pdf"

def result():
    return GeneralAnalysis.model_validate({
        "tipo_documental": "PUC",
        "resumen": "Padrón de contratistas (simulado).",
        "campos": [
            {"campo": "Folio", "valor": "001", "pagina": 1, "evidencia": "Folio 001"},
        ],
        "alertas": ["Verificar vigencia contra documentos."],
    })

class Request:
    def __init__(self, data):
        self.data = data
    def execute(self):
        return self.data

class Values:
    def __init__(self):
        self.doc = [list(DOCUMENT_HEADERS), [
            DOC, WORK, "PUC.pdf", "", "application/pdf", "abc",
            "2026", "20", "Pendiente", "2026", "2026", "SI", "", "", "", "1",
        ]]
        self.ex = [list(EXTRACTION_HEADERS)]
        self.ct = [list(CONTRACT_HEADERS)]
        self.calls = 0

    def batchGet(self, **kwargs):
        return Request({"valueRanges": [
            {"values": self.ex}, {"values": self.ct}, {"values": self.doc},
        ]})

    def batchUpdate(self, **kwargs):
        parts = kwargs["body"]["data"]
        for part in parts:
            addr = part["range"]
            values = part["values"][0]
            if addr.startswith("'Extracciones'!"):
                if "A2" in addr:
                    if len(self.ex) == 1:
                        self.ex.append([""] * len(EXTRACTION_HEADERS))
                    self.ex[1] = list(values)
            if addr.startswith("'Documentos'!I2"):
                self.doc[1][8] = values[0]
            if addr.startswith("'Documentos'!M2"):
                self.doc[1][12:15] = values
        self.calls += 1
        return Request({"responses": [
            {"updatedRows": 1} for _ in parts
        ]})

class Sheets:
    def __init__(self):
        self.data = Values()
    def spreadsheets(self):
        return self
    def values(self):
        return self.data

class DocumentAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.client = Sheets()
        self.doc = DocumentRecord(id=DOC,name="PUC.pdf",md5_checksum="abc")
        self.invoked = 0

    def fake(self, bytes_, key, *, model):
        self.invoked += 1
        self.assertEqual(bytes_, PDF)
        self.assertEqual(key, "private-key")
        return result(), 10, 5

    def analyze(self):
        return analyze_document(
            self.client, "sheet", PDF, self.doc, WORK, "private-key",
            model="gemini-test", invoke=self.fake,
        )

    def test_generates_once_and_cache_reuses(self):
        first = self.analyze()
        self.assertFalse(first.cached)
        self.assertEqual(self.invoked, 1)
        self.assertEqual(first.report.campos[0].pagina, 1)
        self.assertEqual(self.client.data.ex[1][1], "COMPLETADO")
        self.assertEqual(self.client.data.doc[1][13], first.cache.clave)
        second = self.analyze()
        self.assertTrue(second.cached)
        self.assertEqual(self.invoked, 1)

    def test_failed_inference_is_not_retried(self):
        def bad(*args, **kwargs):
            self.invoked += 1
            raise RuntimeError("No capacity")
        with self.assertRaises(ExtractionStateError):
            analyze_document(
                self.client, "sheet", PDF, self.doc, WORK, "private-key",
                model="gemini-test", invoke=bad,
            )
        self.assertEqual(self.client.data.ex[1][1], "REQUIERE_REVISION")
        with self.assertRaises(ExtractionStateError):
            self.analyze()
        self.assertEqual(self.invoked, 1)

    def test_inactive_document_blocks_api(self):
        self.client.data.doc[1][11] = "NO"
        with self.assertRaises(ExtractionStateError):
            self.analyze()
        self.assertEqual(self.invoked, 0)

    def test_schema_without_recursive_defs(self):
        self.assertEqual(GENERAL_SCHEMA["type"], "object")
        self.assertIn("campos", GENERAL_SCHEMA["properties"])
        self.assertNotIn("$defs", str(GENERAL_SCHEMA))
        self.assertEqual(GENERAL_PROMPT_VERSION, "documento-prompt-v1")
        self.assertEqual(GENERAL_KIND, "ficha_documental")


if __name__ == "__main__":
    unittest.main()
