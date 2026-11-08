"""DICTAMEN_AD: almacenamiento seguro, caché y protección de datos PUC."""
from __future__ import annotations
import json
import unittest

from services.dictamen_gemini import DictamenGeminiResult
from services.dictamen_schema import DICTAMEN_HEADERS, DICTAMEN_SCHEMA_VERSION, parse_dictamen
from services.dictamen_store import extract_or_reuse_dictamen
from services.drive_service import DocumentRecord
from services.extraction_store import (
    EXTRACTION_HEADERS, DOCUMENT_HEADERS, CONTRACT_HEADERS, ExtractionStateError,
)
from tests.test_dictamen_schema import sample_dictamen

DOC="dictamenFile123"
WORK="obraPrueba123"
PDF=b"%PDF-1.4 simulated dictamen"
MODEL="gemini-test"

class Request:
    def __init__(self, data):
        self.data = data
    def execute(self):
        return self.data

class Values:
    def __init__(self):
        self.ex = [list(EXTRACTION_HEADERS)]
        self.contracts = [list(CONTRACT_HEADERS)]
        self.dictamen = [list(DICTAMEN_HEADERS)]
        self.docs = [list(DOCUMENT_HEADERS), [
            DOC, WORK, "DICTAMEN_AD.pdf", "DICTAMEN_AD", "application/pdf", "abc",
            "2026", "100", "Pendiente", "2026", "2026", "SI", "", "", "", "1",
        ]]
        self.writes = 0
    def batchGet(self, **kwargs):
        return Request({"valueRanges": [
            {"values": self.ex}, {"values": self.contracts}, {"values": self.docs},
        ]})
    def get(self, **kwargs):
        if "DatosDictamenAD" not in kwargs["range"]:
            raise AssertionError("Lectura inesperada: " + kwargs["range"])
        return Request({"values": self.dictamen})
    def batchUpdate(self, **kwargs):
        entries = kwargs["body"]["data"]
        self.writes += 1
        for item in entries:
            region, value = item["range"], item["values"][0]
            if region.startswith("'Extracciones'!"):
                if len(self.ex) == 1:
                    self.ex.append([""] * len(EXTRACTION_HEADERS))
                self.ex[1] = list(value)
            elif region.startswith("'DatosDictamenAD'!"):
                if len(self.dictamen) == 1:
                    self.dictamen.append([""] * len(DICTAMEN_HEADERS))
                self.dictamen[1] = list(value)
            elif region.startswith("'Documentos'!I2"):
                self.docs[1][8] = value[0]
            elif region.startswith("'Documentos'!M2"):
                self.docs[1][12:15] = value
            else:
                raise AssertionError("Escritura a pestaña inesperada: "+region)
        return Request({"responses":[{"updatedRows":1} for _ in entries]})

class Sheets:
    def __init__(self):
        self.v = Values()
    def spreadsheets(self):
        return self
    def values(self):
        return self.v

class DictamenStoreTests(unittest.TestCase):
    def setUp(self):
        self.sheets=Sheets()
        self.doc=DocumentRecord(id=DOC, name="DICTAMEN_AD.pdf", md5_checksum="abc")
        self.calls=0
    def do_extract(self, *, doc=None, invoke=None):
        if invoke is None:
            def invoke(pdf, key, *, model):
                self.calls+=1
                return DictamenGeminiResult(parse_dictamen(sample_dictamen()), 80, 70)
        return extract_or_reuse_dictamen(
            self.sheets, "sheet", PDF, doc or self.doc, WORK,
            "private-api-key", model=MODEL, invoke=invoke,
        )

    def test_persists_literals_and_lists_and_preserves_other_tabs(self):
        result=self.do_extract()
        self.assertFalse(result.cached)
        self.assertEqual(self.calls,1)
        self.assertEqual(self.sheets.v.ex[1][1],"COMPLETADO")
        self.assertEqual(self.sheets.v.ex[1][7], DICTAMEN_SCHEMA_VERSION)
        self.assertEqual(self.sheets.v.dictamen[1][3],"DGOP/586/CONT/2025")
        self.assertEqual(self.sheets.v.dictamen[1][13],"$ 2,231,632.00")
        self.assertIn("artículo 76",self.sheets.v.dictamen[1][22])
        self.assertIn("vigencia_puc",self.sheets.v.dictamen[1][23])
        self.assertIn("Padrón Único",self.sheets.v.dictamen[1][24])
        self.assertEqual(json.loads(self.sheets.v.dictamen[1][25])["presencia"],"indeterminada")
        self.assertEqual(self.sheets.v.docs[1][13],result.cache.clave)
        self.assertEqual(len(self.sheets.v.contracts),1)
        self.assertEqual(len(self.sheets.v.dictamen[1]),len(DICTAMEN_HEADERS))

    def test_complete_cache_is_reused_without_second_gemini(self):
        first=self.do_extract()
        second=self.do_extract()
        self.assertFalse(first.cached)
        self.assertTrue(second.cached)
        self.assertEqual(self.calls,1)
        self.assertEqual(len(self.sheets.v.dictamen),2)

    def test_failed_or_ambiguous_attempt_blocks_retry(self):
        def invalid(*args,**kwargs):
            self.calls+=1
            raise RuntimeError("No se recibió respuesta")
        with self.assertRaises(ExtractionStateError):
            self.do_extract(invoke=invalid)
        self.assertEqual(self.sheets.v.ex[1][1],"REQUIERE_REVISION")
        with self.assertRaises(ExtractionStateError):
            self.do_extract()
        self.assertEqual(self.calls,1)

    def test_non_dictamen_never_reaches_gemini(self):
        with self.assertRaises(ExtractionStateError):
            self.do_extract(doc=DocumentRecord(
                id=DOC, name="PUC.pdf", md5_checksum="abc"
            ))
        self.assertEqual(self.calls,0)
        self.assertEqual(self.sheets.v.writes,0)

    def test_wrong_header_registered_type_or_md5_blocks_calls(self):
        self.sheets.v.dictamen[0][0]="CLAVE_INVALIDA"
        with self.assertRaises(ExtractionStateError):
            self.do_extract()
        self.sheets.v.dictamen[0][0]="cache_key"
        self.sheets.v.docs[1][3]="PUC"
        with self.assertRaises(ExtractionStateError):
            self.do_extract()
        self.sheets.v.docs[1][3]="DICTAMEN_AD"
        self.sheets.v.docs[1][5]="changed"
        with self.assertRaises(ExtractionStateError):
            self.do_extract()
        self.assertEqual(self.calls,0)

if __name__=="__main__":
    unittest.main()
