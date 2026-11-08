"""Regresión: nunca sobrescribir el estado controlado por un widget Streamlit.

El diagnóstico usa un botón con key='gemini_model_check' y almacena el
resultado de la API bajo otra clave independiente.
"""
from pathlib import Path
import ast
import unittest


class WidgetStateTests(unittest.TestCase):
    def test_no_state_assignment_collides_with_static_widget_key(self):
        path = Path(__file__).resolve().parents[1] / "ui" / "drive_explorer.py"
        root = ast.parse(path.read_text(encoding="utf-8"))
        widget_keys = set()
        assigned = set()
        controls = {"button", "checkbox", "selectbox", "text_input", "radio", "slider"}

        for node in ast.walk(root):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in controls:
                if isinstance(func.value, ast.Name) and func.value.id == "st":
                    for kw in node.keywords:
                        if kw.arg == "key" and isinstance(kw.value, ast.Constant):
                            if isinstance(kw.value.value, str):
                                widget_keys.add(kw.value.value)
        for node in ast.walk(root):
            if not isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Attribute):
                    parent = target.value
                    if isinstance(parent, ast.Attribute) and parent.attr == "session_state":
                        if isinstance(parent.value, ast.Name) and parent.value.id == "st":
                            assigned.add(target.attr)
                if isinstance(target, ast.Subscript):
                    parent = target.value
                    if isinstance(parent, ast.Attribute) and parent.attr == "session_state":
                        if isinstance(parent.value, ast.Name) and parent.value.id == "st":
                            index = target.slice
                            if isinstance(index, ast.Constant) and isinstance(index.value, str):
                                assigned.add(index.value)
        self.assertFalse(
            widget_keys.intersection(assigned),
            f"Claves de widget sobrescritas directamente: {widget_keys.intersection(assigned)}",
        )

    def test_diagnostic_uses_separate_result_key(self):
        source = (Path(__file__).resolve().parents[1] / "ui" / "drive_explorer.py").read_text(encoding="utf-8")
        self.assertIn('key="gemini_model_check"', source)
        self.assertIn('st.session_state["gemini_diagnostic_result"] = (model, check)', source)
        self.assertIn('st.session_state.get("gemini_diagnostic_result")', source)


if __name__ == "__main__":
    unittest.main()
