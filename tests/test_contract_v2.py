"""Pruebas sin red para el extractor ampliado: literalidad y procedencia."""
from __future__ import annotations

import json
import unittest

from services.contract_v2 import (
    CONTRACT_V2_FIELDS, CONTRACT_V2_HEADERS, CONTRACT_SCHEMA_V2,
    GEMINI_RESPONSE_SCHEMA_V2, ContractExtractionV2, classify_cited_regime,
    parse_contract_v2,
)


def contract_payload():
    fields = [
        {
            "campo": name,
            "valor": None,
            "pagina": None,
            "evidencia": None,
        }
        for name in CONTRACT_V2_FIELDS
    ]
    for entry in fields:
        if entry["campo"] == "contratista":
            entry.update({
                "valor": "  CONSTRUCTORA 2M, S.A. DE C.V.  ",
                "pagina": 4,
                "evidencia": "La empresa CONSTRUCTORA 2M, S.A. DE C.V.",
            })
        if entry["campo"] == "numero_contrato":
            entry.update({
                "valor": "A-1810-K100288-61401-D/0117/2025",
                "pagina": 1,
                "evidencia": "No. A-1810-K100288-61401-D/0117/2025",
            })
        if entry["campo"] == "legislacion_citada":
            entry.update({
                "valor": "LEY DE OBRA PÚBLICA Y SERVICIOS RELACIONADOS CON LA MISMA PARA EL ESTADO Y LOS MUNICIPIOS DE GUANAJUATO",
                "pagina": 6,
                "evidencia": "LEY DE OBRA PÚBLICA Y SERVICIOS RELACIONADOS CON LA MISMA PARA EL ESTADO Y LOS MUNICIPIOS DE GUANAJUATO",
            })
    return {
        "campos": fields,
        "personas": [{
            "nombre": "ARQ. JUAN PÉREZ LÓPEZ",
            "cargo_o_caracter": "EL CONTRATISTA",
            "representacion": None,
            "pagina": 21,
            "evidencia": "ARQ. JUAN PÉREZ LÓPEZ — EL CONTRATISTA",
        }],
        "observaciones": ["No se encontró el origen del recurso."],
    }


class ContractV2Tests(unittest.TestCase):
    def test_16_fields_and_complete_row_width(self):
        self.assertEqual(len(CONTRACT_V2_FIELDS), 16)
        self.assertEqual(len(CONTRACT_V2_HEADERS), 23)
        self.assertEqual(CONTRACT_SCHEMA_V2, "contrato-v2")
        self.assertEqual(CONTRACT_V2_HEADERS[3], "numero_contrato")
        self.assertEqual(CONTRACT_V2_HEADERS[-1], "extraido_utc")

    def test_literal_case_spaces_punctuation_and_commas_preserved(self):
        output = parse_contract_v2(contract_payload())
        self.assertEqual(output.contratista.valor, "  CONSTRUCTORA 2M, S.A. DE C.V.  ")
        self.assertEqual(
            output.numero_contrato.valor,
            "A-1810-K100288-61401-D/0117/2025",
        )
        self.assertIsNone(output.rfc.valor)
        self.assertEqual(output.personas_participantes[0].nombre, "ARQ. JUAN PÉREZ LÓPEZ")
        self.assertEqual(output.personas_participantes[0].pagina, 21)
        self.assertEqual(len(output.flat_values()), 16)

    def test_response_json_text_and_missing_field_null(self):
        values = contract_payload()
        values["campos"] = values["campos"][:-1]
        output = parse_contract_v2(json.dumps(values, ensure_ascii=False))
        self.assertIsNone(output.legislacion_citada.valor)
        self.assertTrue(any("legislacion_citada" in x for x in output.observaciones))

    def test_unknown_duplicate_invalid_page_rejected(self):
        values = contract_payload()
        values["campos"][0]["campo"] = "inventado"
        with self.assertRaises(ValueError):
            parse_contract_v2(values)
        values = contract_payload()
        values["campos"][0]["campo"] = values["campos"][1]["campo"]
        with self.assertRaises(ValueError):
            parse_contract_v2(values)
        values = contract_payload()
        values["personas"][0]["pagina"] = -1
        with self.assertRaises(ValueError):
            parse_contract_v2(values)

    def test_municipal_is_not_derived_only_from_the_state_law_name(self):
        law = "Ley de Obra Pública y Servicios relacionados con la misma para el Estado y los Municipios de Guanajuato"
        self.assertEqual(classify_cited_regime(law), "Estatal (citado; por verificar)")
        self.assertEqual(classify_cited_regime("recursos municipales"), "No determinado")
        self.assertEqual(classify_cited_regime(None), "No determinado")

    def test_federal_and_mixed_preliminary_labels(self):
        federal = "Ley de Obras Públicas y Servicios Relacionados con las Mismas"
        state = "Ley de Obra Pública para el Estado y los Municipios de Guanajuato"
        self.assertEqual(classify_cited_regime(federal), "Federal (citado; por verificar)")
        self.assertIn("por verificar", classify_cited_regime(federal + "; " + state))

    def test_sdk_can_construct_v2_schema_without_gemini_call(self):
        from google.genai import types
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=GEMINI_RESPONSE_SCHEMA_V2,
        )
        self.assertIsNone(config.response_schema)
        self.assertEqual(config.response_json_schema, GEMINI_RESPONSE_SCHEMA_V2)
        self.assertNotIn("$defs", json.dumps(GEMINI_RESPONSE_SCHEMA_V2))
        self.assertNotIn("$ref", json.dumps(GEMINI_RESPONSE_SCHEMA_V2))


if __name__ == "__main__":
    unittest.main()
