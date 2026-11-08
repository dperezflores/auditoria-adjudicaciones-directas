"""Regresión de interfaz: análisis manual sin aviso ni casilla adicional."""
from pathlib import Path
import unittest

from services.contract_v2 import CONTRACT_SCHEMA_V2
from services.document_classifier import PDF_MIME, code_from_filename


class AnalysisInterfaceTests(unittest.TestCase):
    def test_no_confirmation_warning_in_expedientes(self):
        source = (
            Path(__file__).resolve().parents[1] / "ui" / "expedientes.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("Antes de usar expedientes reales verifica", source)
        self.assertNotIn("Confirmo que tengo autorización para enviar estos PDF", source)
        self.assertNotIn("ex_approved_", source)
        self.assertIn('key="ex_analyze"', source)
        self.assertIn('disabled=disabled', source)

    def test_contrato_routing_uses_existing_v2_and_cache(self):
        source = (
            Path(__file__).resolve().parents[1] / "ui" / "expedientes.py"
        ).read_text(encoding="utf-8")
        self.assertEqual(code_from_filename("CONTRATO.pdf", PDF_MIME), "CONTRATO")
        self.assertEqual(CONTRACT_SCHEMA_V2, "contrato-v2")
        self.assertIn('"CONTRATO": CONTRACT_SCHEMA_V2', source)
        self.assertIn('if code == "CONTRATO":', source)
        self.assertIn("result = extract_or_reuse_v2(", source)
        self.assertIn("CONTRATO-v2 (16 campos)", source)
        self.assertIn("if pending_attempt:", source)
        self.assertNotIn(
            'pending_attempt or states[doc.id].label in ("Parcial", "Revisar error")', source
        )

    def test_analysis_remains_manual(self):
        source = (
            Path(__file__).resolve().parents[1] / "ui" / "expedientes.py"
        ).read_text(encoding="utf-8")
        self.assertIn('if st.button(\n        f"Analizar', source)
        self.assertIn('st.session_state["ex_last_run"] = _analyze(', source)


if __name__ == "__main__":
    unittest.main()
