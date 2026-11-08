"""Pruebas del dashboard registrado: sin Google, sin IA y sin escrituras."""
from __future__ import annotations

import unittest

from services.dashboard_service import (
    DashboardDataError, prepare_dashboard, read_dashboard,
)
from services.sync_engine import HEADERS
from services.extraction_store import EXTRACTION_HEADERS, CONTRACT_HEADERS

OBRA1 = "folderObra001ABCDE"
OBRA2 = "folderObra002ABCDE"
DOC1 = "documento001ABCDE"
KEY_V1 = "cacheAnterior001"
KEY_V3 = "cacheActual003"


def fixture():
    works = [list(HEADERS["Obras"])]
    works.extend([
        [OBRA1, "Obra 001 - Prueba ficticia", "Pendiente", "1", "1", "0", "2026", "SI", "3"],
        [OBRA2, "Obra 002 - Prueba ficticia", "Sin PDF", "0", "0", "0", "2026", "SI", "1"],
    ])
    docs = [list(HEADERS["Documentos"])]
    docs.append([
        DOC1, OBRA1, "Contrato_SIMULADO.pdf", "", "application/pdf",
        "md5", "2026-11-08", "302268", "Requiere validación", "2026",
        "2026", "SI", "gemini:contrato-prompt-v3", KEY_V3, "", "4",
    ])
    extracts = [list(EXTRACTION_HEADERS)]
    extracts.append([
        KEY_V1, "REQUIERE_REVISION", DOC1, OBRA1, "sha1", "gemini",
        "contrato-prompt-v1", "contrato-v1", "2026", "2026", "",
        "", "", "HTTP_400_INVALID_ARGUMENT",
    ])
    extracts.append([
        KEY_V3, "REQUIERE_REVISION", DOC1, OBRA1, "sha3", "gemini",
        "contrato-prompt-v3", "contrato-v1", "2026", "2026", "",
        "", "", "ExtractionStateError",
    ])
    contracts = [list(CONTRACT_HEADERS)]
    contracts.append([
        KEY_V3, OBRA1, DOC1, "SIM-AD-001/2026",
        "Obra simulada", "Constructora ficticia", "30 de octubre",
        "03 de noviembre", "18 de diciembre", "$1,160,000.00",
        "", "porcentaje_anticipo", "2026",
    ])
    return {
        "Obras": works,
        "Documentos": docs,
        "Extracciones": extracts,
        "DatosContrato": contracts,
    }


class DashboardDataTests(unittest.TestCase):
    def test_partial_extraction_is_visible_but_never_validated(self):
        result = prepare_dashboard(fixture())
        self.assertEqual(len(result.obras), 2)
        self.assertEqual(result.pdf_activos, 1)
        self.assertEqual(result.contratos_con_datos, 1)
        self.assertEqual(result.contratos_pendientes_cotejo, 1)
        self.assertIn("pendiente de cotejo", result.contratos[0].estado)
        self.assertIn("evidencias", result.contratos[0].detalle)
        self.assertEqual(result.contratos[0].datos["numero_contrato"], "SIM-AD-001/2026")
        self.assertEqual(result.contratos[0].datos["porcentaje_anticipo"], "")

    def test_historic_result_not_used_as_current(self):
        data = fixture()
        data["Documentos"][1][13] = KEY_V1
        result = prepare_dashboard(data)
        self.assertEqual(result.contratos_con_datos, 0)

    def test_modified_pdf_hides_stale_extraction(self):
        data = fixture()
        data["Documentos"][1][8] = "Modificado desde el último análisis"
        result = prepare_dashboard(data)
        self.assertEqual(result.contratos_con_datos, 0)

    def test_inactive_pdf_hides_extraction(self):
        data = fixture()
        data["Documentos"][1][11] = "NO"
        result = prepare_dashboard(data)
        self.assertEqual(result.pdf_activos, 0)
        self.assertEqual(result.contratos_con_datos, 0)

    def test_inactive_work_excluded(self):
        data = fixture()
        data["Obras"][1][7] = "NO"
        result = prepare_dashboard(data)
        self.assertEqual(len(result.obras), 1)
        self.assertEqual(result.contratos_con_datos, 0)

    def test_no_value_does_not_count_as_extracted(self):
        data = fixture()
        data["DatosContrato"][1][3:11] = [""] * 8
        self.assertEqual(prepare_dashboard(data).contratos_con_datos, 0)

    def test_duplicate_contract_rejected(self):
        data = fixture()
        data["DatosContrato"].append(data["DatosContrato"][1].copy())
        with self.assertRaises(DashboardDataError):
            prepare_dashboard(data)

    def test_mismatched_headers_rejected(self):
        data = fixture()
        data["DatosContrato"][0][3] = "valor_incorrecto"
        with self.assertRaises(DashboardDataError):
            prepare_dashboard(data)

    def test_complete_extraction_requires_human_cotejo(self):
        data = fixture()
        data["Extracciones"][2][1] = "COMPLETADO"
        result = prepare_dashboard(data)
        self.assertIn("pendiente de cotejo humano", result.contratos[0].estado)
        self.assertEqual(result.contratos_pendientes_cotejo, 1)

    def test_data_contract_wrong_work_rejected(self):
        data = fixture()
        data["DatosContrato"][1][1] = OBRA2
        with self.assertRaises(DashboardDataError):
            prepare_dashboard(data)


class FakeRequest:
    def __init__(self, response):
        self.response = response
    def execute(self):
        return self.response


class ReadOnlyValues:
    def __init__(self):
        self.calls = []
    def batchGet(self, **kwargs):
        self.calls.append(("batchGet", kwargs))
        tables = fixture()
        return FakeRequest({
            "valueRanges": [
                {"values": tables[part.split("'")[1]]}
                for part in kwargs["ranges"]
            ]
        })
    def batchUpdate(self, **kwargs):
        raise AssertionError("El dashboard NUNCA debe escribir en Sheets.")


class FakeSheets:
    def __init__(self):
        self.values_obj = ReadOnlyValues()
    def spreadsheets(self):
        return self
    def values(self):
        return self.values_obj


class DashboardReadTests(unittest.TestCase):
    def test_read_only_and_no_ai(self):
        fake = FakeSheets()
        result = read_dashboard(fake, "sheet-test")
        self.assertEqual(result.contratos_con_datos, 1)
        self.assertEqual(len(fake.values_obj.calls), 1)
        self.assertEqual(fake.values_obj.calls[0][0], "batchGet")


if __name__ == "__main__":
    unittest.main()
