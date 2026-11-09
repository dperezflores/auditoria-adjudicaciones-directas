"""Regresión de normalización visual sin recalcular el importe contractual."""
from __future__ import annotations

import unittest

from services.contract_display import (
    format_contract_amount, normalize_contract_type, normalize_award_method, short_date,
)
from test_contract_table import make_record


class ContractDisplayTests(unittest.TestCase):
    def test_contract_type(self):
        cases = {
            "A base de precios unitarios por tiempo determinado": "Precios Unitarios",
            "CONTRATO A PRECIOS UNITARIOS Y TIEMPO DETERMINADO": "Precios Unitarios",
            "CONTRATO A PRECIO ALZADO Y TIEMPO DETERMINADO": "Precio Alzado",
            "POR PRECIOS UNITARIOS Y A PRECIO ALZADO": "Mixto (precios unitarios y precio alzado)",
            "sin identificar": "—",
            "": "—",
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(normalize_contract_type(source), expected)

    def test_award_method(self):
        cases = {
            "en la modalidad de adjudicación directa conforme al artículo X": "ADJUDICACIÓN DIRECTA",
            "ADJUDICACIÓN DIRECTA.": "ADJUDICACIÓN DIRECTA",
            "LICITACIÓN SIMPLIFICADA NACIONAL": "LICITACIÓN SIMPLIFICADA",
            "licitación pública simplificada, conforme a las bases": "LICITACIÓN SIMPLIFICADA",
            "Licitación Pública Nacional No. 123": "LICITACIÓN PÚBLICA",
            "procedimiento de invitación restringida": "INVITACIÓN RESTRINGIDA",
            "invitación a cuando menos tres personas": "INVITACIÓN RESTRINGIDA",
            "concurso simplificado": "CONCURSO SIMPLIFICADO",
            "licitación pública o adjudicación directa": "—",
            "": "—",
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(normalize_award_method(source), expected)

    def test_short_date_and_unverifiable(self):
        cases = {
            "02 de junio de 2025": "02/06/2025",
            "05 días del mes de Mayo del año de 2025": "05/05/2025",
            "30 de SEPTIEMBRE del 2026": "30/09/2026",
            "4 de Mayo del año 2026": "04/05/2026",
            "2026-11-08": "08/11/2026",
            "08/11/2026": "08/11/2026",
            "31 de febrero de 2026": "31 de febrero de 2026",
            "Fecha de inicio sujeta a notificación": "Fecha de inicio sujeta a notificación",
            "02/06/2026 y 03/06/2026": "02/06/2026 y 03/06/2026",
            "": "—",
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(short_date(source), expected)

    def test_amount_from_contract_is_only_formatted_not_calculated(self):
        raw = "$1,234,567.89 (I.V.A. incluido)"
        self.assertEqual(format_contract_amount(raw, "MXN"), "$1,234,567.89")
        self.assertEqual(format_contract_amount("$1,000.00 SIN IVA", "MXN"), "$1,000.00")
        self.assertEqual(format_contract_amount("$1.234.567,89", "MXN"), "$1,234,567.89")
        self.assertEqual(format_contract_amount("$1,230", ""), "$1,230.00")

    def test_other_currency_retains_clear_currency_marker(self):
        self.assertEqual(format_contract_amount("USD 2,500.00", "USD"), "US$2,500.00")
        self.assertEqual(format_contract_amount("EUR 1.234,50", "EUR"), "€1,234.50")

    def test_amount_with_multiple_different_numbers_is_not_guessed(self):
        self.assertEqual(format_contract_amount("$1,000.00 y $2,000.00", "MXN"), "—")
        self.assertEqual(format_contract_amount("Monto sin identificar", "MXN"), "—")
        self.assertEqual(format_contract_amount("", "MXN"), "—")

    def test_original_value_remains_in_record(self):
        record = make_record()
        self.assertEqual(
            record.full_values["monto_contrato"],
            "$1,234,567.89 (I.V.A. incluido)",
        )
        self.assertEqual(
            format_contract_amount(record.full_values["monto_contrato"], record.currency),
            "$1,234,567.89",
        )


if __name__ == "__main__":
    unittest.main()
