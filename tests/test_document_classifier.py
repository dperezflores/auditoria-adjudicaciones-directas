"""Clasificación sin IA: nombres, contenido y reglas anti-confusión."""
from __future__ import annotations

from io import BytesIO
import unittest

from openpyxl import Workbook

from services.document_classifier import (
    PDF_MIME, XLSX_MIME, DOCUMENT_CODES, _identify_text, _reconcile,
    classify_pdf, classify_xlsx, guess_from_name,
)


def workbook_bytes(*, catalog: bool) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Prefiniquito" if catalog else "Hoja de salarios"
    if catalog:
        ws.append(["CLAVE", "DESCRIPCIÓN", "UNIDAD", "INICIAL", "PRECIO U."])
        ws.append(["101", "PAVIMENTO DE CONCRETO", "M2", 100, 320])
    else:
        ws.append(["NOMBRE", "SUELDO", "SEMANA"])
    raw = BytesIO()
    wb.save(raw)
    wb.close()
    return raw.getvalue()


class ClassificationTests(unittest.TestCase):
    def test_six_codes_are_exact(self):
        self.assertEqual(DOCUMENT_CODES, (
            "CONTRATO", "PUC", "CATALOGO", "DICTAMEN_AD",
            "NOTIFICACION_AD", "ORDEN_AD",
        ))

    def test_filename_suggestions_are_not_verified(self):
        examples = {
            "CONTRATO.pdf": "CONTRATO",
            "CNT_DIR_CNT.pdf": "CONTRATO",
            "PUC.pdf": "PUC",
            "PADRON .pdf": "PUC",
            "DICTAMEN_AD.pdf": "DICTAMEN_AD",
            "NOTIFICACION_AD.pdf": "NOTIFICACION_AD",
            "ORDEN_AD.pdf": "ORDEN_AD",
        }
        for name, code in examples.items():
            with self.subTest(name=name):
                item = guess_from_name(name, PDF_MIME)
                self.assertEqual(item.code, code)
                self.assertFalse(item.confirmed)
        self.assertEqual(guess_from_name("CATALOGO.xlsx", XLSX_MIME).code, "CATALOGO")

    def test_generic_dictamen_tecnico_does_not_become_ad(self):
        self.assertIsNone(guess_from_name("DICTAMEN TECNICO.pdf", PDF_MIME).code)
        self.assertIsNone(guess_from_name("LISTADO.pdf", PDF_MIME).code)
        self.assertIsNone(guess_from_name("ORDEN DE COMPRA.pdf", PDF_MIME).code)

    def test_content_classifies_titles_not_generic_mentions(self):
        examples = {
            "DICTAMEN DE AUTORIZACIÓN DE ADJUDICACIÓN DIRECTA": "DICTAMEN_AD",
            "NOTIFICACIÓN DE ADJUDICACIÓN DIRECTA": "NOTIFICACION_AD",
            "ORDEN DE ADJUDICACIÓN DIRECTA": "ORDEN_AD",
            "INFORMACIÓN DEL PADRÓN ÚNICO DE CONTRATISTAS DEL ESTADO": "PUC",
            "CONTRATO DE OBRA PÚBLICA A PRECIOS UNITARIOS": "CONTRATO",
        }
        for title, code in examples.items():
            self.assertEqual(_identify_text("DIRECCIÓN GENERAL DE OBRA PÚBLICA. " + title), code)
        self.assertIsNone(_identify_text(
            "Se acreditó con su registro del PUC y con un dictamen técnico."
        ))

    def test_content_can_override_unknown_name_but_conflicts_blocked(self):
        unknown = guess_from_name("DGOP_587.pdf", PDF_MIME)
        verified = _reconcile(unknown, "DICTAMEN_AD", readable=True)
        self.assertTrue(verified.confirmed)
        self.assertEqual(verified.code, "DICTAMEN_AD")
        conflict = _reconcile(guess_from_name("PUC.pdf", PDF_MIME), "CONTRATO", readable=True)
        self.assertEqual(conflict.status, "Inconsistente")
        self.assertFalse(conflict.confirmed)
        self.assertIsNone(conflict.code)

    def test_image_pdf_is_not_confirmed_automatically(self):
        scanned = classify_pdf(b"%PDF-1.4\nnot really a PDF", "PUC.pdf")
        self.assertEqual(scanned.code, "PUC")
        self.assertFalse(scanned.confirmed)

    def test_catalog_workbook_read_without_ai(self):
        report = classify_xlsx(workbook_bytes(catalog=True), "CATALOGO.xlsx")
        self.assertTrue(report.confirmed)
        self.assertEqual(report.code, "CATALOGO")
        report = classify_xlsx(workbook_bytes(catalog=True), "PREFINIQUITO.xlsx")
        self.assertTrue(report.confirmed)

    def test_non_catalog_workbook_not_confirmed(self):
        report = classify_xlsx(workbook_bytes(catalog=False), "CATALOGO.xlsx")
        self.assertFalse(report.confirmed)
        self.assertEqual(report.status, "Por verificar")


if __name__ == "__main__":
    unittest.main()
