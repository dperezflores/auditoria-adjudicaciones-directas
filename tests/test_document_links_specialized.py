"""Pruebas de cruce sobre extractores especializados que ya se guardaron."""
from __future__ import annotations

import json
import unittest

from services.contract_portfolio import prepare_contract_portfolio
from services.document_links import candidate_puc_documents, compare_puc, documents_for_contract, puc_values
from services.puc_schema import PUC_FIELDS
from services.dictamen_schema import DICTAMEN_FIELDS
from services.notificacion_schema import NOTIFICACION_FIELDS
from services.orden_schema import ORDEN_FIELDS
from tests.test_contract_portfolio import _contract_v2_fixture


SCHEMAS = (
    ("PUC", "puc-v1", PUC_FIELDS),
    ("DICTAMEN_AD", "dictamen-ad-v1", DICTAMEN_FIELDS),
    ("NOTIFICACION_AD", "notificacion-ad-v1", NOTIFICACION_FIELDS),
    ("ORDEN_AD", "orden-ad-v1", ORDEN_FIELDS),
)


def base_fixture():
    raw = _contract_v2_fixture()
    work = raw["Documentos"][1][1]
    for number, (kind, schema, keys) in enumerate(SCHEMAS, start=1):
        doc_id, cache = f"docSpecial{number}", f"keySpecial{number}"
        data = {
            field: {
                "valor": None, "pagina": None, "evidencia": None,
            } for field in keys
        }
        if "contratista" in data:
            data["contratista"] = {
                "valor": "CONSTRUCTORA DEL BAJÍO, S.A. DE C.V.",
                "pagina": 1, "evidencia": "CONSTRUCTORA DEL BAJÍO, S.A. DE C.V.",
            }
        if "rfc" in data:
            data["rfc"] = {"valor": "ABC010101AB1", "pagina": 1, "evidencia": "RFC: ABC010101AB1"}
        if kind == "PUC":
            data["numero_registro_puc"] = {
                "valor": "GTO-SOPI/PUC-5455-2023", "pagina": 1,
                "evidencia": "Registro GTO-SOPI/PUC-5455-2023",
            }
            data["vigencia_hasta"] = {
                "valor": "9 de abril de 2027", "pagina": 1, "evidencia": "Vigencia al 9 de abril de 2027",
            }
            data["capital_contable"] = {
                "valor": "$300,000.00", "pagina": 2, "evidencia": "$300,000.00",
            }
            data["especialidades"] = [{
                "categoria": "Infraestructura vial", "actividad": "Pavimentación",
                "tipo_marcado": "obra", "aportada_por": "Contratista",
                "pagina": 3, "evidencia": "PAVIMENTACIÓN",
            }]
        elif kind == "DICTAMEN_AD":
            data["fecha_emision"] = {
                "valor": "1 de mayo de 2025", "pagina": 1, "evidencia": "1 de mayo de 2025",
            }
            data["motivaciones"] = [{
                "tema": "especialidad", "afirmacion": "Acredita especialidad",
                "soporte_mencionado": "PUC", "pagina": 2, "evidencia": "PUC",
            }]
        elif kind == "NOTIFICACION_AD":
            data["fecha_emision"] = {
                "valor": "3 de mayo de 2025", "pagina": 1, "evidencia": "3 de mayo de 2025",
            }
            data["acuse_aparente"] = {
                "presencia": "indeterminada", "fecha_legible": None,
                "pagina": None, "nota_visual": None,
            }
        elif kind == "ORDEN_AD":
            data["fecha_emision"] = {
                "valor": "4 de mayo de 2025", "pagina": 1, "evidencia": "4 de mayo de 2025",
            }
            data["firma_aparente"] = {
                "presencia": "indeterminada", "pagina": None, "nota_visual": None,
            }
        data["observaciones"] = []
        raw["Documentos"].append([
            doc_id, work, kind + " .pdf", kind, "application/pdf",
            "md5xyz", "2026-11-08", "12345", "Analizado",
            "2026", "2026", "SI", "gemini-test", cache, "", "1",
        ])
        raw["Extracciones"].append([
            cache, "COMPLETADO", doc_id, work, "sha", "gemini-test",
            "prompt-test", schema, "", "2026-11-08", json.dumps(data, ensure_ascii=False),
            "20", "20", "",
        ])
    raw["Documentos"].append([
        "catalogDocTest", work, "CATALOGO.xlsx", "CATALOGO",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "md5-cat", "2026", "12000", "Analizado",
        "2026", "2026", "SI", "lector-local-xlsx", "catalogCache", "", "1",
    ])
    raw["Extracciones"].append([
        "catalogCache", "COMPLETADO", "catalogDocTest", work,
        "sha", "lector-local-xlsx", "catalogo-parser-v1",
        "catalogo-xlsx-v1", "", "2026-11-08", '{"conceptos_originales":219}',
        "", "", "",
    ])
    return raw


class SpecialistCrosscheckTests(unittest.TestCase):
    def test_all_specialized_extractors_are_visible_in_results(self):
        p = prepare_contract_portfolio(base_fixture())
        contract = p.records[0]
        linked = documents_for_contract(contract, p.supporting_documents)
        self.assertEqual(len(linked), 4)
        self.assertEqual({d.tipo for d in linked}, {
            "PUC", "DICTAMEN_AD", "NOTIFICACION_AD", "ORDEN_AD",
        })
        self.assertTrue(all(d.estado == "Analizado" for d in linked))
        self.assertEqual(len(candidate_puc_documents(contract, p.supporting_documents)), 1)

    def test_puc_specialties_capital_and_dates_are_readable(self):
        p = prepare_contract_portfolio(base_fixture())
        contract = p.records[0]
        puc = candidate_puc_documents(contract, p.supporting_documents)[0]
        facts = puc_values(puc)
        self.assertEqual(facts["capital_contable"]["valor"], "$300,000.00")
        self.assertEqual(facts["especialidad"]["pagina"], 3)
        self.assertEqual(facts["registro_puc"]["valor"], "GTO-SOPI/PUC-5455-2023")
        comparison = compare_puc(contract, puc)
        self.assertEqual(comparison[0].resultado, "Coincide")
        self.assertEqual(comparison[1].resultado, "Coincide")
        self.assertEqual(comparison[-1].resultado, "Fecha posterior a firma")

    def test_old_cache_or_changed_pdf_not_used(self):
        data = base_fixture()
        work = data["Documentos"][1][1]
        puc = next(d for d in data["Documentos"] if d[3] == "PUC")
        puc[13] = "different-cache"
        p = prepare_contract_portfolio(data)
        self.assertFalse(candidate_puc_documents(p.records[0], p.supporting_documents))
        puc[13] = "keySpecial1"
        puc[8] = "Modificado desde el último análisis"
        p = prepare_contract_portfolio(data)
        self.assertFalse(candidate_puc_documents(p.records[0], p.supporting_documents))
        self.assertEqual(next(d for d in p.supporting_documents if d.documento_id == puc[0]).estado,
                         "Desactualizado")

    def test_corrupt_specialized_payload_fails_closed(self):
        data = base_fixture()
        extraction = next(e for e in data["Extracciones"] if e[0] == "keySpecial1")
        extraction[10] = '{"nonsense":42}'
        p = prepare_contract_portfolio(data)
        puc = next(d for d in p.supporting_documents if d.documento_id == "docSpecial1")
        self.assertEqual(puc.estado, "Extracción ilegible")
        self.assertFalse(candidate_puc_documents(p.records[0], p.supporting_documents))


if __name__ == "__main__":
    unittest.main()
