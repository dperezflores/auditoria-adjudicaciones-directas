"""Contrato v2: guardado atómico y reutilización sin gastos duplicados."""
from __future__ import annotations

import unittest

from services.contract_v2 import CONTRACT_V2_FIELDS, CONTRACT_V2_HEADERS, parse_contract_v2
from services.drive_service import DocumentRecord
from services.extraction_store import (
    CONTRACT_HEADERS, DOCUMENT_HEADERS, EXTRACTION_HEADERS, ExtractionStateError,
)
from services.extraction_store_v2 import extract_or_reuse_v2
from services.gemini_service import GeminiResult

DOC = "contractFile01234"
WORK = "folderWork01234"
PDF = b"%PDF-1.5 simulated contract"
MODEL = "gemini-test"


def sample_v2():
    fields = [
        {"campo": x, "valor": None, "pagina": None, "evidencia": None}
        for x in CONTRACT_V2_FIELDS
    ]
    fields[0].update({
        "valor": "A-001/2026", "pagina": 1,
        "evidencia": "CONTRATO A-001/2026",
    })
    fields[3].update({
        "valor": "CONSTRUCTORA DEL BAJÍO, S.A. DE C.V.",
        "pagina": 2, "evidencia": "CONSTRUCTORA DEL BAJÍO, S.A. DE C.V.",
    })
    return parse_contract_v2({
        "campos": fields,
        "personas": [{
            "nombre": "ING. PEDRO RAMÍREZ",
            "cargo_o_caracter": "RESIDENTE",
            "representacion": "LA CONTRATANTE",
            "pagina": 3,
            "evidencia": "ING. PEDRO RAMÍREZ",
        }],
        "observaciones": [],
    })


class Request:
    def __init__(self, data):
        self.data = data
    def execute(self):
        return self.data


class Values:
    def __init__(self):
        self.ex = [list(EXTRACTION_HEADERS)]
        self.ct = [list(CONTRACT_HEADERS)]
        self.v2 = [list(CONTRACT_V2_HEADERS)]
        self.docs = [list(DOCUMENT_HEADERS), [
            DOC, WORK, "CONTRATO.pdf", "", "application/pdf", "abc",
            "2026", "100", "Pendiente", "2026", "2026", "SI", "", "", "", "1",
        ]]
        self.total_writes = 0

    def batchGet(self, **kwargs):
        return Request({"valueRanges": [
            {"values": self.ex}, {"values": self.ct}, {"values": self.docs},
        ]})

    def get(self, **kwargs):
        if "DatosContratoV2" not in kwargs["range"]:
            raise AssertionError("La lectura debe ser solo de DatosContratoV2")
        return Request({"values": self.v2})

    def batchUpdate(self, **kwargs):
        entries = kwargs["body"]["data"]
        self.total_writes += 1
        for entry in entries:
            name = entry["range"]
            row_values = entry["values"][0]
            if name.startswith("'Extracciones'!"):
                if len(self.ex) == 1:
                    self.ex.append([""] * len(EXTRACTION_HEADERS))
                self.ex[1] = list(row_values)
            elif name.startswith("'DatosContratoV2'!"):
                if len(self.v2) == 1:
                    self.v2.append([""] * len(CONTRACT_V2_HEADERS))
                self.v2[1] = list(row_values)
            elif name.startswith("'Documentos'!I2"):
                self.docs[1][8] = row_values[0]
            elif name.startswith("'Documentos'!M2"):
                self.docs[1][12:15] = row_values
            else:
                raise AssertionError("Se intentó modificar otra pestaña: " + name)
        return Request({"responses": [{"updatedRows": 1} for _ in entries]})


class Sheets:
    def __init__(self):
        self.v = Values()
    def spreadsheets(self):
        return self
    def values(self):
        return self.v


class StoreV2Tests(unittest.TestCase):
    def setUp(self):
        self.sheet = Sheets()
        self.doc = DocumentRecord(id=DOC, name="CONTRATO.pdf", md5_checksum="abc")
        self.calls = 0

    def do_extract(self, invoke=None):
        if invoke is None:
            def invoke(pdf, key, *, model):
                self.calls += 1
                return GeminiResult(sample_v2(), 100, 30)
        return extract_or_reuse_v2(
            self.sheet, "master", PDF, self.doc, WORK,
            "key-private", model=MODEL, invoke=invoke,
        )

    def test_writes_v2_without_touching_legacy_contracts(self):
        output = self.do_extract()
        self.assertFalse(output.cached)
        self.assertEqual(self.calls, 1)
        self.assertEqual(self.sheet.v.ex[1][1], "COMPLETADO")
        self.assertEqual(self.sheet.v.ex[1][7], "contrato-v2")
        self.assertEqual(len(self.sheet.v.ct), 1)
        self.assertEqual(len(self.sheet.v.v2), 2)
        self.assertEqual(self.sheet.v.v2[1][3], "A-001/2026")
        self.assertIn("ING. PEDRO RAMÍREZ", self.sheet.v.v2[1][19])
        self.assertEqual(self.sheet.v.docs[1][13], output.cache.clave)

    def test_cache_reuses_same_result_and_no_second_gemini(self):
        first = self.do_extract()
        second = self.do_extract()
        self.assertFalse(first.cached)
        self.assertTrue(second.cached)
        self.assertEqual(self.calls, 1)

    def test_error_blocks_retry(self):
        def faulty(*args, **kwargs):
            self.calls += 1
            raise RuntimeError("Provider failure")
        with self.assertRaises(ExtractionStateError):
            self.do_extract(invoke=faulty)
        self.assertEqual(self.sheet.v.ex[1][1], "REQUIERE_REVISION")
        with self.assertRaises(ExtractionStateError):
            self.do_extract()
        self.assertEqual(self.calls, 1)
        self.assertEqual(len(self.sheet.v.v2), 1)

    def test_wrong_header_fails_before_gemini(self):
        self.sheet.v.v2[0][1] = "mal_encabezado"
        with self.assertRaises(ExtractionStateError):
            self.do_extract()
        self.assertEqual(self.calls, 0)

    def test_inactive_or_modified_pdf_is_not_reused(self):
        self.sheet.v.docs[1][11] = "NO"
        with self.assertRaises(ExtractionStateError):
            self.do_extract()
        self.assertEqual(self.calls, 0)


if __name__ == "__main__":
    unittest.main()
