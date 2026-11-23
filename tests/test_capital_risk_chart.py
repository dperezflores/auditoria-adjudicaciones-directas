"""Regresiones del gráfico CC-01: déficit por contrato y selección de ficha.

No instala Streamlit/Plotly para CI: se prueban los datos puros y los
callbacks de la interfaz mediante inspección AST y estado simulado.
"""
from __future__ import annotations

import ast
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import unittest

from services.capital_contable import evaluate_capital
from services.capital_risk_chart import (
    contract_selection_key, undercapitalized_contracts, selected_deficit_record,
)
from tests.test_capital_contable import _contract, _puc, _sources


ROOT = Path(__file__).resolve().parents[1]


class CapitalRiskChartTests(unittest.TestCase):
    def test_no_deficits_when_capital_sufficient(self):
        contract = _contract()
        good = evaluate_capital(contract, _sources(_puc()))
        self.assertEqual(undercapitalized_contracts([(contract, good)]), ())

    def test_only_numeric_capital_deficits_are_plotted(self):
        contract = _contract()
        bad = evaluate_capital(
            contract, _sources(_puc(capital=Decimal("200000")))
        )
        good = evaluate_capital(contract, _sources(_puc()))
        missing = evaluate_capital(contract, _sources(_puc(capital=None)))
        unavailable = evaluate_capital(contract, _sources())
        deficits = undercapitalized_contracts([
            (contract, good), (contract, missing),
            (contract, bad), (contract, unavailable),
        ])
        self.assertEqual(len(deficits), 1)
        self.assertEqual(deficits[0].portfolio_index, 2)
        self.assertEqual(deficits[0].faltante, Decimal("100000.00"))
        self.assertEqual(deficits[0].minimo, Decimal("300000.00"))
        self.assertEqual(deficits[0].capital, Decimal("200000"))
        self.assertEqual(deficits[0].contratista, "GUTIERREZ GUTIERREZ DE VELASCO ALEJANDRO") if False else None

    def test_same_contractor_multiple_contracts_are_separate(self):
        one = _contract()
        two = replace(
            one, obra_id="otra_obra", documento_id="otro_contrato",
            cache_key="otra_version", nombre_carpeta="010_SegundaObra",
        )
        # Construimos resultados en la misma posición que sus contratos.
        smaller = evaluate_capital(
            one, _sources(_puc(capital=Decimal("200000")))
        )
        biggest = evaluate_capital(
            one, _sources(_puc(capital=Decimal("100000")))
        )
        deficits = undercapitalized_contracts([
            (one, smaller), (two, biggest),
        ])
        self.assertEqual(len(deficits), 2)
        self.assertEqual(
            {item.record_key for item in deficits},
            {contract_selection_key(one), contract_selection_key(two)},
        )
        self.assertEqual([d.portfolio_index for d in deficits], [1, 0])
        self.assertEqual(
            [d.faltante for d in deficits],
            [Decimal("200000.00"), Decimal("100000.00")],
        )

    def test_puc_out_of_period_does_not_hide_numeric_shortfall(self):
        contract = _contract()
        risk = evaluate_capital(
            contract, _sources(_puc(
                vigencia_hasta="01/12/2025",
                capital=Decimal("250000"),
            ))
        )
        self.assertEqual(risk.state, "PUC fuera de vigencia en fecha de firma")
        deficits = undercapitalized_contracts([(contract, risk)])
        self.assertEqual(len(deficits), 1)
        self.assertEqual(deficits[0].vigencia, "Fuera del periodo PUC en fecha de firma")
        self.assertEqual(deficits[0].resultado, risk.state)

    def test_chart_event_uses_stable_document_key_not_plot_position(self):
        one = _contract()
        two = replace(
            one, documento_id="conDoc2", cache_key="different",
        )
        keys = (contract_selection_key(one), contract_selection_key(two))
        event = {
            "selection": {
                "points": [
                    {"point_index": 0, "customdata": [keys[1], "empresa"]},
                ],
            },
        }
        self.assertEqual(selected_deficit_record(event, keys), keys[1])
        self.assertIsNone(
            selected_deficit_record(event, (keys[0],)),
        )
        self.assertIsNone(selected_deficit_record(
            {"selection": {"points": [{"point_index": 1}]}}, keys
        ))
        self.assertIsNone(
            selected_deficit_record({"selection": {"points": []}}, keys)
        )

    def test_chart_and_table_callbacks_control_same_active_contract(self):
        code = (ROOT / "ui" / "capital_contable.py").read_text("utf-8")
        tree = ast.parse(code)
        functions = [
            x for x in tree.body
            if isinstance(x, ast.FunctionDef)
            and x.name in ("_select_capital_from_table", "_select_capital_from_chart")
        ]
        self.assertEqual(len(functions), 2)
        module = ast.Module(body=[
            ast.ImportFrom(
                module="__future__",
                names=[ast.alias(name="annotations")],
                level=0,
            ),
            *functions,
        ], type_ignores=[])
        state = {
            "capital_selectable_work_table": {
                "selection": {"rows": [0]},
            },
            "capital_deficit_selectable_chart": {
                "selection": {"points": [{"customdata": ["contract-B"]}]},
            },
        }
        ns = {
            "st": SimpleNamespace(session_state=state),
            "_TABLE_KEY": "capital_selectable_work_table",
            "_CHART_KEY": "capital_deficit_selectable_chart",
            "_SELECTED_KEY": "capital_active_contract_key",
            "selected_deficit_record": selected_deficit_record,
        }
        exec(compile(ast.fix_missing_locations(module), "ui-test.py", "exec"), ns)
        ns["_select_capital_from_chart"](("contract-A", "contract-B"))
        self.assertEqual(state["capital_active_contract_key"], "contract-B")
        ns["_select_capital_from_table"](("contract-A", "contract-B"))
        self.assertEqual(state["capital_active_contract_key"], "contract-A")
        state["capital_deficit_selectable_chart"]["selection"]["points"] = [
            {"customdata": ["unknown"]}
        ]
        ns["_select_capital_from_chart"](("contract-A", "contract-B"))
        self.assertEqual(state["capital_active_contract_key"], "contract-A")

    def test_chart_has_click_selection_and_reuses_table_detail(self):
        source = (ROOT / "ui" / "capital_contable.py").read_text("utf-8")
        self.assertIn("undercapitalized_contracts(results)", source)
        self.assertIn("st.plotly_chart(", source)
        self.assertIn('selection_mode="points"', source)
        self.assertIn('clickmode="event+select"', source)
        self.assertIn('key=_CHART_KEY', source)
        self.assertIn("on_select=lambda: _select_capital_from_chart(valid_keys)", source)
        self.assertIn('key="capital_selectable_work_table"', source)
        self.assertIn("on_select=lambda: _select_capital_from_table(contract_keys)", source)
        self.assertIn("record,result=results[selected]", source)
        self.assertIn("render_verification_form(record,prefix=\"capital\")", source)
        self.assertNotIn("_analyze(", source)
        self.assertNotIn("extract_or_reuse_", source)


if __name__ == "__main__":
    unittest.main()
