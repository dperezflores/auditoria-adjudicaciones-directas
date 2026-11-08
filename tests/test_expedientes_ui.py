"""Regresión de interfaz: análisis manual sin aviso ni casilla adicional."""
from pathlib import Path
import unittest


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

    def test_analysis_remains_manual(self):
        source = (
            Path(__file__).resolve().parents[1] / "ui" / "expedientes.py"
        ).read_text(encoding="utf-8")
        self.assertIn('if st.button(\n        f"Analizar', source)
        self.assertIn('st.session_state["ex_last_run"] = _analyze(', source)


if __name__ == "__main__":
    unittest.main()
