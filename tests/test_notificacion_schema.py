"""Notificación: pruebas de fechas independientes, PUC de supervisión y plazos."""
from __future__ import annotations

import unittest

from services.notificacion_schema import (
    NOTIFICACION_FIELDS, NOTIFICACION_HEADERS, NOTIFICACION_RESPONSE_SCHEMA,
    NOTIFICACION_SCHEMA_VERSION, NotificacionAdV1, parse_notificacion,
)


def sample_notificacion():
    items = [
        {"campo": key, "valor": None, "pagina": None, "evidencia": None}
        for key in NOTIFICACION_FIELDS
    ]
    found = {
        "numero_notificacion": "DGOP/586/CONT/2025",
        "fecha_emision": "03 DE DICIEMBRE DE 2025",
        "contratista": "GUTIERREZ GUTIERREZ DE VELASCO ALEJANDRO",
        "registro_puc_contratista": "GTO-SOP/PUC-5455-2023",
        "nombre_obra": "CONSTRUCCION DE PARQUE PUBLICO",
        "modalidad_adjudicacion": "ADJUDICACION DIRECTA",
        "monto_adjudicado": "$ 2,231,632.00",
        "referencia_dictamen": "Dictamen de Autorización de Adjudicación Directa",
    }
    for item in items:
        if item["campo"] in found:
            item.update({
                "valor": found[item["campo"]],
                "pagina": 1,
                "evidencia": found[item["campo"]],
            })
    return {
        "campos": items,
        "supervisores": [{
            "funcion": "supervision_externa",
            "nombre": "LUIS GOMEZ SUMUANO",
            "cargo": "Supervisión externa",
            "registro_puc": "GTO-SOP/PUC-4044-2017",
            "pagina": 1,
            "evidencia": "LUIS GOMEZ SUMUANO GTO-SOP/PUC-4044-2017",
        }, {
            "funcion": "coordinacion_interna",
            "nombre": "EZEQUIEL MARTINEZ RODRIGUEZ",
            "cargo": "Coordinador interno",
            "registro_puc": None, "pagina": 1,
            "evidencia": "EZEQUIEL MARTINEZ RODRIGUEZ",
        }],
        "obligaciones": [{
            "obligacion": "presentarse a firmar el contrato",
            "plazo_literal": "cinco días hábiles",
            "evento_inicio_plazo": "recepción de la notificación",
            "condicion": None,
            "destinatario": "el contratista",
            "fundamento_citado": "artículo 102",
            "pagina": 1,
            "evidencia": "cinco días hábiles posteriores a la recepción",
        }, {
            "obligacion": "regularizar registro",
            "plazo_literal": "tres días hábiles",
            "evento_inicio_plazo": "recepción de la notificación",
            "condicion": "si no está vigente",
            "destinatario": "el contratista",
            "fundamento_citado": None,
            "pagina": 1,
            "evidencia": "si no está vigente",
        }],
        "fundamentos": [{
            "norma": "Ley de Obra Pública y Servicios Relacionados con la Misma",
            "articulos": "102 y 103",
            "pagina": 1, "evidencia": "artículos 102 y 103",
        }],
        "acuse_aparente": {
            "presencia": "indeterminada", "fecha_legible": None,
            "pagina": 1, "nota_visual": "Anotación sin fecha legible",
        },
        "observaciones": ["No se identifica fecha real de recepción."],
    }


class NotificacionSchemaTests(unittest.TestCase):
    def test_literal_fields_and_nested_data(self):
        parsed = parse_notificacion(sample_notificacion())
        self.assertEqual(len(NOTIFICACION_FIELDS), 21)
        self.assertEqual(len(NOTIFICACION_HEADERS), 30)
        self.assertEqual(NOTIFICACION_SCHEMA_VERSION, "notificacion-ad-v1")
        self.assertEqual(parsed.fecha_emision.valor, "03 DE DICIEMBRE DE 2025")
        self.assertIsNone(parsed.fecha_recepcion_acuse.valor)
        self.assertEqual(parsed.monto_adjudicado.valor, "$ 2,231,632.00")
        self.assertEqual(parsed.registro_puc_contratista.valor, "GTO-SOP/PUC-5455-2023")
        self.assertEqual(parsed.supervisores[0].registro_puc, "GTO-SOP/PUC-4044-2017")
        self.assertNotEqual(
            parsed.registro_puc_contratista.valor, parsed.supervisores[0].registro_puc
        )
        self.assertEqual(parsed.obligaciones[0].evento_inicio_plazo, "recepción de la notificación")
        self.assertEqual(parsed.acuse_aparente.presencia, "indeterminada")
        self.assertIsNone(parsed.acuse_aparente.fecha_legible)
        self.assertEqual(len(parsed.flat_values()), len(NOTIFICACION_FIELDS))

    def test_missing_reception_is_null_and_not_emission_date(self):
        data = sample_notificacion()
        data["campos"] = [x for x in data["campos"] if x["campo"] != "fecha_recepcion_acuse"]
        parsed = parse_notificacion(data)
        self.assertIsNone(parsed.fecha_recepcion_acuse.valor)
        self.assertIn("No devuelto por el modelo: fecha_recepcion_acuse", parsed.observaciones)

    def test_json_roundtrip_preserves_provenance(self):
        parsed = parse_notificacion(sample_notificacion())
        restored = NotificacionAdV1.model_validate_json(parsed.model_dump_json())
        self.assertEqual(restored.supervisores[0].registro_puc, "GTO-SOP/PUC-4044-2017")
        self.assertEqual(restored.obligaciones[1].condicion, "si no está vigente")

    def test_rejects_extra_unknown_or_duplicate_fields(self):
        bad = sample_notificacion()
        bad["campos"].append(bad["campos"][0])
        with self.assertRaises(ValueError):
            parse_notificacion(bad)
        bad = sample_notificacion()
        bad["campos"][0]["campo"] = "monto_contrato"
        with self.assertRaises(ValueError):
            parse_notificacion(bad)
        bad = sample_notificacion()
        bad["x"] = "intruso"
        with self.assertRaises(ValueError):
            parse_notificacion(bad)

    def test_invalid_critical_data_is_rejected(self):
        bad = sample_notificacion()
        bad["supervisores"][0]["funcion"] = "representante_tecnico"
        with self.assertRaises(ValueError):
            parse_notificacion(bad)
        bad = sample_notificacion()
        bad["acuse_aparente"]["presencia"] = "recibido"
        with self.assertRaises(ValueError):
            parse_notificacion(bad)

    def test_rejects_empty_main_identification(self):
        bad = sample_notificacion()
        for entry in bad["campos"]:
            entry["valor"] = None
        with self.assertRaises(ValueError):
            parse_notificacion(bad)

    def test_compatible_with_structured_gemini_request(self):
        from google.genai import types
        conf = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=NOTIFICACION_RESPONSE_SCHEMA,
        )
        self.assertEqual(conf.response_json_schema, NOTIFICACION_RESPONSE_SCHEMA)
        self.assertNotIn("$ref", str(NOTIFICACION_RESPONSE_SCHEMA))


if __name__ == "__main__":
    unittest.main()
