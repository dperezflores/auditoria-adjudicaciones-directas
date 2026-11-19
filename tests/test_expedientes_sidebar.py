"""Verifica la distribución de la app original sin iniciar Streamlit ni Gemini."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class ExpedientesSidebarTests(unittest.TestCase):
    def test_sidebar_slot_is_above_service_controls_and_only_on_expedientes(self):
        app = source("app.py")
        self.assertIn('initial_sidebar_state="expanded"', app)
        self.assertIn(
            'folder_panel = st.container() if page == "Expedientes" else None',
            app,
        )
        self.assertIn(
            'render_expedientes(allowed, folder_container=folder_panel)',
            app,
        )
        self.assertLess(
            app.index('folder_panel = st.container()'),
            app.index('st.caption("SERVICIOS CONECTADOS")'),
        )
        self.assertIn('elif page == "Resultados":', app)
        self.assertIn('render_award_tests()', app)

    def test_main_extraction_is_not_preceded_by_full_folder_list(self):
        screen = source("ui/expedientes.py")
        start = screen.index("def render_expedientes(")
        body = screen[start:]
        self.assertIn('obra_id = _render_sidebar_folders(', body)
        self.assertLess(
            body.index('obra_id = _render_sidebar_folders('),
            body.index('st.markdown("### Extracción documental")'),
        )
        self.assertLess(
            body.index('st.markdown("### Extracción documental")'),
            body.index('work_docs = ['),
        )
        self.assertNotIn('st.markdown("### Carpetas de obra")', body)
        self.assertNotIn('st.expander(\n            f"📁 {work.name}', body)
        self.assertNotIn('col1.metric("Carpetas"', body)

    def test_sidebar_search_filter_select_and_scroll_are_preserved(self):
        screen = source("ui/expedientes.py")
        tree = screen.split("def _render_sidebar_folders(", 1)[1].split(
            "\ndef render_expedientes(", 1,
        )[0]
        for expected in (
            'key="ex_selected_folder"',
            'key="ex_search"',
            'key="ex_folder_filter"',
            'key=f"ex_nav_folder_{work.id}"',
            'st.container(height=300, border=False)',
            'with st.expander("Buscar y explorar obras", expanded=True)',
            'with st.expander("Documentos de la carpeta seleccionada"',
            'for file in (*work.pdfs, *work.other_files)',
            'states[doc.id].label',
            'return obra_id',
        ):
            self.assertIn(expected, tree)
        self.assertIn(
            'st.session_state["ex_selected_folder"] = folder_id',
            screen,
        )
        self.assertNotIn("_analyze(", tree)
        self.assertNotIn("genai", tree)
        self.assertNotIn("_refresh_inventory(", tree)

    def test_original_extraction_and_preview_remain_in_main(self):
        screen = source("ui/expedientes.py")
        for expected in (
            'if pending_attempt:',
            'needs_sync += 1',
            'batch = to_process[:MAX_BATCH]',
            'key="ex_analyze"',
            'st.session_state["ex_last_run"] = _analyze(obra, batch, model)',
            '_summarize_saved(preview, st.session_state["ex_status_tables"], current_state)',
            '_render_contract_upgrade(',
            '_render_delete_analysis(',
            '"Ver documento en Drive"',
            'key=f"ex_preview_{obra.id}"',
        ):
            self.assertIn(expected, screen)

    def test_python_source_remains_syntactically_valid(self):
        ast.parse(source("app.py"))
        ast.parse(source("ui/expedientes.py"))


if __name__ == "__main__":
    unittest.main()
