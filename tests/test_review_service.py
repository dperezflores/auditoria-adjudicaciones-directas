"""Pruebas del cotejo humano: sin red, sin IA y sin documentos privados."""
from __future__ import annotations

import unittest

from services.review_service import (
    REVIEW_HEADERS, ReviewError, latest_reviews, read_reviews,
    save_review, validate_review,
)
from services.extraction_store import DOCUMENT_HEADERS, CONTRACT_HEADERS

WORK = "folderObra001ABCDE"
DOC = "documento001ABCDE"
KEY = "cacheActual003"


def manual_event(**overrides):
    values = {
        "obra_id": WORK, "documento_id": DOC, "cache_key": KEY,
        "campo": "numero_contrato", "decision": "Confirmado",
        "valor_extraido": "SIM-AD-001/2026",
        "valor_cotejado": "SIM-AD-001/2026", "pagina": "1",
        "evidencia": "Contrato SIM-AD-001/2026", "justificacion": "",
        "revisor_email": "auditor@example.com", "revision_id": "revision-A001",
    }
    values.update(overrides)
    return validate_review(**values)


class MockRequest:
    def __init__(self, response):
        self.response = response
    def execute(self):
        return self.response


class MockValues:
    def __init__(self):
        self.calls = []
        self.docs = [list(DOCUMENT_HEADERS), [
            DOC, WORK, "Contrato_SIMULADO.pdf", "", "application/pdf",
            "md5", "2026-11-08", "302268", "Requiere validación",
            "2026", "2026", "SI", "gemini:contrato-prompt-v3", KEY, "", "4",
        ]]
        self.contracts = [list(CONTRACT_HEADERS), [
            KEY, WORK, DOC, "SIM-AD-001/2026",
            "Obra simulada", "Constructora ficticia", "30 de octubre",
            "03 de noviembre", "18 de diciembre", "$1,160,000.00",
            "", "porcentaje_anticipo", "2026",
        ]]
        self.reviews = [list(REVIEW_HEADERS)]

    def get(self, **kwargs):
        self.calls.append("get")
        return MockRequest({"values": self.reviews})

    def batchGet(self, **kwargs):
        self.calls.append("batchGet")
        self.assert_no_secrets(kwargs)
        return MockRequest({
            "valueRanges": [
                {"values": self.docs},
                {"values": self.contracts},
            ],
        })

    def assert_no_secrets(self, kwargs):
        assert "api_key" not in str(kwargs)

    def append(self, **kwargs):
        self.calls.append("append")
        self.reviews.append(kwargs["body"]["values"][0])
        return MockRequest({"updates": {"updatedRows": 1}})

    def batchUpdate(self, **kwargs):
        raise AssertionError("El cotejo nunca debe sobrescribir el expediente.")


class MockClient:
    def __init__(self):
        self.sheet = MockValues()
    def spreadsheets(self):
        return self
    def values(self):
        return self.sheet


class ReviewValidationTests(unittest.TestCase):
    def test_valid_confirmation_requires_page_and_quote(self):
        record = manual_event()
        self.assertEqual(record.decision, "Confirmado")
        self.assertEqual(record.pagina, "1")
        self.assertEqual(record.revisor_email, "auditor@example.com")

    def test_confirmation_requires_matching_extracted_value(self):
        with self.assertRaises(ReviewError):
            manual_event(valor_cotejado="Otro contrato")

    def test_value_without_page_rejected(self):
        with self.assertRaises(ReviewError):
            manual_event(pagina="")

    def test_value_without_quote_rejected(self):
        with self.assertRaises(ReviewError):
            manual_event(evidencia="")

    def test_bad_page_rejected(self):
        with self.assertRaises(ReviewError):
            manual_event(pagina="-1")

    def test_correction_requires_changed_value_and_reason(self):
        with self.assertRaises(ReviewError):
            manual_event(decision="Corregido", valor_cotejado="SIM-AD-002/2026")
        corrected = manual_event(
            decision="Corregido", valor_cotejado="SIM-AD-002/2026",
            justificacion="Error de transcripción"
        )
        self.assertEqual(corrected.valor_cotejado, "SIM-AD-002/2026")

    def test_not_found_requires_justification_and_no_page(self):
        with self.assertRaises(ReviewError):
            manual_event(
                decision="No localizado", valor_cotejado="",
                pagina="", evidencia="", justificacion="",
            )
        record = manual_event(
            decision="No localizado", valor_cotejado="",
            pagina="", evidencia="", justificacion="El PDF es ilegible",
        )
        self.assertEqual(record.pagina, "")
        self.assertEqual(record.valor_cotejado, "")

    def test_reviewer_email_is_obligatory(self):
        with self.assertRaises(ReviewError):
            manual_event(revisor_email="")

    def test_invalid_field_rejected(self):
        with self.assertRaises(ReviewError):
            manual_event(campo="riesgo_juridico_automatico")


class ReviewStoreTests(unittest.TestCase):
    def setUp(self):
        self.client = MockClient()

    def test_append_only_and_repeat_is_idempotent(self):
        event = manual_event()
        added, _ = save_review(self.client, "sheet-test", event)
        self.assertTrue(added)
        self.assertEqual(len(self.client.sheet.reviews), 2)
        added_again, _ = save_review(self.client, "sheet-test", event)
        self.assertFalse(added_again)
        self.assertEqual(len(self.client.sheet.reviews), 2)
        self.assertEqual(self.client.sheet.calls.count("append"), 1)

    def test_second_revision_preserves_first_and_is_current(self):
        first = manual_event(revision_id="review1")
        second = manual_event(
            revision_id="review2", decision="Corregido",
            valor_cotejado="SIM-AD-002/2026",
            justificacion="Se revisó la portada",
        )
        save_review(self.client, "sheet-test", first)
        save_review(self.client, "sheet-test", second)
        items = read_reviews(self.client, "sheet-test")
        self.assertEqual(len(items), 2)
        self.assertEqual(
            latest_reviews(items, WORK, DOC, KEY)["numero_contrato"].decision,
            "Corregido"
        )

    def test_old_version_cannot_replace_current(self):
        bad = manual_event(cache_key="cache-old")
        with self.assertRaises(ReviewError):
            save_review(self.client, "sheet-test", bad)
        self.assertEqual(len(self.client.sheet.reviews), 1)

    def test_inactive_document_blocks_review(self):
        self.client.sheet.docs[1][11] = "NO"
        with self.assertRaises(ReviewError):
            save_review(self.client, "sheet-test", manual_event())

    def test_modified_document_blocks_review(self):
        self.client.sheet.docs[1][8] = "Modificado desde el último análisis"
        with self.assertRaises(ReviewError):
            save_review(self.client, "sheet-test", manual_event())

    def test_orig_value_must_match_sheet(self):
        with self.assertRaises(ReviewError):
            save_review(
                self.client, "sheet-test",
                manual_event(
                    valor_extraido="INVENTADO",
                    valor_cotejado="INVENTADO",
                )
            )

    def test_same_event_id_different_content_rejected(self):
        save_review(self.client, "sheet-test", manual_event())
        conflict = manual_event(
            decision="Corregido", valor_cotejado="SIM-AD-002/2026",
            justificacion="Cambio", revision_id="revision-A001",
        )
        with self.assertRaises(ReviewError):
            save_review(self.client, "sheet-test", conflict)

    def test_no_update_or_ai_called(self):
        save_review(self.client, "sheet-test", manual_event())
        self.assertNotIn("batchUpdate", self.client.sheet.calls)


if __name__ == "__main__":
    unittest.main()
