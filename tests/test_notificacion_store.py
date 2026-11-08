"""NOTIFICACION_AD: caché y persistencia segura, sin llamadas reales a Gemini."""
from __future__ import annotations

import json
import unittest

from services.notificacion_gemini import NotificacionGeminiResult
from services.notificacion_schema import NOTIFICACION_HEADERS, NOTIFICACION_SCHEMA_VERSION, parse_notificacion
from services.notificacion_store import extract_or_reuse_notificacion
from services.drive_service import DocumentRecord
from services.extraction_store import (
    EXTRACTION_HEADERS, DOCUMENT_HEADERS, CONTRACT_HEADERS, ExtractionStateError,
)
from tests.test_notificacion_schema import sample_notificacion

DOC = "notificacionFileTest01"
WORK = "obraTestNotif001"
PDF = b"%PDF-1.5 simulated notification"
MODEL = "gemini-test"


class Request:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


class Values:
    def __init__(self):
        self.ex = [list(EXTRACTION_HEADERS)]
        self.contracts = [list(CONTRACT_HEADERS)]
        self.notificacion = [list(NOTIFICACION_HEADERS)]
        self.docs = [list(DOCUMENT_HEADERS), [
            DOC, WORK, "NOTIFICACION_AD.pdf", "NOTIFICACION_AD",
            "application/pdf", "abc123", "2026", "1000", "Pendiente",
            "2026", "2026", "SI", "", "", "", "1",
        ]]
        self.writes = 0

    def batchGet(self, **kwargs):
        return Request({"valueRanges": [
            {"values": self.ex}, {"values": self.contracts},
            {"values": self.docs},
        ]})

    def get(self, **kwargs):
        if "DatosNotificacionAD" not in kwargs["range"]:
            raise AssertionError("Lectura de una pestaña no autorizada")
        return Request({"values": self.notificacion})

    def batchUpdate(self, **kwargs):
        data = kwargs["body"]["data"]
        self.writes += 1
        for item in data:
            rg = item["range"]
            value = item["values"][0]
            if rg.startswith("'Extracciones'!"):
                if len(self.ex) == 1:
                    self.ex.append([""] * len(EXTRACTION_HEADERS))
                self.ex[1] = list(value)
            elif rg.startswith("'DatosNotificacionAD'!"):
                if len(self.notificacion) == 1:
                    self.notificacion.append([""] * len(NOTIFICACION_HEADERS))
                self.notificacion[1] = list(value)
            elif rg.startswith("'Documentos'!I2"):
                self.docs[1][8] = value[0]
            elif rg.startswith("'Documentos'!M2"):
                self.docs[1][12:15] = value
            else:
                raise AssertionError("Escritura a otra pestaña: " + rg)
        return Request({"responses": [{"updatedRows": 1} for _ in data]})


class Sheets:
    def __init__(self):
        self.v = Values()

    def spreadsheets(self):
        return self

    def values(self):
        return self.v


class NotificacionStoreTests(unittest.TestCase):
    def setUp(self):
        self.sheets = Sheets()
        self.doc = DocumentRecord(
            id=DOC, name="NOTIFICACION_AD.pdf", md5_checksum="abc123",
        )
        self.calls = 0

    def do_extract(self, doc=None, invoke=None):
        if invoke is None:
            def invoke(pdf, api, *, model):
                self.calls += 1
                return NotificacionGeminiResult(
                    parse_notificacion(sample_notificacion()), 180, 95,
                )
        return extract_or_reuse_notificacion(
            self.sheets, "spreadsheet", PDF, doc or self.doc, WORK,
            "dummy-key", model=MODEL, invoke=invoke,
        )

    def test_persists_notifications_without_touching_contract_tables(self):
        response = self.do_extract()
        self.assertFalse(response.cached)
        self.assertEqual(self.calls, 1)
        self.assertEqual(self.sheets.v.ex[1][7], NOTIFICACION_SCHEMA_VERSION)
        self.assertEqual(self.sheets.v.ex[1][1], "COMPLETADO")
        self.assertEqual(self.sheets.v.notificacion[1][3], "DGOP/586/CONT/2025")
        self.assertEqual(self.sheets.v.notificacion[1][4], "03 DE DICIEMBRE DE 2025")
        self.assertEqual(self.sheets.v.notificacion[1][5], "")
        self.assertIn("GTO-SOP/PUC-4044-2017", self.sheets.v.notificacion[1][24])
        self.assertIn("cinco días hábiles", self.sheets.v.notificacion[1][25])
        self.assertEqual(json.loads(self.sheets.v.notificacion[1][27])["presencia"], "indeterminada")
        self.assertEqual(len(self.sheets.v.notificacion[1]), 30)
        self.assertEqual(len(self.sheets.v.contracts), 1)
        self.assertEqual(self.sheets.v.docs[1][13], response.cache.clave)

    def test_existing_cache_reuses_without_second_call(self):
        self.assertFalse(self.do_extract().cached)
        self.assertTrue(self.do_extract().cached)
        self.assertEqual(self.calls, 1)
        self.assertEqual(len(self.sheets.v.notificacion), 2)

    def test_failed_attempt_is_blocked(self):
        def fail(*args, **kwargs):
            self.calls += 1
            raise RuntimeError("no se puede responder")
        with self.assertRaises(ExtractionStateError):
            self.do_extract(invoke=fail)
        self.assertEqual(self.sheets.v.ex[1][1], "REQUIERE_REVISION")
        with self.assertRaises(ExtractionStateError):
            self.do_extract()
        self.assertEqual(self.calls, 1)

    def test_name_and_mime_mismatch_block_before_gemini(self):
        with self.assertRaises(ExtractionStateError):
            self.do_extract(DocumentRecord(id=DOC, name="DICTAMEN_AD.pdf", md5_checksum="abc123"))
        self.assertEqual(self.calls, 0)
        self.assertEqual(self.sheets.v.writes, 0)

    def test_wrong_registered_id_and_md5_are_blocked(self):
        self.sheets.v.docs[1][3] = "DICTAMEN_AD"
        with self.assertRaises(ExtractionStateError):
            self.do_extract()
        self.sheets.v.docs[1][3] = "NOTIFICACION_AD"
        self.sheets.v.docs[1][5] = "changed"
        with self.assertRaises(ExtractionStateError):
            self.do_extract()
        self.assertEqual(self.calls, 0)

    def test_invalid_header_blocks_before_calls(self):
        self.sheets.v.notificacion[0][24] = "supervision_lista"
        with self.assertRaises(ExtractionStateError):
            self.do_extract()
        self.assertEqual(self.calls, 0)


if __name__ == "__main__":
    unittest.main()
