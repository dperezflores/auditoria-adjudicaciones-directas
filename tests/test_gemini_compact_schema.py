"""Pruebas locales de esquema compacto, sin consumir ni conectar Gemini."""
from __future__ import annotations

import json
from pathlib import Path
import unittest

from pydantic import ValidationError

from services.gemini_compact_schema import (
    CAMPOS_CONTRATO, GEMINI_COMPACT_SCHEMA, convertir_respuesta_compacta,
)
from services.contract_prompt import PROMPT_VERSION


def sample():
    return {
        "campos": [
            {
                "campo": name,
                "valor": "AD-001" if name == "numero_contrato" else None,
                "pagina": 1 if name == "numero_contrato" else None,
                "evidencia": "CONTRATO AD-001" if name == "numero_contrato" else None,
            }
            for name in CAMPOS_CONTRATO
        ],
        "observaciones": ["Documento ficticio."],
    }


class CompactGeminiTests(unittest.TestCase):
    def test_structure_is_small_without_recursive_refs(self):
        text = json.dumps(GEMINI_COMPACT_SCHEMA)
        self.assertNotIn("$defs", text)
        self.assertNotIn("$ref", text)
        self.assertNotIn("additionalProperties", text)
        self.assertNotIn("maxItems", text)
        self.assertNotIn("minimum", text)
        self.assertLess(len(text), 1000)

    def test_eight_fields_are_preserved(self):
        result = convertir_respuesta_compacta(sample())
        self.assertEqual(result.numero_contrato.valor, "AD-001")
        self.assertEqual(result.numero_contrato.pagina, 1)
        self.assertEqual(result.numero_contrato.evidencia, "CONTRATO AD-001")
        self.assertEqual(result.fecha_inicio.valor, None)
        self.assertEqual(len(CAMPOS_CONTRATO), 8)

    def test_parses_json_text(self):
        result = convertir_respuesta_compacta(json.dumps(sample()))
        self.assertEqual(result.observaciones[0], "Documento ficticio.")

    def test_omitted_field_is_null_and_flagged(self):
        data = sample()
        data["campos"] = data["campos"][:-1]
        result = convertir_respuesta_compacta(data)
        self.assertIsNone(result.porcentaje_anticipo.valor)
        self.assertTrue(any("porcentaje_anticipo" in x for x in result.observaciones))

    def test_unknown_field_is_rejected(self):
        data = sample()
        data["campos"][0]["campo"] = "contrato_inventado"
        with self.assertRaises(ValueError):
            convertir_respuesta_compacta(data)

    def test_duplicate_field_is_rejected(self):
        data = sample()
        data["campos"][0]["campo"] = "fecha_inicio"
        with self.assertRaises(ValueError):
            convertir_respuesta_compacta(data)

    def test_extra_keys_are_rejected(self):
        data = sample()
        data["secreto"] = "no permitido"
        with self.assertRaises(ValueError):
            convertir_respuesta_compacta(data)

    def test_invalid_page_is_rejected(self):
        data = sample()
        data["campos"][0]["pagina"] = -1
        with self.assertRaises(ValidationError):
            convertir_respuesta_compacta(data)

    def test_malformed_json_is_rejected(self):
        with self.assertRaises(ValueError):
            convertir_respuesta_compacta("no es un objeto json")

    def test_output_validation_still_forbids_extraneous_values(self):
        data = sample()
        data["campos"][0]["no_permitido"] = "x"
        with self.assertRaises(ValueError):
            convertir_respuesta_compacta(data)

    def test_new_version_invalidates_previous_cache(self):
        self.assertEqual(PROMPT_VERSION, "contrato-prompt-v4")

    def test_offline_genai_sdk_accepts_compact_response_json_schema(self):
        # Instancia del SDK local, sin cliente ni conexión ni generación.
        from google.genai import types

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=GEMINI_COMPACT_SCHEMA,
        )
        self.assertEqual(config.response_mime_type, "application/json")
        self.assertEqual(config.response_json_schema, GEMINI_COMPACT_SCHEMA)
        self.assertIsNone(config.response_schema)

    def test_only_compact_schema_is_sent_to_provider(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "services" / "gemini_service.py").read_text(encoding="utf-8")
        self.assertIn("response_json_schema=GEMINI_RESPONSE_SCHEMA_V2", source)
        self.assertNotIn("response_schema=ExtraccionContrato", source)


if __name__ == "__main__":
    unittest.main()
