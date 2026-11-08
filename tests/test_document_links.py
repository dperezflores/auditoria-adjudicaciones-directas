"""Cruce de contrato y PUC: se consultan resultados guardados sin Gemini."""
from __future__ import annotations

import json
import unittest

from services.document_links import (
    build_supporting_documents, candidate_puc_documents, compare_puc,
    documents_for_contract, identification_note, puc_values,
)
from services.contract_portfolio import prepare_contract_portfolio
from tests.test_contract_portfolio import _contract_v2_fixture


def fixture():
    data = _contract_v2_fixture()
    work = "folderJerez001"
    data["Documentos"].append([
        "pucDocument001", work, "PUC .pdf", "",
        "application/pdf", "md5-puc", "2026", "1000",
        "Analizado", "2026", "2026", "SI", "gemini:documento-prompt-v1",
        "puc-key-current", "", "1",
    ])
    facts = [
        ("nombre_contratista", "CONSTRUCTORA DEL BAJÍO, S.A. DE C.V."),
        ("numero_de_registro", "SOPI/PUC-5455-2023"),
        ("rfc", "ABCD012345EF1"),
        ("vigencia_hasta", "9 de abril de 2027"),
        ("capital_contable", "$300,000.00"),
        ("especialidad", "OBRA DE INFRAESTRUCTURA VIAL TIPO B"),
        ("representante_legal", "LÓPEZ MARÍA"),
        ("representacion_tecnica", "RAMÍREZ JOSÉ"),
    ]
    payload = {
        "tipo_documental": "CONSTANCIA DE INSCRIPCIÓN EN EL PADRÓN ÚNICO DE CONTRATISTAS",
        "resumen": "Constancia ficticia para pruebas.",
        "campos": [
            {"campo": k, "valor": v, "pagina": 1, "evidencia": f"{k} = {v}"}
            for k, v in facts
        ],
        "alertas": ["POR VERIFICAR el original."],
    }
    data["Extracciones"].append([
        "puc-key-current", "COMPLETADO", "pucDocument001", work,
        "sha-puc", "gemini-test", "documento-prompt-v1",
        "documento-schema-v1", "", "2026-11-08",
        json.dumps(payload, ensure_ascii=False), "100", "50", "",
    ])
    data["Documentos"].append([
        "dictamenDoc01", work, "DICTAMEN TECNICO.pdf", "",
        "application/pdf", "md5-dictamen", "2026", "1000",
        "Pendiente", "2026", "2026", "SI", "", "", "", "1",
    ])
    data["Obras"].append([
        "otherWork1", "Otra obra", "", "1", "0", "0", "", "SI", "1",
    ])
    data["Documentos"].append([
        "otherPucDoc", "otherWork1", "PUC de otra obra.pdf", "",
        "application/pdf", "md5", "2026", "1000", "Analizado",
        "2026", "2026", "SI", "", "other-puc-key", "", "1",
    ])
    other = payload.copy()
    other["campos"] = [
        {"campo": "rfc", "valor": "DIF010101001", "pagina": 1, "evidencia": "DIF010101001"},
    ]
    data["Extracciones"].append([
        "other-puc-key", "COMPLETADO", "otherPucDoc", "otherWork1",
        "sha", "gemini-test", "documento-prompt-v1",
        "documento-schema-v1", "", "2026-11-08",
        json.dumps(other), "100", "50", "",
    ])
    return data


class LinkedDocumentsTests(unittest.TestCase):
    def test_puc_and_contract_associate_only_by_work_and_identifiers(self):
        portfolio = prepare_contract_portfolio(fixture())
        self.assertEqual(len(portfolio.records), 1)
        contract = portfolio.records[0]
        linked = documents_for_contract(contract, portfolio.supporting_documents)
        self.assertEqual({d.nombre for d in linked}, {"PUC .pdf", "DICTAMEN TECNICO.pdf"})
        puc = candidate_puc_documents(contract, portfolio.supporting_documents)
        self.assertEqual(len(puc), 1)
        self.assertIn("identificadores disponibles coinciden", identification_note(contract, puc[0]))

    def test_read_realistic_puc_facts_without_reanalysing(self):
        p = prepare_contract_portfolio(fixture())
        contract = p.records[0]
        doc = candidate_puc_documents(contract, p.supporting_documents)[0]
        self.assertEqual(doc.tipo, "CONSTANCIA DE INSCRIPCIÓN EN EL PADRÓN ÚNICO DE CONTRATISTAS")
        self.assertEqual(puc_values(doc)["capital_contable"]["valor"], "$300,000.00")
        self.assertEqual(puc_values(doc)["especialidad"]["valor"], "OBRA DE INFRAESTRUCTURA VIAL TIPO B")
        self.assertEqual(puc_values(doc)["vigencia_hasta"]["pagina"], 1)
        comparison = compare_puc(contract, doc)
        self.assertEqual(comparison[0].resultado, "Coincide")
        self.assertEqual(comparison[1].resultado, "Diferente")  # registros ficticios diferentes
        self.assertEqual(comparison[2].resultado, "Diferente")  # RFC ficticios diferentes
        self.assertEqual(comparison[-1].resultado, "Fecha posterior a firma")
        self.assertIn("NO demuestra inicio de vigencia", comparison[-1].detalle)

    def test_different_identifiers_flag_uncertainty_not_compliance(self):
        p = prepare_contract_portfolio(fixture())
        contract = p.records[0]
        doc = candidate_puc_documents(contract, p.supporting_documents)[0]
        self.assertIn("NO coincide", identification_note(contract, doc))
        self.assertNotIn("incumplimiento", comparison_text(compare_puc(contract, doc)))

    def test_stale_puc_is_excluded_from_comparisons(self):
        data = fixture()
        doc = next(row for row in data["Documentos"][1:] if row[0] == "pucDocument001")
        doc[8] = "Modificado desde el último análisis"
        p = prepare_contract_portfolio(data)
        self.assertFalse(candidate_puc_documents(p.records[0], p.supporting_documents))
        linked = documents_for_contract(p.records[0], p.supporting_documents)
        self.assertEqual(next(d for d in linked if d.is_puc).estado, "Desactualizado")

    def test_old_extraction_not_reused_for_new_document_version(self):
        data = fixture()
        doc = next(row for row in data["Documentos"][1:] if row[0] == "pucDocument001")
        doc[13] = "new-cache-key"
        p = prepare_contract_portfolio(data)
        self.assertFalse(candidate_puc_documents(p.records[0], p.supporting_documents))

    def test_no_cross_work_extraction_used_even_if_cache_points_to_it(self):
        data = fixture()
        puc = next(row for row in data["Documentos"][1:] if row[0] == "pucDocument001")
        puc[13] = "other-puc-key"
        p = prepare_contract_portfolio(data)
        self.assertFalse(candidate_puc_documents(p.records[0], p.supporting_documents))

    def test_pending_document_visible_but_no_fabricated_facts(self):
        p = prepare_contract_portfolio(fixture())
        docs = documents_for_contract(p.records[0], p.supporting_documents)
        pending = next(d for d in docs if d.nombre == "DICTAMEN TECNICO.pdf")
        self.assertEqual(pending.estado, "Sin análisis")
        self.assertFalse(pending.campos)


def comparison_text(items):
    return " ".join(x.resultado for x in items)


if __name__ == "__main__":
    unittest.main()
