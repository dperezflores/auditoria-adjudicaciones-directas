"""Pruebas sin API de la extracción literal DICTAMEN_AD-v1."""
from __future__ import annotations

import unittest

from services.dictamen_schema import (
    DICTAMEN_FIELDS, DICTAMEN_HEADERS, DICTAMEN_LABELS,
    DICTAMEN_RESPONSE_SCHEMA, DICTAMEN_SCHEMA_VERSION,
    DictamenAdV1, parse_dictamen,
)


def sample_dictamen():
    fields = [
        {"campo": name, "valor": None, "pagina": None, "evidencia": None}
        for name in DICTAMEN_FIELDS
    ]
    samples = {
        "numero_dictamen": "DGOP/586/CONT/2025",
        "fecha_emision": "03 DE DICIEMBRE DE 2025",
        "nombre_obra": "OBRA PP 1715 LA CONSTRUCCION DE PARQUE PUBLICO",
        "contratista": "GUTIERREZ GUTIERREZ DE VELASCO ALEJANDRO",
        "registro_puc": "GTO-SOP/PUC-5455-2023",
        "modalidad_adjudicacion": "DIRECTA",
        "monto_asignado": "$ 2,231,632.00",
        "fecha_probable_inicio": "15-12-25",
        "plazo_ejecucion": "16 SEMANAS",
        "autoridad_firmante": "Arq. Laura Elena Becerra García",
        "cargo_autoridad": "Directora General de Obra Pública",
    }
    for field in fields:
        if field["campo"] in samples:
            field.update({
                "valor": samples[field["campo"]],
                "pagina": 1,
                "evidencia": samples[field["campo"]],
            })
    return {
        "campos": fields,
        "fundamentos": [{
            "norma": "Ley de Obra Pública y Servicios Relacionados con la Misma para el Estado y los Municipios de Guanajuato",
            "articulos": "76",
            "texto_citado": None,
            "pagina": 1,
            "evidencia": "artículo 76 de la Ley de Obra Pública",
        }],
        "motivaciones": [{
            "tema": "vigencia_puc",
            "afirmacion": "el contratista cuenta con registro vigente en el padrón",
            "soporte_mencionado": "Padrón Único de Contratistas",
            "pagina": 1,
            "evidencia": "el contratista cuenta con registro vigente en el padrón",
        }, {
            "tema": "experiencia",
            "afirmacion": "cuenta con experiencia para ejecutar los trabajos",
            "soporte_mencionado": None,
            "pagina": 1,
            "evidencia": "cuenta con experiencia para ejecutar los trabajos",
        }],
        "soportes": [{
            "documento": "Padrón Único de Contratistas",
            "finalidad_citada": "registro vigente",
            "pagina": 1,
            "evidencia": "Padrón Único de Contratistas",
        }],
        "firma_aparente": {
            "presencia": "indeterminada",
            "pagina": 1,
            "nota_visual": "La imagen no permite corroborar autenticidad.",
        },
        "observaciones": [],
    }


class DictamenSchemaTests(unittest.TestCase):
    def test_19_literals_and_28_sheet_columns(self):
        self.assertEqual(DICTAMEN_SCHEMA_VERSION, "dictamen-ad-v1")
        self.assertEqual(len(DICTAMEN_FIELDS), 19)
        self.assertEqual(len(DICTAMEN_LABELS), 19)
        self.assertEqual(len(DICTAMEN_HEADERS), 28)
        d = parse_dictamen(sample_dictamen())
        self.assertEqual(d.numero_dictamen.valor, "DGOP/586/CONT/2025")
        self.assertEqual(d.fecha_emision.valor, "03 DE DICIEMBRE DE 2025")
        self.assertEqual(d.monto_asignado.valor, "$ 2,231,632.00")
        self.assertIsNone(d.fecha_revision_formato.valor)
        self.assertEqual(len(d.flat_values()), 19)

    def test_fundamentos_motivaciones_soportes_y_firma_no_se_confunden(self):
        d = parse_dictamen(sample_dictamen())
        self.assertEqual(d.fundamentos[0].articulos, "76")
        self.assertEqual(d.motivaciones[0].tema, "vigencia_puc")
        self.assertEqual(d.soportes[0].documento, "Padrón Único de Contratistas")
        self.assertEqual(d.firma_aparente.presencia, "indeterminada")
        self.assertEqual(DictamenAdV1.model_validate_json(d.model_dump_json()).monto_asignado.valor, "$ 2,231,632.00")

    def test_no_inventa_fechas_de_formato_si_no_estan_presentes(self):
        d = sample_dictamen()
        d["campos"] = [x for x in d["campos"] if x["campo"] != "fecha_revision_formato"]
        report = parse_dictamen(d)
        self.assertIsNone(report.fecha_revision_formato.valor)
        self.assertIn(
            "No devuelto por el modelo: fecha_revision_formato",
            report.observaciones,
        )

    def test_fundamento_inexistente_y_tema_invalido_son_rechazados(self):
        payload = sample_dictamen()
        payload["fundamentos"][0]["norma"] = None
        payload["fundamentos"][0]["articulos"] = None
        with self.assertRaises(ValueError):
            parse_dictamen(payload)
        payload = sample_dictamen()
        payload["motivaciones"][0]["tema"] = "incumplimiento"
        with self.assertRaises(ValueError):
            parse_dictamen(payload)

    def test_duplicados_y_falta_de_identidad_rechazados(self):
        payload = sample_dictamen()
        payload["campos"].append(payload["campos"][0])
        with self.assertRaises(ValueError):
            parse_dictamen(payload)
        payload = sample_dictamen()
        for entry in payload["campos"]:
            entry["valor"] = None
        with self.assertRaises(ValueError):
            parse_dictamen(payload)

    def test_google_json_schema_sin_referencias_modelo(self):
        from google.genai import types
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=DICTAMEN_RESPONSE_SCHEMA,
        )
        self.assertEqual(config.response_json_schema, DICTAMEN_RESPONSE_SCHEMA)
        self.assertNotIn("$defs", str(DICTAMEN_RESPONSE_SCHEMA))
        self.assertNotIn("$ref", str(DICTAMEN_RESPONSE_SCHEMA))


if __name__ == "__main__":
    unittest.main()
