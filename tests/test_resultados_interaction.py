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
        self.assertIn("chosen_contract = filtered[chosen_index]", source)
        self.assertIn("_render_details(chosen_contract)", source)
        self.assertIn("render_document_crosscheck(chosen_contract, portfolio.supporting_documents)", source)
        self.assertLess(
            source.index("_render_details(chosen_contract)"),
            source.index("_render_aggregate_visuals(filtered)"),
        )
        self.assertIn("Personas participantes", source)
        self.assertIn("Legislación y recursos", source)
        self.assertIn("Evidencias del PDF", source)
        self.assertIn("FIELD_LABELS_V2", source)

    def test_fixed_16_field_extraction_and_pdf_link_placement(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "ui" / "expedientes.py").read_text(encoding="utf-8")
        self.assertNotIn('"Plantilla de extracción"', source)
        self.assertNotIn("ex_analysis_choice", source)
        self.assertNotIn("analysis_choice", source)
        self.assertNotIn("analyze_document(", source)
        self.assertIn("extract_or_reuse_v2(", source)
        self.assertIn('key="ex_analyze"', source)
        self.assertIn('"Código sugerido": guess_from_name(d.name, d.mime_type).label', source)
        self.assertIn("render_classification(inventory)", source)
        self.assertIn("disabled = True", source)
        self.assertIn("is_current_v2(doc)", source)
        self.assertLess(
            source.index('_summarize_saved(preview, st.session_state["ex_status_tables"], current_state)'),
            source.index('"Ver PDF en Drive"'),
        )


if __name__ == "__main__":
    unittest.main()
