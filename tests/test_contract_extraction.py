"""Pruebas de contrato y caché sin llamadas a IA."""
import unittest
from pydantic import ValidationError
from services.contract_schema import DatoConEvidencia, ExtraccionContrato, SCHEMA_VERSION
from services.contract_prompt import PROMPT_VERSION
from services.extraction_cache import crear_clave_cache


def example(**kwargs):
    base = {
        "numero_contrato": {"valor": "AD-001-2026", "pagina": 1, "evidencia": "Contrato AD-001-2026"},
        "nombre_obra": {"valor": None, "pagina": None, "evidencia": None},
        "contratista": {"valor": "Contratista de Prueba", "pagina": 2, "evidencia": "Contratista de Prueba"},
        "fecha_firma": {"valor": None, "pagina": None, "evidencia": None},
        "fecha_inicio": {"valor": None, "pagina": None, "evidencia": None},
        "fecha_termino": {"valor": None, "pagina": None, "evidencia": None},
        "monto_con_iva": {"valor": None, "pagina": None, "evidencia": None},
        "porcentaje_anticipo": {"valor": None, "pagina": None, "evidencia": None},
        "observaciones": [],
    }
    base.update(kwargs)
    return base


class SchemaTests(unittest.TestCase):
    def test_good_document(self):
        a = ExtraccionContrato.model_validate(example())
        self.assertEqual(a.numero_contrato.pagina, 1)
        self.assertEqual(a.campos_que_requieren_revision(), [])

    def test_missing_fields_are_not_guessed(self):
        a = ExtraccionContrato.model_validate(example())
        self.assertIsNone(a.fecha_inicio.valor)

    def test_uncited_value_requires_review(self):
        a = ExtraccionContrato.model_validate(example(contratista={"valor": "XYZ", "pagina": 1, "evidencia": None}))
        self.assertEqual(a.campos_que_requieren_revision(), ["contratista"])

    def test_invalid_page_rejected(self):
        with self.assertRaises(ValidationError):
            DatoConEvidencia.model_validate({"valor": "ABC", "pagina": 0, "evidencia": "ABC"})

    def test_unknown_field_rejected(self):
        with self.assertRaises(ValidationError):
            ExtraccionContrato.model_validate(example(numero_desconocido="X"))

    def test_empty_string_becomes_null(self):
        x = DatoConEvidencia.model_validate({"valor": "  ", "pagina": None, "evidencia": " "})
        self.assertIsNone(x.valor)
        self.assertIsNone(x.evidencia)


class CacheTests(unittest.TestCase):
    def cache(self, b: bytes, **kwargs):
        return crear_clave_cache(
            b,
            modelo=kwargs.get("modelo", "gemini-model-test"),
            version_prompt=kwargs.get("prompt", PROMPT_VERSION),
            version_esquema=kwargs.get("schema", SCHEMA_VERSION),
        )

    def test_same_bytes_same_key(self):
        self.assertEqual(self.cache(b"%PDF-1.7 test").clave, self.cache(b"%PDF-1.7 test").clave)

    def test_modified_bytes_change_key(self):
        self.assertNotEqual(self.cache(b"%PDF-1.7 test").clave, self.cache(b"%PDF-1.7 test plus page").clave)

    def test_new_model_or_prompt_changes_key(self):
        self.assertNotEqual(self.cache(b"%PDF-1.7 test").clave, self.cache(b"%PDF-1.7 test", modelo="other").clave)
        self.assertNotEqual(self.cache(b"%PDF-1.7 test").clave, self.cache(b"%PDF-1.7 test", prompt="new").clave)

    def test_invalid_pdf_rejected(self):
        with self.assertRaises(ValueError):
            self.cache(b"not-a-pdf")


if __name__ == "__main__":
    unittest.main()
