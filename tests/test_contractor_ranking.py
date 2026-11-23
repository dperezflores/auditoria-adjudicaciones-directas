"""Top 10 de contratistas en Resultados, filtrado y sin doble conteo.

Pruebas puras de clasificación; no requieren Streamlit ni Plotly durante CI.
"""
from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path
import unittest

from services.contractor_ranking import rank_contractors
from services.contract_portfolio import ContractPortfolio, filter_contracts
from tests.test_award_limits import contract


def _record(
    num: int, contractor: str, rfc: str, year: str,
    *, status: str | None = None,
):
    original = contract()
    old_values = original.values
    old_full = original.full_values or {}
    date = f"10/03/{year}" if year.isdecimal() else ""
    return replace(
        original,
        obra_id=f"obra-{num}",
        documento_id=f"contrato-{num}",
        cache_key=f"cache-{num}",
        signature_year=year,
        nombre_carpeta=f"Obra {num}",
        values={**old_values, "contratista": contractor,
                "numero_contrato": f"C-{num}", "fecha_firma": date},
        full_values={
            **old_full, "contratista": contractor,
            "rfc": rfc, "numero_contrato": f"C-{num}",
            "fecha_firma_contrato": date,
        },
        state=status or original.state,
    )


class TopContractorsRankingTests(unittest.TestCase):
    def test_count_contracts_not_works_and_sort_most_first(self):
        contracts = (
            _record(1, "Empresa Alfa SA de CV", "AAA010101AB1", "2025"),
            _record(2, "Empresa Alfa S.A. de C.V.", "AAA010101AB1", "2025"),
            _record(3, "Constructora Beta", "BBB010101AB1", "2025"),
            _record(4, "Empresa Alfa SA de CV", "AAA010101AB1", "2024"),
            _record(5, "Empresa Gamma", "CCC010101AB1", "2024"),
        )
        ranking = rank_contractors(contracts)
        self.assertEqual(
            [(item.count, item.rfc) for item in ranking.top],
            [(3, "AAA010101AB1"), (1, "BBB010101AB1"), (1, "CCC010101AB1")],
        )
        self.assertEqual(ranking.unique_contractors, 3)

    def test_year_filter_is_shared_with_existing_results_view(self):
        records = (
            _record(1, "Empresa Alfa", "AAA010101AB1", "2025"),
            _record(2, "Empresa Alfa", "AAA010101AB1", "2025"),
            _record(3, "Empresa Beta", "BBB010101AB1", "2025"),
            _record(4, "Empresa Alfa", "AAA010101AB1", "2024"),
            _record(5, "Empresa Beta", "BBB010101AB1", "2024"),
        )
        p = ContractPortfolio(records)
        ranking_2025 = rank_contractors(filter_contracts(p, year="2025"))
        ranking_2024 = rank_contractors(filter_contracts(p, year="2024"))
        ranking_all = rank_contractors(filter_contracts(p, year="Todos"))
        self.assertEqual(
            [(item.name, item.count) for item in ranking_2025.top],
            [("Empresa Alfa", 2), ("Empresa Beta", 1)],
        )
        self.assertEqual([item.count for item in ranking_2024.top], [1, 1])
        self.assertEqual([item.count for item in ranking_all.top], [3, 2])

    def test_filter_by_name_search_and_status_is_inherited(self):
        records = (
            _record(1, "Empresa Alfa", "AAA010101AB1", "2025"),
            _record(2, "Empresa Beta", "BBB010101AB1", "2025"),
        )
        p = ContractPortfolio(records)
        only_alfa = filter_contracts(p, contractor="Empresa Alfa")
        self.assertEqual(rank_contractors(only_alfa).top[0].count, 1)
        self.assertEqual(len(rank_contractors(only_alfa).top), 1)
        by_search = filter_contracts(p, query="obra 2")
        self.assertEqual(rank_contractors(by_search).top[0].name, "Empresa Beta")
        no_state = filter_contracts(p, status="Estado que no existe")
        self.assertFalse(rank_contractors(no_state).top)

    def test_name_without_rfc_joins_unambiguous_legal_name(self):
        ranking = rank_contractors((
            _record(1, "CONSTRUCTORA DEL BAJÍO, S.A. DE C.V.",
                    "ABC010101AB1", "2025"),
            _record(2, "Constructora del Bajio SA de CV", "", "2025"),
        ))
        self.assertEqual(ranking.unique_contractors, 1)
        self.assertEqual(ranking.top[0].count, 2)

    def test_same_name_with_different_rfcs_are_not_falsely_merged(self):
        ranking = rank_contractors((
            _record(1, "Constructora del Centro", "AAA010101AB1", "2025"),
            _record(2, "Constructora del Centro", "BBB010101AB1", "2025"),
            _record(3, "Constructora del Centro", "", "2025"),
        ))
        self.assertEqual(ranking.unique_contractors, 3)
        self.assertEqual([i.count for i in ranking.top], [1, 1, 1])

    def test_exact_duplicated_document_is_only_counted_once(self):
        first = _record(1, "Empresa Alfa", "AAA010101AB1", "2025")
        old_extraction = replace(first, cache_key="extraccion-vieja")
        ranking = rank_contractors((first, old_extraction))
        self.assertEqual(ranking.top[0].count, 1)

    def test_top_ten_limit_and_contractors_without_name(self):
        records = tuple(
            _record(i, f"Empresa {i}", "", "2025")
            for i in range(12)
        )
        records += (_record(20, "No localizado", "", "2025"),)
        ranking = rank_contractors(records, limit=10)
        self.assertEqual(ranking.unique_contractors, 12)
        self.assertEqual(len(ranking.top), 10)
        self.assertEqual(ranking.contracts_without_contractor, 1)
        with self.assertRaises(ValueError):
            rank_contractors(records, limit=0)

    def test_saved_contractor_correction_changes_group(self):
        first = _record(1, "Empresa Alfa", "AAA010101AB1", "2025")
        second = _record(2, "Empresa Beta", "BBB010101AB1", "2025")
        second = replace(
            second,
            verification={"campos": {
                "contratista": "Empresa Alfa",
                "rfc": "AAA010101AB1",
            }},
        )
        ranking = rank_contractors((first, second))
        self.assertEqual(len(ranking.top), 1)
        self.assertEqual(ranking.top[0].count, 2)

    def test_visual_is_between_indicators_and_table_and_uses_filtered(self):
        src = (Path(__file__).resolve().parents[1] /
               "ui" / "resultados.py").read_text("utf-8")
        ast.parse(src)
        self.assertIn("def _render_top_contractors(", src)
        self.assertIn("rank_contractors(records, limit=10)", src)
        self.assertIn("st.plotly_chart(", src)
        self.assertIn('"results_top10_contractors_chart"', src)
        self.assertIn('label_year = (', src)
        self.assertIn("_render_top_contractors(filtered, year)", src)
        self.assertLess(
            src.index('col1.metric("Obras con contrato"'),
            src.index("_render_top_contractors(filtered, year)"),
        )
        self.assertLess(
            src.index("_render_top_contractors(filtered, year)"),
            src.index('st.markdown("#### Listado de obras y contratos")'),
        )
        self.assertNotIn("extract_or_reuse", src)


if __name__ == "__main__":
    unittest.main()
