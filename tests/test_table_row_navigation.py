"""Selección de obra desde las tablas de las tres secciones operativas.

La prueba no importa Streamlit: inspecciona estructura y comprueba el callback
de sincronización de Expedientes con un estado de sesión simulado.
"""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]


def _source(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


class WorkTableNavigationTests(unittest.TestCase):
    def test_results_already_selects_contract_from_table(self):
        text = _source("ui/resultados.py")
        self.assertIn('selection_mode="single-row"', text)
        self.assertIn('on_select="rerun"', text)
        self.assertIn('chosen_contract = filtered[chosen_index]', text)
        self.assertIn('_render_details(chosen_contract)', text)

    def test_all_three_award_tests_select_from_their_result_table(self):
        checks = (
            ("ui/pruebas_adjudicacion.py",
             "award_limits_selectable_work_table",
             "record, automatic=evaluations[chosen]",
             "render_verification_form(record,prefix=\"ad06\")"),
            ("ui/capital_contable.py",
             "capital_selectable_work_table",
             "record,result=results[selected]",
             "render_puc_history_form(record,result.puc,revisions,prefix=\"capital\")"),
            ("ui/puc_validity.py",
             "puc_validity_selectable_work_table",
             "record, result, review = results[selected]",
             "render_puc_history_form(record, result.puc, reviews, prefix=\"puc_validity\")"),
        )
        for file, key, mapping, details in checks:
            with self.subTest(page=file):
                text = _source(file)
                ast.parse(text)
                self.assertIn('selection_mode="single-row"', text)
                if file == "ui/capital_contable.py":
                    self.assertIn(
                        "on_select=lambda: _select_capital_from_table(contract_keys)",
                        text,
                    )
                    self.assertIn(
                        "on_select=lambda: _select_capital_from_chart(valid_keys)",
                        text,
                    )
                else:
                    self.assertIn('on_select="rerun"', text)
                self.assertIn(f'key="{key}"', text)
                self.assertIn('selected_rows = table_event.selection.rows', text)
                self.assertIn(mapping, text)
                self.assertIn(details, text)
                self.assertLess(text.index('selected_rows = table_event.selection.rows'),
                                text.index(mapping))
                self.assertLess(text.index(mapping), text.index(details))

    def test_expedientes_selection_syncs_sidebar_and_opens_bulk_work(self):
        text = _source("ui/expedientes.py")
        ast.parse(text)
        for marker in (
            "def _select_folder_from_work_table(",
            'st.session_state["ex_selected_folder"] = work_ids[rows[0]]',
            'on_select=lambda: _select_folder_from_work_table(table_key, work_ids)',
            'selection_mode="single-row"',
            "def _show_bulk_selected_work(",
            'key="ex_bulk_decisions_selectable"',
            'key="ex_bulk_pending_selectable"',
            'key="ex_bulk_completed_selectable"',
            'st.session_state["ex_analysis_mode"] = "Una carpeta"',
        ):
            self.assertIn(marker, text)
        self.assertNotIn("on_select=_analyze", text)
        self.assertNotIn("on_select=extract_or_reuse", text)

    def test_callback_uses_exact_row_id_and_ignores_out_of_range(self):
        tree = ast.parse(_source("ui/expedientes.py"))
        fn = next(
            n for n in tree.body
            if isinstance(n, ast.FunctionDef)
            and n.name == "_select_folder_from_work_table"
        )
        module = ast.Module(
            body=[
                ast.ImportFrom(
                    module="__future__",
                    names=[ast.alias(name="annotations")],
                    level=0,
                ),
                fn,
            ],
            type_ignores=[],
        )
        state = {
            "ex_selected_folder": "obra-original",
            "tabla_abc": {"selection": {"rows": [1]}},
        }
        namespace = {"st": SimpleNamespace(session_state=state)}
        exec(compile(ast.fix_missing_locations(module), "test_ui.py", "exec"), namespace)
        navigate = namespace["_select_folder_from_work_table"]
        navigate("tabla_abc", ("obra-uno", "obra-dos", "obra-tres"))
        self.assertEqual(state["ex_selected_folder"], "obra-dos")
        state["tabla_abc"]["selection"]["rows"] = [99]
        navigate("tabla_abc", ("obra-uno", "obra-dos", "obra-tres"))
        self.assertEqual(state["ex_selected_folder"], "obra-dos")
        state["tabla_abc"]["selection"]["rows"] = []
        navigate("tabla_abc", ("obra-uno", "obra-dos", "obra-tres"))
        self.assertEqual(state["ex_selected_folder"], "obra-dos")


if __name__ == "__main__":
    unittest.main()
