"""Regresión de normalización visual: no alterar evidencia ni adivinar impuestos."""
from __future__ import annotations

from dataclasses import replace
import unittest

from services.contract_display import (
    financial_cells, normalize_contract_type, normalize_award_method, short_date,
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

    def test_amount_with_iva_and_default_supposition(self):
        record = make_record()
        financial = financial_cells(record, "$1,234,567.89 IVA incluido")
        self.assertEqual(financial["Monto del contrato con IVA"], "$1,234,567.89 MXN")
        self.assertEqual(financial["Monto del contrato sin IVA"], "$1,064,282.66 MXN")
        self.assertEqual(financial["IVA utilizado en el cálculo"], "16% (supuesto; verificar)")

    def test_amount_without_iva_and_calculated_opposite(self):
        record = make_record()
        financial = financial_cells(record, "$1,000.00 SIN IVA")
        self.assertEqual(financial["Monto del contrato sin IVA"], "$1,000.00 MXN")
        self.assertEqual(financial["Monto del contrato con IVA"], "$1,160.00 MXN")

    def test_explicit_eight_percent_rate(self):
        financial = financial_cells(make_record(), "$1,080.00 CON IVA DEL 8%")
        self.assertEqual(financial["Monto del contrato con IVA"], "$1,080.00 MXN")
        self.assertEqual(financial["Monto del contrato sin IVA"], "$1,000.00 MXN")
        self.assertEqual(financial["IVA utilizado en el cálculo"], "8% (documentado)")

    def test_without_basis_does_not_invent_iva(self):
        source = make_record()
        record = replace(source, evidence={})
        financial = financial_cells(record, "$1,234,567.89")
        self.assertEqual(financial["Monto del contrato (IVA no indicado)"], "$1,234,567.89 MXN")
        self.assertEqual(financial["Monto del contrato con IVA"], "—")
        self.assertEqual(financial["Monto del contrato sin IVA"], "—")
        self.assertEqual(financial["IVA utilizado en el cálculo"], "—")

    def test_nearby_evidence_must_cite_same_amount(self):
        source = make_record()
        record = replace(source, evidence={
            "monto_contrato": {"evidencia": "$999,999.99 IVA incluido"},
        })
        value = financial_cells(record, "$2,000.00")
        self.assertEqual(value["Monto del contrato (IVA no indicado)"], "$2,000.00 MXN")
        record = replace(source, evidence={
            "monto_contrato": {"evidencia": "El importe total de $2,000.00 incluye IVA"},
        })
        value = financial_cells(record, "$2,000.00")
        self.assertEqual(value["Monto del contrato con IVA"], "$2,000.00 MXN")
        self.assertEqual(value["Monto del contrato sin IVA"], "$1,724.14 MXN")

    def test_vat_conflict_does_not_generate_calculated_amount(self):
        record = make_record()
        financial = financial_cells(record, "$1,160.00 IVA 8% y IVA 16% incluido")
        self.assertEqual(financial["Monto del contrato sin IVA"], "—")
        self.assertEqual(financial["Monto del contrato con IVA"], "—")

    def test_old_schema_uses_explicit_taxed_field_without_touching_source(self):
        record = make_record(modern=False)
        record = replace(record, values={**record.values, "monto_con_iva": "$1,160.00"})
        financial = financial_cells(record, "$1,160.00")
        self.assertEqual(financial["Monto del contrato con IVA"], "$1,160.00 MXN")
        self.assertEqual(financial["Monto del contrato sin IVA"], "$1,000.00 MXN")


if __name__ == "__main__":
    unittest.main()
