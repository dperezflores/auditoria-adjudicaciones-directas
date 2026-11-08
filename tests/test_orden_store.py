"""ORDEN_AD: guardar, reutilizar y bloquear reintentos; sin Gemini real."""
from __future__ import annotations
import json
import unittest

from services.orden_gemini import OrdenGeminiResult
from services.orden_schema import ORDEN_HEADERS, ORDEN_SCHEMA_VERSION, parse_orden
from services.orden_store import extract_or_reuse_orden
from services.drive_service import DocumentRecord
from services.extraction_store import EXTRACTION_HEADERS, DOCUMENT_HEADERS, CONTRACT_HEADERS, ExtractionStateError
from tests.test_orden_schema import sample_orden

DOC="ordenFileTest12345"
WORK="obraOrdenTest12345"
PDF=b"%PDF-1.7 simulated orden"
MODEL="gemini-test"


class Request:
    def __init__(self, result):
        self.result=result
    def execute(self):
        return self.result


class Values:
    def __init__(self):
        self.ex=[list(EXTRACTION_HEADERS)]
        self.contracts=[list(CONTRACT_HEADERS)]
        self.orden=[list(ORDEN_HEADERS)]
        self.docs=[list(DOCUMENT_HEADERS),[
            DOC,WORK,"ORDEN_AD.pdf","ORDEN_AD","application/pdf",
            "abc", "2026","9800","Pendiente","2026","2026","SI","","","","1",
        ]]
        self.writes=0

    def batchGet(self, **kwargs):
        return Request({"valueRanges":[
            {"values":self.ex},{"values":self.contracts},{"values":self.docs},
        ]})

    def get(self, **kwargs):
        if "DatosOrdenAD" not in kwargs["range"]:
            raise AssertionError("Unexpected table")
        return Request({"values":self.orden})

    def batchUpdate(self, **kwargs):
        writes=kwargs["body"]["data"]
        self.writes+=1
        for row in writes:
            dest, vals = row["range"], row["values"][0]
            if dest.startswith("'Extracciones'!"):
                if len(self.ex)==1:
                    self.ex.append([""]*len(EXTRACTION_HEADERS))
                self.ex[1]=list(vals)
            elif dest.startswith("'DatosOrdenAD'!"):
                if len(self.orden)==1:
                    self.orden.append([""]*len(ORDEN_HEADERS))
                self.orden[1]=list(vals)
            elif dest.startswith("'Documentos'!I2"):
                self.docs[1][8]=vals[0]
            elif dest.startswith("'Documentos'!M2"):
                self.docs[1][12:15]=vals
            else:
                raise AssertionError("Unexpected write: "+dest)
        return Request({"responses":[{"updatedRows":1} for _ in writes]})


class Sheets:
    def __init__(self):
        self.v=Values()
    def spreadsheets(self):
        return self
    def values(self):
        return self.v


class OrdenStoreTests(unittest.TestCase):
    def setUp(self):
        self.sheet=Sheets()
        self.doc=DocumentRecord(id=DOC,name="ORDEN_AD.pdf",md5_checksum="abc")
        self.calls=0

    def extract(self, *, doc=None, invoke=None):
        if invoke is None:
            def invoke(pdf,key,*,model):
                self.calls+=1
                return OrdenGeminiResult(parse_orden(sample_orden()),120,80)
        return extract_or_reuse_orden(
            self.sheet, "sheet", PDF, doc or self.doc,WORK,
            "dummy-api-key",model=MODEL,invoke=invoke,
        )

    def test_saves_32_columns_and_literal_lists(self):
        result=self.extract()
        self.assertFalse(result.cached)
        self.assertEqual(self.calls,1)
        self.assertEqual(self.sheet.v.ex[1][7],ORDEN_SCHEMA_VERSION)
        self.assertEqual(self.sheet.v.ex[1][1],"COMPLETADO")
        row=self.sheet.v.orden[1]
        self.assertEqual(row[3],"0589")
        self.assertEqual(row[10],"$ 1,234,567.89")
        self.assertIn("ING. PEDRO",row[25])
        self.assertIn("DOS DÍAS HÁBILES",row[26])
        self.assertIn("ARTÍCULO 72",row[27])
        self.assertIn("PLANOS",row[28])
        self.assertEqual(json.loads(row[29])["presencia"],"indeterminada")
        self.assertEqual(len(row),32)
        self.assertEqual(self.sheet.v.docs[1][13],result.cache.clave)
        self.assertEqual(len(self.sheet.v.contracts),1)

    def test_cached_reuses_without_gemini(self):
        self.assertFalse(self.extract().cached)
        self.assertTrue(self.extract().cached)
        self.assertEqual(self.calls,1)
        self.assertEqual(len(self.sheet.v.orden),2)

    def test_failed_request_blocks_repeat(self):
        def fail(*args,**kwargs):
            self.calls+=1
            raise RuntimeError("simulated")
        with self.assertRaises(ExtractionStateError):
            self.extract(invoke=fail)
        self.assertEqual(self.sheet.v.ex[1][1],"REQUIERE_REVISION")
        with self.assertRaises(ExtractionStateError):
            self.extract()
        self.assertEqual(self.calls,1)

    def test_wrong_document_no_request(self):
        with self.assertRaises(ExtractionStateError):
            self.extract(doc=DocumentRecord(
                id=DOC,name="NOTIFICACION_AD.pdf",md5_checksum="abc"
            ))
        self.assertEqual(self.calls,0)
        self.assertEqual(self.sheet.v.writes,0)

    def test_bad_header_type_and_md5_blocked(self):
        self.sheet.v.orden[0][0]="bad"
        with self.assertRaises(ExtractionStateError):
            self.extract()
        self.sheet.v.orden[0][0]="cache_key"
        self.sheet.v.docs[1][3]="PUC"
        with self.assertRaises(ExtractionStateError):
            self.extract()
        self.sheet.v.docs[1][3]="ORDEN_AD"
        self.sheet.v.docs[1][5]="different"
        with self.assertRaises(ExtractionStateError):
            self.extract()
        self.assertEqual(self.calls,0)


if __name__=="__main__":
    unittest.main()
