"""Pruebas del esquema literal de ORDEN_AD-v1, sin Gemini real."""
from __future__ import annotations
import unittest
from services.orden_schema import (
    ORDEN_FIELDS, ORDEN_HEADERS, ORDEN_RESPONSE_SCHEMA,
    ORDEN_SCHEMA_VERSION, OrdenAdV1, parse_orden,
)


def sample_orden():
    items = [
        {"campo": k, "valor": None, "pagina": None, "evidencia": None}
        for k in ORDEN_FIELDS
    ]
    found = {
        "numero_orden": "0589",
        "fecha_emision": "03 DE DICIEMBRE DE 2025",
        "contratista": "EMPRESA CONSTRUCTORA DEL BAJÍO, S.A. DE C.V.",
        "nombre_obra": "CONSTRUCCIÓN DE VIALIDAD",
        "localidad": "LEÓN",
        "tipo_adjudicacion": "ASIGNACIÓN DIRECTA",
        "monto_adjudicado": "$ 1,234,567.89",
        "codigo_formato": "FO-DGOP/DPP-05",
        "revision_formato": "REV. 01",
        "fecha_revision_formato": "15/05/17",
    }
    for item in items:
        if item["campo"] in found:
            item.update({"valor": found[item["campo"]], "pagina": 1,
                         "evidencia": found[item["campo"]]})
    return {
        "campos": items,
        "personal_designado": [{
            "nombre": "ING. PEDRO PÉREZ",
            "funcion": "Supervisor Interno",
            "direccion": "Dirección de Supervisión",
            "telefono": "477 123 4567",
            "pagina": 1,
            "evidencia": "NOMBRE DEL SUPERVISOR: ING. PEDRO PÉREZ",
        }],
        "instrucciones": [{
            "obligacion": "PRESENTAR EL CALENDARIO DE OBRA",
            "plazo_literal": "DOS DÍAS HÁBILES",
            "evento_inicio_plazo": "A PARTIR DE LA ENTREGA DEL PRESUPUESTO Y PLANOS AUTORIZADOS",
            "condicion": None,
            "consecuencia_literal": "QUEDARÁ DEROGADA ESTA ORDEN DE ADJUDICACIÓN",
            "destinatario": "CONTRATISTA",
            "pagina": 1,
            "evidencia": "DISPONE DE DOS DÍAS HÁBILES PARA PRESENTAR EL CALENDARIO",
        }],
        "fundamentos": [{
            "norma": "LEY DE OBRA PÚBLICA Y SERVICIOS RELACIONADOS",
            "articulos": "72", "pagina": 1, "evidencia": "ARTÍCULO 72",
        }],
        "documentos_referidos": [{
            "documento": "PLANOS",
            "finalidad": "INICIO DE LA OBRA",
            "pagina": 1,
            "evidencia": "CONTRATO, PLANOS, PRESUPUESTO Y BITÁCORA",
        }],
        "firma_aparente": {
            "presencia": "indeterminada", "pagina": 1,
            "nota_visual": "La reproducción no permite identificar una rúbrica.",
        },
        "observaciones": [],
    }


class OrdenSchemaTests(unittest.TestCase):
    def test_22_literals_and_32_columns(self):
        r = parse_orden(sample_orden())
        self.assertEqual(ORDEN_SCHEMA_VERSION, "orden-ad-v1")
        self.assertEqual(len(ORDEN_FIELDS), 22)
        self.assertEqual(len(ORDEN_HEADERS), 32)
        self.assertEqual(len(r.flat_values()), 22)
        self.assertEqual(r.monto_adjudicado.valor, "$ 1,234,567.89")
        self.assertEqual(r.fecha_emision.valor, "03 DE DICIEMBRE DE 2025")
        self.assertEqual(r.fecha_revision_formato.valor, "15/05/17")
        self.assertIsNone(r.numero_contrato_referido.valor)

    def test_preserves_supervisor_and_deadline_literal_not_derived(self):
        r = parse_orden(sample_orden())
        self.assertEqual(r.personal_designado[0].nombre, "ING. PEDRO PÉREZ")
        self.assertEqual(r.instrucciones[0].plazo_literal, "DOS DÍAS HÁBILES")
        self.assertEqual(r.instrucciones[0].evento_inicio_plazo,
            "A PARTIR DE LA ENTREGA DEL PRESUPUESTO Y PLANOS AUTORIZADOS")
        self.assertEqual(r.instrucciones[0].consecuencia_literal,
            "QUEDARÁ DEROGADA ESTA ORDEN DE ADJUDICACIÓN")
        self.assertEqual(r.documentos_referidos[0].documento, "PLANOS")
        self.assertEqual(r.fundamentos[0].articulos, "72")
        self.assertEqual(r.firma_aparente.presencia, "indeterminada")

    def test_roundtrip_and_nulls(self):
        payload = sample_orden()
        payload["campos"] = [i for i in payload["campos"] if i["campo"] != "fecha_revision_formato"]
        r = parse_orden(payload)
        self.assertIsNone(r.fecha_revision_formato.valor)
        self.assertIn("No devuelto por el modelo: fecha_revision_formato", r.observaciones)
        restored = OrdenAdV1.model_validate_json(r.model_dump_json())
        self.assertEqual(restored.instrucciones[0].plazo_literal, "DOS DÍAS HÁBILES")

    def test_reject_invalid_and_duplicate(self):
        payload=sample_orden()
        payload["campos"].append(payload["campos"][0])
        with self.assertRaises(ValueError):
            parse_orden(payload)
        payload=sample_orden()
        payload["fundamentos"][0]["norma"]=None
        payload["fundamentos"][0]["articulos"]=None
        with self.assertRaises(ValueError):
            parse_orden(payload)
        payload=sample_orden()
        for f in payload["campos"]:
            f["valor"]=None
        with self.assertRaises(ValueError):
            parse_orden(payload)

    def test_compatible_gemini_schema(self):
        from google.genai import types
        cfg=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=ORDEN_RESPONSE_SCHEMA,
        )
        self.assertEqual(cfg.response_json_schema, ORDEN_RESPONSE_SCHEMA)
        self.assertNotIn("$ref", str(ORDEN_RESPONSE_SCHEMA))


if __name__ == "__main__":
    unittest.main()
