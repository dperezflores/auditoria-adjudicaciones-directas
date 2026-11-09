"""Regresión del tema y encabezado de Fase 1 sin instalar Streamlit en CI."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo
import importlib
import sys
import types
import unittest

from ui.theme import EXPECTED_DOCUMENTS, NAVIGATION, PALETTE, state_style


ROOT = Path(__file__).resolve().parents[1]


def load_components_without_streamlit():
    """Las rutinas puras de formato no deben necesitar un servidor Streamlit."""
    stub = types.ModuleType("streamlit")
    with patch.dict(sys.modules, {"streamlit": stub}):
        return importlib.import_module("ui.components")


class ThemeTests(unittest.TestCase):
    def test_palette_and_navigation_match_approved_prompt(self):
        self.assertEqual(PALETTE["acento"], "#1F4FD1")
        self.assertEqual(PALETTE["fondo"], "#F4F5F7")
        self.assertEqual(PALETTE["oscuro"], "#18212B")
        self.assertEqual(
            NAVIGATION,
            ("Expedientes", "Resultados", "Pruebas de adjudicación"),
        )
        self.assertEqual([kind for kind, _ in EXPECTED_DOCUMENTS], [
            "CONTRATO", "PUC", "CATALOGO",
            "DICTAMEN_AD", "NOTIFICACION_AD",
        ])

    def test_all_known_statuses_and_unknown_status_are_visible(self):
        for state, label in [
            ("Analizado", "Analizado"),
            ("Pendiente", "Por analizar"),
            ("Parcial", "Parcial"),
            ("Desactualizado", "Modificado"),
            ("Revisar error", "Error"),
            ("Sin registrar", "Sin registrar"),
            ("POR_IDENTIFICAR", "Sin identificar"),
            ("Falta", "Falta"),
            ("No compatible", "No compatible"),
        ]:
            with self.subTest(state=state):
                self.assertEqual(state_style(state).label, label)
        self.assertEqual(state_style("Nuevo estado backend").label,
                         "Nuevo estado backend")

    def test_svg_and_pill_escape_external_values(self):
        comps = load_components_without_streamlit()
        html = comps.pildora_estado('<script>alert("x")</script>')
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>", html)
        self.assertIn("aud-pill--other", html)
        self.assertEqual(comps.pildora_estado("Analizado").count("<svg"), 1)
        self.assertIn("currentColor", comps.icono("folder"))

    def test_sync_local_utc_and_nonexistent_date(self):
        comps = load_components_without_streamlit()
        now = datetime(2026, 11, 8, 18, 30, tzinfo=ZoneInfo("America/Mexico_City"))
        self.assertEqual(
            comps.sincronizacion_local("2026-11-09T00:20:00+00:00", now=now),
            "Revisada hace 10 min",
        )
        self.assertEqual(comps.sincronizacion_local(None, now=now), "Sin revisar")
        self.assertEqual(comps.sincronizacion_local("no-es-fecha", now=now), "Sin revisar")

    def test_header_is_top_level_and_does_not_auto_analyze(self):
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        components = (ROOT / "ui" / "components.py").read_text(encoding="utf-8")
        css = (ROOT / "ui" / "styles.css").read_text(encoding="utf-8")
        config = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
        self.assertIn('initial_sidebar_state="collapsed"', app)
        self.assertNotIn("with st.sidebar:", app)
        self.assertLess(app.index("allowed = require_access()"),
                        app.index("page = encabezado_app("))
        self.assertIn('key="ex_refresh_header"', components)
        self.assertIn('key="ex_logout_header"', components)
        self.assertIn('key="app_section"', components)
        self.assertIn("st.segmented_control(", components)
        self.assertIn("on_click=on_refresh", components)
        self.assertIn("def _refresh_from_header()", app)
        self.assertIn("_refresh_inventory()", app)
        self.assertNotIn("extract_or_reuse_", app)
        self.assertIn(".st-key-auditoria_header", css)
        self.assertIn(".st-key-ex_barra_seleccion", css)
        self.assertIn('primaryColor = "#1F4FD1"', config)


if __name__ == "__main__":
    unittest.main()
