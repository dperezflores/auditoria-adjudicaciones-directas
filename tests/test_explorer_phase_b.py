"""Pruebas del explorador Fase B, con datos ilustrativos y sin Streamlit/Gemini."""
from __future__ import annotations

from pathlib import Path
import unittest

from services.analysis_catalog import folder_states
from services.document_classifier import XLSX_MIME
from services.selection_rules import plan_work_selection
from ui.preview_data import visual_preview


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = {
    "CONTRATO": "contrato-v2", "PUC": "puc-v1",
    "DICTAMEN_AD": "dictamen-ad-v1",
    "NOTIFICACION_AD": "notificacion-ad-v1",
    "ORDEN_AD": "orden-ad-v1",
    "CATALOGO": "catalogo-xlsx-v1",
}


class ExplorerPhaseBTests(unittest.TestCase):
    def test_preview_has_three_fictitious_works_no_real_urls(self):
        inventory, tables, states = visual_preview()
        self.assertEqual(len(inventory.works), 3)
        self.assertTrue(all(w.id.startswith("DEMO_") for w in inventory.works))
        self.assertTrue(all(w.name.startswith("EJEMPLO_") for w in inventory.works))
        self.assertTrue(all(not w.url for w in inventory.works))
        self.assertEqual(len(folder_states(inventory, states)), 3)
        self.assertTrue(all(not d.url for w in inventory.works for d in (*w.pdfs, *w.other_files)))
        self.assertTrue(all("SAMPLE_" in a["cache_key"] for a in tables["Extracciones"]))
        self.assertEqual(states["DA1"].label, "Analizado")
        self.assertEqual(states["DA3"].label, "Pendiente")

    def test_preview_catalog_is_local_and_completed_not_reanalyzed(self):
        inventory, tables, states = visual_preview()
        registered = {x["documento_id"]: x for x in tables["Documentos"]}
        extractions = {x["cache_key"]: x for x in tables["Extracciones"]}
        work = inventory.works[0]
        supported = [*work.pdfs, *(d for d in work.other_files if d.mime_type == XLSX_MIME)]
        plan = plan_work_selection(work.id, supported, registered, extractions, states, SCHEMAS)
        self.assertIn("DA6", {d.id for d in plan.reused})
        self.assertNotIn("DA6", {d.id for d in plan.eligible})
        self.assertEqual({d.id for d in plan.eligible}, {"DA3", "DA4", "DA5"})

    def test_real_data_source_routes_to_new_ui_without_touching_legacy(self):
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        old = (ROOT / "ui" / "expedientes.py").read_text(encoding="utf-8")
        screen = (ROOT / "ui" / "explorer_panel.py").read_text(encoding="utf-8")
        self.assertIn("from ui.explorer_panel import render_expedientes", app)
        self.assertIn("from ui.expedientes import _refresh_inventory", app)
        self.assertIn("from ui.expedientes import (", screen)
        self.assertIn("_analyze(active_work, batch, model)", screen)
        self.assertIn("_summarize_saved(doc, tables, status)", screen)
        self.assertIn("_render_delete_analysis(doc, work, tables)", screen)
        self.assertIn('if st.session_state.pop("ex_v2_request_analysis", False):', screen)
        self.assertIn("plan_work_selection(", screen)
        self.assertIn("st.segmented_control(", screen)
        self.assertIn("st.checkbox(", screen)
        self.assertIn("barra_seleccion(", screen)
        self.assertIn("_load_or_preview()", screen)
        self.assertIn("No se reintentarán automáticamente.", screen)
        self.assertIn("max_batch", (ROOT / "services" / "selection_rules.py").read_text())
        self.assertIn("def render_expedientes(authenticated: bool)", old)
        self.assertIn("def _analyze(", old)

    def test_page_uses_fixed_bar_and_new_cards_in_separate_components(self):
        styles = (ROOT / "ui" / "styles.css").read_text(encoding="utf-8")
        components = (ROOT / "ui" / "components.py").read_text(encoding="utf-8")
        screen = (ROOT / "ui" / "explorer_panel.py").read_text(encoding="utf-8")
        self.assertIn("position:fixed;bottom:0", styles)
        self.assertIn(".aud-space-for-bar", styles)
        self.assertIn("st.container(key=\"ex_barra_seleccion\")", components)
        self.assertIn('class="aud-bar-active"', components)
        self.assertIn("EXPECTED_DOCUMENTS", screen)
        self.assertIn("OPTIONAL_DOCUMENT", screen)
        self.assertIn("Sin extractor compatible", screen)
        self.assertIn("disabled=is_demo", screen)

    def test_widget_reset_runs_before_render_to_avoid_streamlit_exception(self):
        screen = (ROOT / "ui" / "explorer_panel.py").read_text(encoding="utf-8")
        self.assertIn('st.session_state["ex_v2_reset_after_analysis"] = True', screen)
        self.assertIn('st.session_state.pop("ex_v2_reset_after_analysis", False)', screen)
        self.assertLess(
            screen.index('st.session_state.pop("ex_v2_reset_after_analysis", False)'),
            screen.index('focused = _render_tree('),
        )
        self.assertNotIn(
            'st.session_state["ex_last_run_obra_id"] = active_work.id\n        _clear_selection()',
            screen,
        )

    def test_no_demo_analysis_or_drive_calls(self):
        source = (ROOT / "ui" / "preview_data.py").read_text(encoding="utf-8")
        self.assertNotIn("create_drive_client", source)
        self.assertNotIn("create_sheets_client", source)
        self.assertNotIn("extract_or_reuse", source)
        self.assertNotIn("genai.Client", source)


if __name__ == "__main__":
    unittest.main()
