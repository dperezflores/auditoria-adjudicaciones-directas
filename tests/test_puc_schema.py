"""PUC-v1: preservar literales, especialidades y evidencia de las hojas."""
from __future__ import annotations

import unittest
from pydantic import ValidationError

from services.puc_schema import (
    PUC_FIELDS, PUC_HEADERS, PUC_LABELS, PUC_SCHEMA_VERSION,
    parse_puc, PucExtractionV1,
)


def sample_puc():
    fields = [
        {"campo": key, "valor": None, "pagina": None, "evidencia": None}
        for key in PUC_FIELDS
    ]
    literal = {
        "contratista": "GUTIERREZ GUTIERREZ DE VELASCO ALEJANDRO",
        "numero_registro_puc": "GTO-SOP/PUC-5455-2023",
        "rfc": "GUGA940107FJ3",
        "capital_contable": "$352,203.00",
        "fecha_validacion": "7 de abril de 2025",
        "fecha_impresion": "5 de diciembre de 2025",
        "vigencia_hasta": "16 de mayo de 2026",
        "representacion_legal": "LA PERSONA FISICA SE REPRESENTA ASI MISMA",
        "representante_tecnico": "ARGOTE RODRIGUEZ VICTOR TOMAS",
        "cedula_profesional": "1922504",
    }
    for field in fields:
        if field["campo"] in literal:
            field.update({
                "valor": literal[field["campo"]], "pagina": 1,
                "evidencia": literal[field["campo"]],
            })
    return {
        "campos": fields,
        "especialidades": [
            {
                "categoria": "OBRA DE INFRAESTRUCTURA VIAL TIPO B",
                "actividad": "PAVIMENTACION URBANA",
                "tipo_marcado": "OBRA",
                "aportada_por": "ARGOTE RODRIGUEZ VICTOR TOMAS",
                "pagina": 1, "evidencia": "PAVIMENTACION URBANA",
            },
            {
                "categoria": "OBRA COMPLEMENTARIA DE EDIFICACION",
                "actividad": "JARDINERIA",
                "tipo_marcado": "OBRA",
                "aportada_por": "LA CONTRATISTA",
                "pagina": 1, "evidencia": "JARDINERIA",
            },
        ],
        "observaciones": ["La fecha de inicio de vigencia no se indica."],
    }


class PucSchemaTests(unittest.TestCase):
    def test_literal_values_stay_exactly_as_document(self):
        p = parse_puc(sample_puc())
        self.assertEqual(len(PUC_FIELDS), 18)
        self.assertEqual(len(PUC_HEADERS), 24)
        self.assertEqual(PUC_SCHEMA_VERSION, "puc-v1")
        self.assertEqual(p.capital_contable.valor, "$352,203.00")
        self.assertEqual(p.contratista.valor, "GUTIERREZ GUTIERREZ DE VELASCO ALEJANDRO")
        self.assertIsNone(p.vigencia_desde.valor)
        self.assertEqual(p.fecha_validacion.valor, "7 de abril de 2025")
        self.assertEqual(p.vigencia_hasta.valor, "16 de mayo de 2026")
        self.assertEqual(p.especialidades[0].actividad, "PAVIMENTACION URBANA")
        self.assertEqual(p.especialidades[1].aportada_por, "LA CONTRATISTA")
        self.assertEqual(len(p.flat_values()), len(PUC_FIELDS))
        self.assertEqual(len(PUC_LABELS), len(PUC_FIELDS))

    def test_missing_optional_fields_are_null_not_guessed(self):
        p = sample_puc()
        p["campos"] = [item for item in p["campos"] if item["campo"] != "vigencia_desde"]
        parsed = parse_puc(p)
        self.assertIsNone(parsed.vigencia_desde.valor)
        self.assertTrue(any("vigencia_desde" in x for x in parsed.observaciones))

    def test_unknown_duplicate_and_empty_puc_rejected(self):
        data = sample_puc()
        data["campos"].append(data["campos"][0])
        with self.assertRaises(ValueError):
            parse_puc(data)
        data = sample_puc()
        data["campos"][0]["campo"] = "monto_del_contrato"
        with self.assertRaises(ValueError):
            parse_puc(data)
        data = sample_puc()
        for item in data["campos"]:
            item["valor"] = None
        with self.assertRaises(ValueError):
            parse_puc(data)

    def test_invalid_specialties_rejected(self):
        data = sample_puc()
        data["especialidades"][0]["categoria"] = None
        data["especialidades"][0]["actividad"] = None
        with self.assertRaises(ValidationError):
            parse_puc(data)

    def test_json_roundtrip_preserves_evidence(self):
        parsed = parse_puc(sample_puc())
        after = PucExtractionV1.model_validate_json(parsed.model_dump_json())
        self.assertEqual(after.capital_contable.evidencia, "$352,203.00")
        self.assertEqual(after.especialidades[0].pagina, 1)


if __name__ == "__main__":
    unittest.main()
