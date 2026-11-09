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

    def test_results_view_identifies_unique_amount_release(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "ui" / "resultados.py").read_text(encoding="utf-8")
        self.assertIn("Versión de vista: monto único v2", source)
        self.assertIn('key="results_contract_table_v2_monto_unico"', source)
        self.assertIn('"Monto del contrato": st.column_config.TextColumn', source)
        self.assertNotIn('"Monto del contrato con IVA": st.column_config', source)
        self.assertNotIn('"Monto del contrato sin IVA": st.column_config', source)

    def test_specialized_puc_and_dictamen_extractors_and_pdf_link(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "ui" / "expedientes.py").read_text(encoding="utf-8")
        self.assertNotIn('"Plantilla de extracción"', source)
        self.assertNotIn("ex_analysis_choice", source)
        self.assertNotIn("analysis_choice", source)
        self.assertNotIn("analyze_document(", source)
        self.assertIn("extract_or_reuse_puc(", source)
        self.assertIn('if code == "PUC":', source)
        self.assertIn('elif code == "DICTAMEN_AD":', source)
        self.assertIn('extract_or_reuse_dictamen(', source)
        self.assertIn('"DICTAMEN_AD": "dictamen-ad-v1"', source)
        self.assertIn('elif code == "NOTIFICACION_AD":', source)
        self.assertIn('extract_or_reuse_notificacion(', source)
        self.assertIn('elif code == "ORDEN_AD":', source)
        self.assertIn('extract_or_reuse_orden(', source)
        self.assertIn('"ORDEN_AD": "orden-ad-v1"', source)
        self.assertIn('old["version_esquema"] == "orden-ad-v1"', source)
        self.assertIn("#### Instrucciones, condiciones y plazos", source)
        self.assertIn('"NOTIFICACION_AD": "notificacion-ad-v1"', source)
        self.assertIn('old["version_esquema"] == "notificacion-ad-v1"', source)
        self.assertIn("#### Obligaciones y plazos comunicados", source)
        self.assertIn("#### Acuse aparente", source)
        self.assertIn('key="ex_analyze"', source)
        self.assertIn('"Tipo documental": guess_from_name(d.name, d.mime_type).label', source)
        self.assertIn("Eliminar análisis guardado de este archivo", source)
        self.assertIn("delete_analysis(", source)
        self.assertIn('typed != "ELIMINAR"', source)
        self.assertNotIn("render_classification(inventory)", source)
        self.assertNotIn("Verificar tipo por contenido (sin IA)", source)
        self.assertIn('disabled = not batch or (requires_gemini and not gemini.get("api_key"))', source)
        self.assertIn('f"Analizar {len(batch)} documento(s) con IA y/o importar Excel"', source)
        self.assertIn('saved["version_esquema"] == schema', source)
        self.assertIn('old["version_esquema"] == "dictamen-ad-v1"', source)
        self.assertIn('old["version_esquema"] == "puc-v1"', source)
        self.assertLess(
            source.index('_summarize_saved(preview, st.session_state["ex_status_tables"], current_state)'),
            source.index('"Ver documento en Drive"'),
        )


if __name__ == "__main__":
    unittest.main()
