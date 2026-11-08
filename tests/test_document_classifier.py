"""El tipo documental depende exclusivamente del nombre y del MIME de Drive."""
import unittest

from services.document_classifier import (
    DOCUMENT_CODES, PDF_MIME, XLSX_MIME, code_from_filename, guess_from_name,
)


class FilenameClassificationTests(unittest.TestCase):
    def test_six_document_codes_and_canonical_filenames(self):
        expected = {
            "CONTRATO.pdf": "CONTRATO",
            "PUC.pdf": "PUC",
            "DICTAMEN_AD.pdf": "DICTAMEN_AD",
            "NOTIFICACION_AD.pdf": "NOTIFICACION_AD",
            "ORDEN_AD.pdf": "ORDEN_AD",
            "CATALOGO.xlsx": "CATALOGO",
        }
        self.assertEqual(len(DOCUMENT_CODES), 6)
        for name, code in expected.items():
            mime = XLSX_MIME if name.endswith(".xlsx") else PDF_MIME
            with self.subTest(file=name):
                self.assertEqual(code_from_filename(name, mime), code)
                classification = guess_from_name(name, mime)
                self.assertEqual(classification.code, code)
                self.assertTrue(classification.confirmed)
                self.assertEqual(classification.status, "Asignado por nombre")

    def test_case_insensitive_but_exact_document_codes(self):
        self.assertEqual(code_from_filename("puc.PDF", PDF_MIME), "PUC")
        self.assertEqual(code_from_filename("contrato.pdf", PDF_MIME), "CONTRATO")
        self.assertEqual(code_from_filename("catalogo.XLSX", XLSX_MIME), "CATALOGO")
        self.assertIsNone(code_from_filename("PUC (1).pdf", PDF_MIME))
        self.assertIsNone(code_from_filename("PADRON.pdf", PDF_MIME))
        self.assertIsNone(code_from_filename("CNT_DIR_CNT.pdf", PDF_MIME))

    def test_space_before_extension_in_second_work_folder(self):
        # Nombres observados directamente en Drive (carpeta 00_117_25).
        for name, code in (
            ("CONTRATO .pdf", "CONTRATO"),
            ("PUC .pdf", "PUC"),
            ("DICTAMEN_AD .pdf", "DICTAMEN_AD"),
            ("NOTIFICACION_AD  .PDF", "NOTIFICACION_AD"),
            ("ORDEN_AD\u00a0.pdf", "ORDEN_AD"),
            ("CATALOGO .xlsx", "CATALOGO"),
        ):
            mime = XLSX_MIME if name.upper().endswith("XLSX") else PDF_MIME
            with self.subTest(name=name):
                self.assertEqual(code_from_filename(name, mime), code)
                self.assertEqual(guess_from_name(name, mime).label, code)

    def test_spaces_do_not_allow_different_document_names(self):
        for name in ("CONTRATO FINAL .pdf", "CONTRATO (1) .pdf",
                     "PUC actual .pdf", "DICTAMEN .pdf"):
            with self.subTest(name=name):
                self.assertIsNone(code_from_filename(name, PDF_MIME))
        self.assertIsNone(code_from_filename("PUC .pdf", XLSX_MIME))

    def test_unknown_or_unrelated_files_never_receive_an_incorrect_code(self):
        for name in (
            "DICTAMEN TECNICO.pdf", "DICTAMEN.pdf", "ORDEN DE COMPRA.pdf",
            "PUC_ANTERIOR.pdf", "PRESUPUESTO.xlsx", "CONTRATO_BORRADOR.pdf",
        ):
            mime = XLSX_MIME if name.endswith(".xlsx") else PDF_MIME
            with self.subTest(file=name):
                self.assertIsNone(code_from_filename(name, mime))
                self.assertEqual(guess_from_name(name, mime).label, "POR_IDENTIFICAR")

    def test_mime_mismatch_does_not_assign_code(self):
        self.assertIsNone(code_from_filename("PUC.pdf", XLSX_MIME))
        self.assertIsNone(code_from_filename("CATALOGO.xlsx", PDF_MIME))
        self.assertIsNone(code_from_filename("PUC.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))


if __name__ == "__main__":
    unittest.main()
