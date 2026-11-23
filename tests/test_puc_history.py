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
        conclusion_auditor="Pendiente",
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
    def test_historical_interval_covers_assignment_and_signature(self):
        puc = _puc(
            vigencia_desde="01 de enero de 2025",
            vigencia_hasta="31 de diciembre de 2025",
            fecha_impresion="18 de diciembre de 2025",
        )
        result = evaluate_puc_validity(_contract(), _sources(puc), _review())
        self.assertEqual(result.state, "Vigencia documental compatible (preliminar)")
        self.assertEqual(result.assignment_result, "Dentro del periodo aportado")
        self.assertEqual(result.contract_result, "Dentro del periodo aportado")
        self.assertTrue(any("impresión" in n for n in result.notes))

    def test_dictamen_only_is_not_final_assignment_date(self):
        puc = _puc(vigencia_desde="01/01/2025", vigencia_hasta="31/12/2025")
        result = evaluate_puc_validity(_contract(), _sources(puc))
        self.assertEqual(result.state, "Pendiente de fecha efectiva de asignación")

    def test_newer_refrendo_does_not_disprove_older_validity(self):
        event = _review(vigencia_desde="22/11/2025", vigencia_hasta="22/11/2026")
        result = evaluate_puc_validity(_contract(), _sources(_puc()), event)
        self.assertEqual(result.state, "Periodo aportado no acredita vigencia")
        self.assertEqual(result.assignment_result, "Anterior al periodo aportado")

    def test_expired_reference_prompts_search_for_refrendo(self):
        event = _review(vigencia_desde="01/01/2024", vigencia_hasta="31/12/2024")
        result = evaluate_puc_validity(_contract(), _sources(_puc()), event)
        self.assertEqual(result.state, "Periodo aportado no acredita vigencia")
        self.assertTrue(any("refrendos" in n for n in result.notes))

    def test_missing_start_cannot_be_filled_with_validation_date(self):
        result = evaluate_puc_validity(
            _contract(), _sources(_puc(vigencia_desde="")), _review(
                vigencia_desde="", vigencia_hasta="",
            ),
        )
        self.assertEqual(result.state, "Pendiente de vigencia histórica")
        self.assertEqual(result.assignment_result, "Periodo insuficiente")

    def test_suspended_current_cedula_requires_status_review(self):
        result = evaluate_puc_validity(
            _contract(), _sources(_puc(estado_registro="SUSPENDIDO")), _review()
        )
        self.assertEqual(result.state, "Requiere revisión del estado del registro")

    def test_missing_puc_and_other_procedures_do_not_claim_failure(self):
        result = evaluate_puc_validity(_contract(), _sources())
        self.assertEqual(result.state, "Pendiente de PUC")
        c = _contract(modalidad_adjudicacion="LICITACIÓN PÚBLICA")
        result = evaluate_puc_validity(c, _sources(_puc()))
        self.assertEqual(result.state, "No aplica al piloto AD")

    def test_foreign_document_review_cannot_supply_date_or_interval(self):
        altered = replace(_review(), contrato_cache_key="other_version")
        puc = _puc(vigencia_desde="", vigencia_hasta="31/12/2025")
        result = evaluate_puc_validity(_contract(), _sources(puc), altered)
        self.assertEqual(result.state, "Pendiente de fecha efectiva de asignación")
        self.assertTrue(any("otra versión" in n for n in result.notes))


if __name__ == "__main__":
    unittest.main()
