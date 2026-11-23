"""Regresiones del historial PUC y de la prueba AD-03, sin APIs externas."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from unittest.mock import Mock, patch
import unittest

from services.puc_history import (
    PucHistoryError, make_puc_review, latest_puc_review,
    read_puc_reviews, save_puc_review,
)
from services.puc_validity import evaluate_puc_validity
from services.capital_contable import CapitalSources
from tests.test_capital_contable import _contract, _puc, _sources, WORK, DOC, KEY


def _review(**extra):
    c = _contract()
    fields = dict(
        obra_id=WORK,
        contrato_documento_id=c.documento_id,
        contrato_cache_key=c.cache_key,
        puc_documento_id=DOC, puc_cache_key=KEY,
        auditor="auditor@aseg.example",
        fecha_asignacion="10/12/2025",
        vigencia_desde="01/01/2025", vigencia_hasta="31/12/2025",
        fuente="Constancia histórica certificada",
        referencia="Oficio PUC 123/2025, foja 3",
        observaciones="Cotejo de registro vigente al adjudicar.",
        conclusion_capital="Pendiente", conclusion_vigencia="Pendiente",
    )
    fields.update(extra)
    return make_puc_review(**fields)


class PucHistoryTests(unittest.TestCase):
    def test_review_required_fields_and_dates(self):
        with self.assertRaisesRegex(PucHistoryError, "ambas fechas"):
            _review(vigencia_desde="")
        with self.assertRaisesRegex(PucHistoryError, "posterior al vencimiento"):
            _review(vigencia_desde="01/01/2026")
        with self.assertRaisesRegex(PucHistoryError, "fecha de registro"):
            _review(capital_historico="200000.00", fecha_registro_capital="")
        with self.assertRaisesRegex(PucHistoryError, "fuente"):
            _review(fuente="")
        with self.assertRaisesRegex(PucHistoryError, "fecha revisada"):
            _review(fecha_asignacion="31/02/2025")

    def test_review_exact_contract_and_puc_versions_only(self):
        c = _contract()
        current = _puc()
        event = _review()
        self.assertEqual(latest_puc_review([event], c, current), event)
        self.assertIsNone(
            latest_puc_review([event], replace(c, cache_key="changed"), current)
        )
        self.assertIsNone(
            latest_puc_review([event], c, replace(current, cache_key="changed"))
        )

    def test_read_history_missing_tab_does_not_create_it(self):
        client = Mock()
        client.spreadsheets.return_value.get.return_value.execute.return_value = {
            "sheets": [{"properties": {"title": "DatosPUC"}}],
        }
        self.assertEqual(read_puc_reviews(client, "master"), [])
        client.spreadsheets.return_value.batchUpdate.assert_not_called()

    @patch("services.capital_contable.read_capital_sources")
    @patch("services.puc_history.read_contract_portfolio")
    def test_save_appends_only_after_versions_verified(self, portfolio, sources):
        client = Mock()
        client.spreadsheets.return_value.get.return_value.execute.return_value = {
            "sheets": [{"properties": {"title": "DatosPUC"}}],
        }
        portfolio.return_value = Mock(records=(_contract(),))
        sources.return_value = _sources(_puc())
        client.spreadsheets.return_value.values.return_value.append.return_value.execute.return_value = {
            "updates": {"updatedRows": 1},
        }
        event = _review()
        self.assertEqual(save_puc_review(client, "master", event), event.revision_id)
        client.spreadsheets.return_value.batchUpdate.assert_called_once()
        client.spreadsheets.return_value.values.return_value.append.assert_called_once()

        with self.assertRaisesRegex(PucHistoryError, "sustituidos"):
            save_puc_review(client, "master", replace(event, contrato_cache_key="old"))


class PucValidityTests(unittest.TestCase):
    def test_explicit_interval_uses_signature_only(self):
        puc = _puc(
            vigencia_desde="01 de enero de 2025",
            vigencia_hasta="31 de diciembre de 2025",
            fecha_impresion="18 de diciembre de 2025",
        )
        result = evaluate_puc_validity(_contract(), _sources(puc), _review())
        self.assertEqual(result.state, "Vigente en fecha de firma")
        self.assertFalse(result.inferred_start)
        self.assertEqual(result.signature_date, "15/12/2025")
        self.assertEqual(result.period_from, "01/01/2025")
        self.assertEqual(result.period_to, "31/12/2025")

    def test_does_not_depend_on_assignment_or_dictamen(self):
        puc = _puc(vigencia_desde="01/01/2025", vigencia_hasta="31/12/2025")
        result = evaluate_puc_validity(_contract(), _sources(puc, date=""))
        self.assertEqual(result.state, "Vigente en fecha de firma")

    def test_missing_start_infers_exactly_one_calendar_year(self):
        # Ejemplo solicitado: vencimiento 15/06/2025 -> inicio 15/06/2024.
        puc = _puc(vigencia_desde="", vigencia_hasta="15/06/2025")
        contract = _contract(fecha_firma_contrato="14/06/2025")
        result = evaluate_puc_validity(contract, _sources(puc, date=""))
        self.assertEqual(result.state, "Vigente en fecha de firma")
        self.assertTrue(result.inferred_start)
        self.assertEqual(result.period_from, "15/06/2024")
        self.assertEqual(result.period_to, "15/06/2025")
        self.assertIn("calculado", result.period_source)
        # Sin escribir la fecha deducida en la extracción original.
        self.assertEqual(puc.vigencia_desde, "")

    def test_inclusive_first_and_last_day(self):
        puc = _puc(vigencia_desde="", vigencia_hasta="15/06/2025")
        for signed in ("15/06/2024", "15/06/2025"):
            with self.subTest(firma=signed):
                result = evaluate_puc_validity(
                    _contract(fecha_firma_contrato=signed), _sources(puc)
                )
                self.assertEqual(result.state, "Vigente en fecha de firma")

    def test_signing_outside_annual_period(self):
        puc = _puc(vigencia_desde="", vigencia_hasta="15/06/2025")
        for signed in ("14/06/2024", "16/06/2025"):
            with self.subTest(firma=signed):
                result = evaluate_puc_validity(
                    _contract(fecha_firma_contrato=signed), _sources(puc)
                )
                self.assertEqual(
                    result.state, "Fuera del periodo PUC en fecha de firma"
                )
                self.assertTrue(any("refrendo" in n for n in result.notes))

    def test_explicit_beginning_has_priority_over_derived_one(self):
        puc = _puc(vigencia_desde="01/01/2025", vigencia_hasta="15/06/2025")
        result = evaluate_puc_validity(
            _contract(fecha_firma_contrato="15/06/2024"), _sources(puc)
        )
        self.assertFalse(result.inferred_start)
        self.assertEqual(result.period_from, "01/01/2025")
        self.assertEqual(
            result.state, "Fuera del periodo PUC en fecha de firma"
        )

    def test_manual_historical_period_still_supported(self):
        event = _review(vigencia_desde="22/12/2025", vigencia_hasta="22/12/2026")
        result = evaluate_puc_validity(_contract(), _sources(_puc()), event)
        self.assertEqual(
            result.state, "Fuera del periodo PUC en fecha de firma"
        )
        self.assertFalse(result.inferred_start)
        self.assertEqual(result.period_from, "22/12/2025")

    def test_leap_day_expiry_falls_back_to_february_28(self):
        puc = _puc(vigencia_desde="", vigencia_hasta="29/02/2024")
        result = evaluate_puc_validity(
            _contract(fecha_firma_contrato="28/02/2023"), _sources(puc)
        )
        self.assertEqual(result.period_from, "28/02/2023")
        self.assertEqual(result.state, "Vigente en fecha de firma")

    def test_missing_expiration_is_pending(self):
        result = evaluate_puc_validity(
            _contract(), _sources(_puc(vigencia_desde="", vigencia_hasta=""))
        )
        self.assertEqual(result.state, "Pendiente de vigencia del PUC")

    def test_missing_signature_is_pending(self):
        result = evaluate_puc_validity(
            _contract(fecha_firma_contrato=""),
            _sources(_puc(vigencia_desde="", vigencia_hasta="31/12/2025")),
        )
        self.assertEqual(result.state, "Pendiente de fecha de firma")

    def test_suspended_current_cedula_requires_status_review(self):
        result = evaluate_puc_validity(
            _contract(), _sources(_puc(estado_registro="SUSPENDIDO"))
        )
        self.assertEqual(result.state, "Requiere revisión del estado del registro")

    def test_missing_puc_and_other_procedures_do_not_claim_failure(self):
        result = evaluate_puc_validity(_contract(), _sources())
        self.assertEqual(result.state, "Pendiente de PUC")
        c = _contract(modalidad_adjudicacion="LICITACIÓN PÚBLICA")
        result = evaluate_puc_validity(c, _sources(_puc()))
        self.assertEqual(result.state, "No aplica al piloto AD")

    def test_foreign_review_not_applied_to_this_version(self):
        altered = replace(_review(), contrato_cache_key="other_version")
        puc = _puc(vigencia_desde="", vigencia_hasta="31/12/2025")
        result = evaluate_puc_validity(_contract(), _sources(puc), altered)
        self.assertEqual(result.state, "Vigente en fecha de firma")
        self.assertEqual(result.period_from, "31/12/2024")
        self.assertTrue(any("otra versión" in n for n in result.notes))


if __name__ == "__main__":
    unittest.main()
