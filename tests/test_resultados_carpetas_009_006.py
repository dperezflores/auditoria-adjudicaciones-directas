"""Regresiones de dos extracciones v8 reales en carpetas 009 y 006.

No se altera Sheets: se prueban los valores literales de la extracción
y la forma de presentarlos en la tabla de Resultados.
"""
from __future__ import annotations

from dataclasses import replace
import unittest

from services.contract_display import short_date
from services.contract_role_rules import authorized_legal_role
from services.contract_table import contract_table_rows
from tests.test_contract_table import make_record


LEGAL_009 = "ING. HORACIO GONZALEZ GUTIERREZ"
EVIDENCE_009 = (
    "b) Que tiene capacidad jurídica para suscribir el presente contrato "
    "y que el ING. HORACIO GONZALEZ GUTIERREZ está facultado para "
    "representarla legalmente en este acto, acreditando su personalidad "
    "como ADMINISTRADOR ÚNICO"
)
DATE_006 = "27 des del mes de Abril del año de 2024"
DATE_QUOTE_006 = "y terminación el día 27 des del mes de Abril del año de 2024"


class ResultsRealCasesTests(unittest.TestCase):
    def test_009_legal_rep_is_not_hidden_in_normalized_results(self):
        record = make_record()
        full = dict(record.full_values)
        full.update({
            "representante_legal": LEGAL_009,
            "contratista": "E.M.S. Y CONTROL DE CALIDAD PARA LA CONSTRUCCION, S.A. DE C.V.",
        })
        updated = replace(record, nombre_carpeta="009", full_values=full, evidence={
            "representante_legal": {
                "valor": LEGAL_009,
                "pagina": 2,
                "evidencia": EVIDENCE_009,
            },
        }, extraction_prompt="contrato-prompt-v8")
        self.assertTrue(authorized_legal_role(LEGAL_009, EVIDENCE_009))
        row = contract_table_rows((updated,))[0]
        self.assertEqual(row["Carpeta"], "009")
        self.assertEqual(row["Representante legal"], LEGAL_009)
        self.assertEqual(updated.full_values["representante_legal"], LEGAL_009)
        self.assertEqual(updated.evidence["representante_legal"]["evidencia"], EVIDENCE_009)

    def test_role_not_inferred_from_signature_without_legal_clause(self):
        self.assertFalse(authorized_legal_role(
            LEGAL_009, "FIRMA: ING. HORACIO GONZALEZ GUTIERREZ"
        ))
        self.assertFalse(authorized_legal_role(
            "ING. HORACIO GONZALEZ GUTIERREZ",
            "OTRA PERSONA está facultada para representarla legalmente.",
        ))

    def test_006_end_date_normalized_without_altering_literal(self):
        record = make_record()
        full = dict(record.full_values)
        full["fecha_termino_contractual"] = DATE_006
        updated = replace(record, nombre_carpeta="006", full_values=full, evidence={
            "fecha_termino_contractual": {
                "valor": DATE_006, "pagina": 2, "evidencia": DATE_QUOTE_006,
            },
        }, extraction_prompt="contrato-prompt-v8")
        row = contract_table_rows((updated,))[0]
        self.assertEqual(row["Carpeta"], "006")
        self.assertEqual(row["Fecha de término contractual"], "27/04/2024")
        self.assertIn("expresión anómala", row["Observaciones de extracción"])
        self.assertIn("cotejar el PDF original", row["Observaciones de extracción"])
        self.assertEqual(updated.full_values["fecha_termino_contractual"], DATE_006)
        self.assertEqual(updated.evidence["fecha_termino_contractual"]["evidencia"], DATE_QUOTE_006)

    def test_date_parser_keeps_other_formats_and_invalid_dates_safe(self):
        self.assertEqual(short_date("27 de abril del año de 2024"),"27/04/2024")
        self.assertEqual(short_date("27 del mes de Abril del año de 2024"),"27/04/2024")
        self.assertEqual(short_date("04 días del mes de Marzo del año de 2024"),"04/03/2024")
        self.assertEqual(short_date("27 des del mes de Abril del año de 2024"),"27/04/2024")
        self.assertEqual(
            short_date("31 des del mes de Abril del año de 2024"),
            "31 des del mes de Abril del año de 2024",
        )


if __name__ == "__main__":
    unittest.main()
