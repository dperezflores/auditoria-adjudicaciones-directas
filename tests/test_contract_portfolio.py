"""Portafolio contractual: integridad de versiones, agregados y filtros.

Todos los datos son ficticios; pruebas sin acceso a Sheets ni llamadas a IA.
"""
from __future__ import annotations

import json
import unittest
from decimal import Decimal

from services.contract_portfolio import (
    DATA_FIELDS, HEADERS, PortfolioError, amount_summary, currency_group,
    filter_contracts, money_text, parse_amount, prepare_contract_portfolio,
    read_contract_portfolio, signature_year,
)

WORK = "folderJerez001"
DOCUMENT = "contractJerez001"
KEY = "cacheCurrent001"


def dataset():
    works = [list(HEADERS["Obras"]),
             [WORK, "Cerrito de Jerez", "", "1", "0", "0", "", "SI", "1"],
             ["folderInactive", "Obra ficticia", "", "1", "0", "0", "", "NO", "1"]]
    documents = [
        list(HEADERS["Documentos"]),
        [DOCUMENT, WORK, "CONTRATO.pdf", "", "application/pdf",
         "md5real", "", "21000000", "Analizado", "", "", "SI",
         "gemini:contrato-prompt-v3", KEY, "", "1"],
        ["docInactive", "folderInactive", "SIMULADO.pdf", "", "application/pdf",
         "md5fake", "", "2000", "Analizado", "", "", "NO",
         "gemini:contrato-prompt-v3", "cacheFake", "", "1"],
    ]
    values = {
        "numero_contrato": "A-117/2025",
        "nombre_obra": "Rehabilitación de caminos principales",
        "contratista": "CONSTRUCTORA DEL BAJÍO",
        "fecha_firma": "05 días del mes de Mayo del año de 2025",
        "fecha_inicio": "02 de junio de 2025",
        "fecha_termino": "26 de julio de 2025",
        "monto_con_iva": "$2,350,150.88",
        "porcentaje_anticipo": "30%",
    }
    extraction = {
        key: {"valor": value, "pagina": 1, "evidencia": f"Texto de {key}"}
        for key, value in values.items()
    }
    extraction["observaciones"] = []
    analyses = [
        list(HEADERS["Extracciones"]),
        [KEY, "COMPLETADO", DOCUMENT, WORK, "hash", "gemini-3.5-flash-lite",
         "contrato-prompt-v3", "contrato-v1", "", "2026-11-08T06:19:03Z",
         json.dumps(extraction), "12322", "736", ""],
        ["cacheFake", "COMPLETADO", "docInactive", "folderInactive",
         "hash", "gemini-3.5-flash-lite", "contrato-prompt-v3", "contrato-v1",
         "", "", json.dumps(extraction), "0", "0", ""],
    ]
    rows = [
        list(HEADERS["DatosContrato"]),
        [KEY, WORK, DOCUMENT, *[values[field] for field in DATA_FIELDS],
         "", "2026-11-08T06:18:57Z"],
        ["cacheFake", "folderInactive", "docInactive",
         *[values[field] for field in DATA_FIELDS],
         "", "2026-11-08"],
    ]
    return {
        "Obras": works,
        "Documentos": documents,
        "Extracciones": analyses,
        "DatosContrato": rows,
    }


class PortfolioTests(unittest.TestCase):
    def test_works_are_built_from_contracts_not_folders(self):
        portfolio = prepare_contract_portfolio(dataset())
        self.assertEqual(portfolio.works_count, 1)
        self.assertEqual(len(portfolio.records), 1)
        record = portfolio.records[0]
        self.assertEqual(record.values["numero_contrato"], "A-117/2025")
        self.assertEqual(record.signature_year, "2025")
        self.assertEqual(record.coverage, "8/8")
        self.assertEqual(record.evidence["numero_contrato"]["pagina"], 1)
        self.assertEqual(record.amount, Decimal("2350150.88"))

    def test_filter_search_ignores_accents(self):
        portfolio = prepare_contract_portfolio(dataset())
        self.assertEqual(len(filter_contracts(portfolio, query="rehabilitacion")), 1)
        self.assertEqual(len(filter_contracts(portfolio, query="A-117/2025")), 1)
        self.assertEqual(len(filter_contracts(portfolio, query="no existe")), 0)

    def test_filters_year_and_contractor(self):
        portfolio = prepare_contract_portfolio(dataset())
        self.assertEqual(len(filter_contracts(portfolio, year="2025")), 1)
        self.assertEqual(len(filter_contracts(portfolio, year="2024")), 0)
        self.assertEqual(
            len(filter_contracts(portfolio, contractor="CONSTRUCTORA DEL BAJÍO")), 1
        )

    def test_finished_old_version_is_not_counted(self):
        data = dataset()
        data["Documentos"][1][13] = "cacheNew"
        self.assertEqual(len(prepare_contract_portfolio(data).records), 0)

    def test_modified_or_inactive_pdf_excluded(self):
        data = dataset()
        data["Documentos"][1][8] = "Modificado desde el último análisis"
        self.assertEqual(len(prepare_contract_portfolio(data).records), 0)
        data = dataset()
        data["Documentos"][1][11] = "NO"
        self.assertEqual(len(prepare_contract_portfolio(data).records), 0)

    def test_partial_data_visible_as_partial_without_inventing_evidence(self):
        data = dataset()
        data["Extracciones"][1][1] = "REQUIERE_REVISION"
        data["Extracciones"][1][10] = ""
        data["DatosContrato"][1][10] = ""
        portfolio = prepare_contract_portfolio(data)
        self.assertEqual(len(portfolio.records), 1)
        self.assertEqual(portfolio.records[0].status_label, "Recuperación parcial")
        self.assertEqual(portfolio.records[0].completeness, 7)
        self.assertFalse(portfolio.records[0].evidence)

    def test_a_puc_is_not_contract(self):
        data = dataset()
        data["Extracciones"][1][7] = "documento-schema-v1"
        self.assertEqual(len(prepare_contract_portfolio(data).records), 0)

    def test_invalid_headers_fail_without_guessing(self):
        data = dataset()
        data["DatosContrato"][0][3] = "numero_incorrecto"
        with self.assertRaisesRegex(PortfolioError, "Encabezados"):
            prepare_contract_portfolio(data)

    def test_duplicate_current_contract_rejected(self):
        data = dataset()
        data["DatosContrato"].append(data["DatosContrato"][1].copy())
        with self.assertRaisesRegex(PortfolioError, "duplicada"):
            prepare_contract_portfolio(data)

    def test_missing_amount_still_in_list_no_fabricated_total(self):
        data = dataset()
        data["DatosContrato"][1][9] = ""
        portfolio = prepare_contract_portfolio(data)
        self.assertIsNone(portfolio.records[0].amount)
        amount, explanation, missing = amount_summary(portfolio.records)
        self.assertIsNone(amount)
        self.assertEqual(missing, 1)
        self.assertIn("Sin importes", explanation)

    def test_money_parsing_mexican_and_other_format(self):
        self.assertEqual(parse_amount("$2,350,150.88"), Decimal("2350150.88"))
        self.assertEqual(parse_amount("$1.234.567,89"), Decimal("1234567.89"))
        self.assertEqual(parse_amount("$2500"), Decimal("2500"))
        self.assertIsNone(parse_amount("No localizado"))
        self.assertIsNone(parse_amount("$10 y $20"))

    def test_mixed_currencies_are_never_aggregated(self):
        data = dataset()
        data["Obras"].append(["folderOther", "Otra obra", "", "1", "0", "0", "", "SI", "1"])
        data["Documentos"].append([
            "documentOther", "folderOther", "otro.pdf", "", "application/pdf", "md5",
            "", "1000", "Analizado", "", "", "SI", "", "cacheOther", "", "1",
        ])
        old = data["Extracciones"][1].copy()
        old[0], old[2], old[3] = "cacheOther", "documentOther", "folderOther"
        data["Extracciones"].append(old)
        row = data["DatosContrato"][1].copy()
        row[0], row[1], row[2] = "cacheOther", "folderOther", "documentOther"
        row[9] = "USD 2000.00"
        data["DatosContrato"].append(row)
        portfolio = prepare_contract_portfolio(data)
        amount, description, missing = amount_summary(portfolio.records)
        self.assertIsNone(amount)
        self.assertIn("Monedas distintas", description)

    def test_signature_year_does_not_guess(self):
        self.assertEqual(signature_year("05 de mayo de 2025"), "2025")
        self.assertEqual(signature_year("2024 y 2025"), "Sin año")
        self.assertEqual(signature_year("Sin fecha"), "Sin año")
        self.assertEqual(currency_group("MXN $1,000"), "MXN")
        self.assertEqual(money_text(Decimal("2500.00"), "MXN"), "$2,500.00 MXN")


class _Request:
    def __init__(self, payload):
        self.payload = payload
    def execute(self):
        return self.payload


class _Values:
    def __init__(self):
        self.called = False
    def batchGet(self, **kwargs):
        self.called = True
        data = dataset()
        return _Request({
            "valueRanges": [
                {"values": data[name]}
                for name in HEADERS
            ]
        })
    def batchUpdate(self, **kwargs):
        raise AssertionError("El dashboard jamás debe escribir en Google Sheets")


class _Sheets:
    def __init__(self):
        self.value_object = _Values()
    def spreadsheets(self):
        return self
    def values(self):
        return self.value_object


class PortfolioReadTests(unittest.TestCase):
    def test_portfolio_reads_sheet_only(self):
        sheets = _Sheets()
        result = read_contract_portfolio(sheets, "id-sheet")
        self.assertTrue(sheets.value_object.called)
        self.assertEqual(result.works_count, 1)


if __name__ == "__main__":
    unittest.main()
