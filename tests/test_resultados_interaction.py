"""Comprobar que la interfaz muestra la ficha del contrato seleccionado."""
import ast
from pathlib import Path
import unittest


class ResultadosSelectionTests(unittest.TestCase):
    def test_selecting_row_rerenders_contract_details(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "ui" / "resultados.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        self.assertIn('selection_mode="single-row"', source)
        self.assertIn('on_select="rerun"', source)
        self.assertIn("selected_rows = event.selection.rows", source)
        self.assertIn("_render_details(filtered[chosen_index])", source)
        self.assertLess(
            source.index("_render_details(filtered[chosen_index])"),
            source.index("_render_aggregate_visuals(filtered)"),
        )
        self.assertIn("Personas participantes", source)
        self.assertIn("Legislación y recursos", source)
        self.assertIn("Evidencias del PDF", source)
        self.assertIn("FIELD_LABELS_V2", source)

    def test_extractor_can_be_selected_manually_for_old_contracts(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "ui" / "expedientes.py").read_text(encoding="utf-8")
        self.assertIn("Contrato completo (16 campos)", source)
        self.assertIn("extract_or_reuse_v2(", source)
        self.assertIn("st.session_state[", source)
        self.assertIn('key="ex_analyze"', source)


if __name__ == "__main__":
    unittest.main()
