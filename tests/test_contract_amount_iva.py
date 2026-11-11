"""Regresión del IVA del importe contractual y su evidencia, sin Gemini."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import unittest

from services.amount_iva import (
    identify_contract_amount_iva, identify_record_iva,
)
from services.award_limits import evaluate, infer_iva, money
from services.contract_portfolio import parse_amount
from services.contract_prompt import PROMPT_CONTRATO, PROMPT_VERSION
from tests.test_award_limits import contract, fixture_catalog


AMOUNT = "$1,542,830.55"
CLAUSE = (
    'TERCERA. - MONTO DEL CONTRATO. "LA CONTRATANTE" se obliga a cubrir '
    'a "EL CONTRATISTA" la cantidad de: $1,542,830.55 '
    '(UN MILLON QUINIENTOS CUARENTA Y DOS MIL OCHOCIENTOS TREINTA PESOS '
    '55/100 M.N.) IVA INCLUIDO, cantidad que se fija como importe total.'
)


class ContractAmountIvaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = __import__(
            "services.award_limits", fromlist=["parse_catalog"]
        ).parse_catalog(fixture_catalog())

    def _contract_with_clause(self, evidence=CLAUSE, amount=AMOUNT):
        original = contract(monto_contrato=amount)
        return replace(
            original, evidence={
                **original.evidence,
                "monto_contrato": {
                    "valor": amount, "pagina": 3, "evidencia": evidence,
                },
            },
        )

    def test_user_image_case_detects_iva_from_clause(self):
        status = identify_contract_amount_iva(
            AMOUNT, evidence=CLAUSE, page=3
        )
        self.assertEqual(status.basis, "Con IVA (16%)")
        self.assertEqual(status.source, "Evidencia de la cláusula del monto")
        self.assertEqual(status.page, 3)
        self.assertIn("IVA INCLUIDO", status.quote)
        self.assertEqual(parse_amount(AMOUNT), Decimal("1542830.55"))

        record = self._contract_with_clause()
        result = evaluate(record, self.catalog)
        self.assertEqual(result.iva, "Con IVA (16%)")
        self.assertEqual(result.net, Decimal("1330026.34"))
        self.assertEqual(result.state, "Dentro del límite")
        self.assertEqual(result.regime, "Municipal")
        self.assertEqual(result.row.key, "2025|LEON")

    def test_amount_value_with_full_clause_and_centavos_in_words(self):
        value = "$1,542,830.55 (UN MILLÓN ... PESOS 55/100 M.N.) IVA INCLUIDO"
        self.assertEqual(parse_amount(value), Decimal("1542830.55"))
        self.assertEqual(infer_iva(value), "Con IVA (16%)")

    def test_spelled_out_i_v_a_included(self):
        for literal in (
            "$1,542,830.55 I.V.A. INCLUIDO",
            "$1,542,830.55 IVA incluido",
            "$1,542,830.55 CON IVA",
            "$1,542,830.55 Incluye el impuesto al valor agregado",
        ):
            with self.subTest(literal=literal):
                self.assertEqual(
                    identify_contract_amount_iva(literal).basis,
                    "Con IVA (16%)",
                )

    def test_iva_excluded_phrases(self):
        for literal in (
            "$1,542,830.55 SIN IVA",
            "$1,542,830.55 más I.V.A.",
            "$1,542,830.55 IVA NO INCLUIDO",
            "$1,542,830.55 no incluye IVA",
        ):
            with self.subTest(literal=literal):
                self.assertEqual(
                    identify_contract_amount_iva(literal).basis, "Sin IVA"
                )

    def test_evidence_quote_without_same_amount_is_not_reliable(self):
        status = identify_contract_amount_iva(
            AMOUNT, evidence="$3,000,000.00 IVA INCLUIDO", page=5,
        )
        self.assertEqual(status.basis, "Por confirmar")
        self.assertEqual(status.source, "No acreditado")

    def test_evidence_only_mentions_iva_does_not_infer(self):
        self.assertEqual(
            identify_contract_amount_iva(
                AMOUNT,
                evidence="$1,542,830.55. Se causará IVA al 16%.",
            ).basis,
            "Por confirmar",
        )

    def test_mixed_or_opposing_taxes_require_review(self):
        status = identify_contract_amount_iva(
            AMOUNT + " SIN IVA", evidence=CLAUSE, page=3
        )
        self.assertEqual(status.basis, "Por confirmar")
        self.assertIn("contradictorias", status.source)
        self.assertEqual(
            evaluate(self._contract_with_clause(amount=AMOUNT + " SIN IVA"),
                     self.catalog).state,
            "Requiere revisión",
        )

    def test_quote_may_have_other_numbers_if_exact_total_present(self):
        text = (
            "$1,542,830.55 (UN MILLÓN ... 55/100 M.N.) IVA INCLUIDO. "
            "El anticipo será 30%."
        )
        result = identify_contract_amount_iva(AMOUNT,evidence=text)
        self.assertEqual(result.basis, "Con IVA (16%)")

    def test_old_saved_contract_can_be_evaluated_from_existing_quote(self):
        record = self._contract_with_clause()
        result = identify_record_iva(record)
        self.assertEqual(result.basis,"Con IVA (16%)")
        self.assertEqual(result.page,3)
        no_evidence = replace(record,evidence={})
        self.assertEqual(identify_record_iva(no_evidence).basis,"Por confirmar")

    def test_prompt_version_and_no_extra_column_or_schema(self):
        from services.contract_v2 import CONTRACT_SCHEMA_V2, CONTRACT_V2_FIELDS
        self.assertEqual(PROMPT_VERSION,"contrato-prompt-v5")
        self.assertEqual(CONTRACT_SCHEMA_V2,"contrato-v2")
        self.assertEqual(len(CONTRACT_V2_FIELDS),16)
        self.assertIn("monto_contrato",PROMPT_CONTRATO)
        self.assertIn("A LA VEZ el mismo importe total y la frase sobre el IVA",
                      PROMPT_CONTRATO)
        self.assertIn("No recortes solo la cantidad",PROMPT_CONTRATO)
        self.assertIn("NO inventes",PROMPT_CONTRATO)
        self.assertTrue(money(Decimal("1330026.34")),"$1,330,026.34")


if __name__ == "__main__":
    unittest.main()
