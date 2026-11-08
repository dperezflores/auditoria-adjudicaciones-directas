"""Portafolio contractual: integridad de versiones, agregados y filtros.

Todos los datos son ficticios; pruebas sin acceso a Sheets ni llamadas a IA.
"""
from __future__ import annotations

import json
import unittest
from decimal import Decimal

from services.contract_v2 import CONTRACT_V2_FIELDS, parse_contract_v2

from services.contract_portfolio import (
    DATA_FIELDS, HEADERS, PortfolioError, amount_summary, currency_group,
    filter_contracts, money_text, parse_amount, prepare_contract_portfolio,
    read_contract_portfolio, signature_year,
)

WORK = "folderJerez001"
DOCUMENT = "contractJerez001"
KEY = "cacheCurrent001"


def dataset():
    works = [list(HEADERS["Obras"]),
             [WORK, "Cerrito de Jerez", "", "1", "0", "0", "", "SI", "1"],
             ["folderInactive", "Obra ficticia", "", "1", "0", "0", "", "NO", "1"]]
    documents = [
        list(HEADERS["Documentos"]),
        [DOCUMENT, WORK, "CONTRATO.pdf", "", "application/pdf",
         "md5real", "", "21000000", "Analizado", "", "", "SI",
         "gemini:contrato-prompt-v3", KEY, "", "1"],
        ["docInactive", "folderInactive", "SIMULADO.pdf", "", "application/pdf",
         "md5fake", "", "2000", "Analizado", "", "", "NO",
         "gemini:contrato-prompt-v3", "cacheFake", "", "1"],
    ]
    values = {
        "numero_contrato": "A-117/2025",
        "nombre_obra": "Rehabilitación de caminos principales",
        "contratista": "CONSTRUCTORA DEL BAJÍO",
        "fecha_firma": "05 días del mes de Mayo del año de 2025",
        "fecha_inicio": "02 de junio de 2025",
        "fecha_termino": "26 de julio de 2025",
        "monto_con_iva": "$2,350,150.88",
        "porcentaje_anticipo": "30%",
    }
    extraction = {
        key: {"valor": value, "pagina": 1, "evidencia": f"Texto de {key}"}
        for key, value in values.items()
    }
    extraction["observaciones"] = []
    analyses = [
        list(HEADERS["Extracciones"]),
        [KEY, "COMPLETADO", DOCUMENT, WORK, "hash", "gemini-3.5-flash-lite",
         "contrato-prompt-v3", "contrato-v1", "", "2026-11-08T06:19:03Z",
         json.dumps(extraction), "12322", "736", ""],
        ["cacheFake", "COMPLETADO", "docInactive", "folderInactive",
         "hash", "gemini-3.5-flash-lite", "contrato-prompt-v3", "contrato-v1",
         "", "", json.dumps(extraction), "0", "0", ""],
    ]
    rows = [
        list(HEADERS["DatosContrato"]),
        [KEY, WORK, DOCUMENT, *[values[field] for field in DATA_FIELDS],
         "", "2026-11-08T06:18:57Z"],
        ["cacheFake", "folderInactive", "docInactive",
         *[values[field] for field in DATA_FIELDS],
         "", "2026-11-08"],
    ]
    return {
        "Obras": works,
        "Documentos": documents,
        "Extracciones": analyses,
        "DatosContrato": rows,
        "DatosContratoV2": [list(HEADERS["DatosContratoV2"])],
    }


class PortfolioTests(unittest.TestCase):
    def test_works_are_built_from_contracts_not_folders(self):
        portfolio = prepare_contract_portfolio(dataset())
        self.assertEqual(portfolio.works_count, 1)
        self.assertEqual(len(portfolio.records), 1)
        record = portfolio.records[0]
        self.assertEqual(record.values["numero_contrato"], "A-117/2025")
        self.assertEqual(record.signature_year, "2025")
        self.assertEqual(record.coverage, "8/8")
        self.assertEqual(record.evidence["numero_contrato"]["pagina"], 1)
        self.assertEqual(record.amount, Decimal("2350150.88"))

    def test_filter_search_ignores_accents(self):
        portfolio = prepare_contract_portfolio(dataset())
        self.assertEqual(len(filter_contracts(portfolio, query="rehabilitacion")), 1)
        self.assertEqual(len(filter_contracts(portfolio, query="A-117/2025")), 1)
        self.assertEqual(len(filter_contracts(portfolio, query="no existe")), 0)

    def test_filters_year_and_contractor(self):
        portfolio = prepare_contract_portfolio(dataset())
        self.assertEqual(len(filter_contracts(portfolio, year="2025")), 1)
        self.assertEqual(len(filter_contracts(portfolio, year="2024")), 0)
        self.assertEqual(
            len(filter_contracts(portfolio, contractor="CONSTRUCTORA DEL BAJÍO")), 1
        )

    def test_finished_old_version_is_not_counted(self):
        data = dataset()
        data["Documentos"][1][13] = "cacheNew"
        self.assertEqual(len(prepare_contract_portfolio(data).records), 0)

    def test_modified_or_inactive_pdf_excluded(self):
        data = dataset()
        data["Documentos"][1][8] = "Modificado desde el último análisis"
        self.assertEqual(len(prepare_contract_portfolio(data).records), 0)
        data = dataset()
        data["Documentos"][1][11] = "NO"
        self.assertEqual(len(prepare_contract_portfolio(data).records), 0)

    def test_partial_data_visible_as_partial_without_inventing_evidence(self):
        data = dataset()
        data["Extracciones"][1][1] = "REQUIERE_REVISION"
        data["Extracciones"][1][10] = ""
        data["DatosContrato"][1][10] = ""
        portfolio = prepare_contract_portfolio(data)
        self.assertEqual(len(portfolio.records), 1)
        self.assertEqual(portfolio.records[0].status_label, "Recuperación parcial")
        self.assertEqual(portfolio.records[0].completeness, 7)
        self.assertFalse(portfolio.records[0].evidence)

    def test_a_puc_is_not_contract(self):
        data = dataset()
        data["Extracciones"][1][7] = "documento-schema-v1"
        self.assertEqual(len(prepare_contract_portfolio(data).records), 0)

    def test_invalid_headers_fail_without_guessing(self):
        data = dataset()
        data["DatosContrato"][0][3] = "numero_incorrecto"
        with self.assertRaisesRegex(PortfolioError, "Encabezados"):
            prepare_contract_portfolio(data)

    def test_duplicate_current_contract_rejected(self):
        data = dataset()
        data["DatosContrato"].append(data["DatosContrato"][1].copy())
        with self.assertRaisesRegex(PortfolioError, "duplicada"):
            prepare_contract_portfolio(data)

    def test_missing_amount_still_in_list_no_fabricated_total(self):
        data = dataset()
        data["DatosContrato"][1][9] = ""
        portfolio = prepare_contract_portfolio(data)
        self.assertIsNone(portfolio.records[0].amount)
        amount, explanation, missing = amount_summary(portfolio.records)
        self.assertIsNone(amount)
        self.assertEqual(missing, 1)
        self.assertIn("Sin importes", explanation)

    def test_money_parsing_mexican_and_other_format(self):
        self.assertEqual(parse_amount("$2,350,150.88"), Decimal("2350150.88"))
        self.assertEqual(parse_amount("$1.234.567,89"), Decimal("1234567.89"))
        self.assertEqual(parse_amount("$2500"), Decimal("2500"))
        self.assertIsNone(parse_amount("No localizado"))
        self.assertIsNone(parse_amount("$10 y $20"))

    def test_mixed_currencies_are_never_aggregated(self):
        data = dataset()
        data["Obras"].append(["folderOther", "Otra obra", "", "1", "0", "0", "", "SI", "1"])
        data["Documentos"].append([
            "documentOther", "folderOther", "otro.pdf", "", "application/pdf", "md5",
            "", "1000", "Analizado", "", "", "SI", "", "cacheOther", "", "1",
        ])
        old = data["Extracciones"][1].copy()
        old[0], old[2], old[3] = "cacheOther", "documentOther", "folderOther"
        data["Extracciones"].append(old)
        row = data["DatosContrato"][1].copy()
        row[0], row[1], row[2] = "cacheOther", "folderOther", "documentOther"
        row[9] = "USD 2000.00"
        data["DatosContrato"].append(row)
        portfolio = prepare_contract_portfolio(data)
        amount, description, missing = amount_summary(portfolio.records)
        self.assertIsNone(amount)
        self.assertIn("Monedas distintas", description)

    def test_signature_year_does_not_guess(self):
        self.assertEqual(signature_year("05 de mayo de 2025"), "2025")
        self.assertEqual(signature_year("2024 y 2025"), "Sin año")
        self.assertEqual(signature_year("Sin fecha"), "Sin año")
        self.assertEqual(currency_group("MXN $1,000"), "MXN")
        self.assertEqual(money_text(Decimal("2500.00"), "MXN"), "$2,500.00 MXN")


def _generic_contract_dataset():
    data = dataset()
    data["Obras"].append([
        "workUyepac", "00_591_25_ParqueUyepac", "", "3", "2", "0", "", "SI", "1",
    ])
    data["Documentos"].append([
        "docUyepac", "workUyepac", "CNT_DIR_CNT.pdf", "",
        "application/pdf", "md5Uyepac", "", "20857265", "Analizado",
        "", "", "SI", "gemini:documento-prompt-v1", "cacheGeneral", "", "1",
    ])
    labels = [
        ("Número de Contrato", "A-1816-K100288-62201-E/0591/2025"),
        ("Objeto de la Obra", "Construcción de parque público Uyepac"),
        ("Contratista", "Arq. Alejandro Gutiérrez Gutiérrez de Velasco"),
        ("Fecha de Firma del Contrato", "04 de diciembre de 2025"),
        ("Fecha de Inicio de Obra", "15 de diciembre de 2025"),
        ("Fecha de Terminación de Obra", "04 de abril de 2026"),
        ("Monto del Contrato", "$2,231,632.00"),
        ("Anticipo", "30%"),
    ]
    facts = [
        {"campo": k, "valor": v, "pagina": 1, "evidencia": f"Documento: {v}"}
        for k, v in labels
    ]
    payload = {
        "tipo_documental": "Contrato de Obra Pública",
        "resumen": "Monto total de $2,231,632.00 IVA incluido.",
        "campos": facts,
        "alertas": [],
    }
    data["Extracciones"].append([
        "cacheGeneral", "COMPLETADO", "docUyepac", "workUyepac",
        "hash", "gemini-3.5-flash-lite", "documento-prompt-v1",
        "documento-schema-v1", "", "2026-11-08",
        json.dumps(payload), "100", "100", "",
    ])
    return data


class GeneralContractPortfolioTests(unittest.TestCase):
    def test_generic_contract_extracted_without_new_api_call(self):
        portfolio = prepare_contract_portfolio(_generic_contract_dataset())
        self.assertEqual(portfolio.works_count, 2)
        self.assertEqual(len(portfolio.records), 2)
        general = next(r for r in portfolio.records if r.source_schema == "documento-schema-v1")
        self.assertEqual(general.values["numero_contrato"], "A-1816-K100288-62201-E/0591/2025")
        self.assertEqual(general.values["contratista"], "Arq. Alejandro Gutiérrez Gutiérrez de Velasco")
        self.assertEqual(general.values["monto_con_iva"], "$2,231,632.00")
        self.assertEqual(general.values["porcentaje_anticipo"], "30%")
        self.assertEqual(general.coverage, "8/8")
        self.assertEqual(general.evidence["numero_contrato"]["pagina"], 1)
        self.assertIn("extracción general", general.status_label)
        total, explanation, missing = amount_summary(portfolio.records)
        self.assertEqual(total, Decimal("4581782.88"))
        self.assertEqual(missing, 0)

    def test_generic_contract_does_not_require_flat_data_row(self):
        data = _generic_contract_dataset()
        self.assertEqual(len(data["DatosContrato"]), 3)
        self.assertEqual(len(prepare_contract_portfolio(data).records), 2)

    def test_generic_contract_not_counted_if_inactive_or_old(self):
        data = _generic_contract_dataset()
        data["Documentos"][-1][11] = "NO"
        self.assertEqual(len(prepare_contract_portfolio(data).records), 1)
        data = _generic_contract_dataset()
        data["Documentos"][-1][13] = "different-version"
        self.assertEqual(len(prepare_contract_portfolio(data).records), 1)

    def test_non_contract_document_excluded(self):
        data = _generic_contract_dataset()
        payload = json.loads(data["Extracciones"][-1][10])
        payload["tipo_documental"] = "Padrón Único de Contratistas"
        data["Extracciones"][-1][10] = json.dumps(payload)
        self.assertEqual(len(prepare_contract_portfolio(data).records), 1)

    def test_amount_does_not_claim_iva_without_source(self):
        data = _generic_contract_dataset()
        payload = json.loads(data["Extracciones"][-1][10])
        payload["resumen"] = "Contrato por importe $2,231,632.00."
        data["Extracciones"][-1][10] = json.dumps(payload)
        portfolio = prepare_contract_portfolio(data)
        general = next(r for r in portfolio.records if r.source_schema == "documento-schema-v1")
        self.assertEqual(general.values["monto_con_iva"], "")
        self.assertIsNone(general.amount)


def _contract_v2_fixture():
    data = dataset()
    fields = [
        {"campo": name, "valor": None, "pagina": None, "evidencia": None}
        for name in CONTRACT_V2_FIELDS
    ]
    literal = {
        "numero_contrato": "A-117/2025",
        "obra_servicio": "OBRA PP Z1867, REHABILITACIÓN DE CAMINOS.",
        "tipo_contrato": "A PRECIOS UNITARIOS Y TIEMPO DETERMINADO",
        "contratista": "CONSTRUCTORA DEL BAJÍO, S.A. DE C.V.",
        "registro_puc": "GTO-SOPI/PUC-5455-2023",
        "rfc": "ABC010101AB1",
        "representante_legal": "ARQ. JOSE LUIS, S.A.",
        "representante_tecnico": "ING. CÉSAR RAMÍREZ",
        "modalidad_adjudicacion": "ADJUDICACIÓN DIRECTA",
        "monto_contrato": "$2,350,150.88",
        "fecha_inicio_contractual": "02 de Junio de 2025",
        "fecha_termino_contractual": "26 de Julio de 2025",
        "fecha_firma_contrato": "05 de Mayo de 2025",
        "anticipo": "30%",
        "fuente_financiamiento": "Recursos Municipales",
        "legislacion_citada": "Ley de Obra Pública y Servicios relacionados con la misma para el Estado y los Municipios de Guanajuato",
    }
    for item in fields:
        if item["campo"] in literal:
            item.update({
                "valor": literal[item["campo"]],
                "pagina": 1,
                "evidencia": literal[item["campo"]],
            })
    result = parse_contract_v2({
        "campos": fields,
        "personas": [{
            "nombre": "ARQ. JOSE LUIS, S.A.",
            "cargo_o_caracter": "REPRESENTANTE LEGAL",
            "representacion": "CONSTRUCTORA DEL BAJÍO, S.A. DE C.V.",
            "pagina": 22,
            "evidencia": "ARQ. JOSE LUIS, S.A.",
        }],
        "observaciones": [],
    })
    key = "cacheV2Current"
    data["Documentos"][1][13] = key
    data["Extracciones"].append([
        key, "COMPLETADO", DOCUMENT, WORK, "hash", "gemini-3.5-flash-lite",
        "contrato-prompt-v4", "contrato-v2", "",
        "2026-11-08", result.model_dump_json(exclude_none=False),
        "800", "300", "",
    ])
    data["DatosContratoV2"].append([
        key, WORK, DOCUMENT, *result.flat_values(),
        json.dumps([p.model_dump(mode="json") for p in result.personas_participantes], ensure_ascii=False),
        "Estatal (citado; por verificar)", "[]", "2026-11-08",
    ])
    return data


class ContractPortfolioV2Tests(unittest.TestCase):
    def test_new_schema_upgrades_same_contract_without_double_count(self):
        result = prepare_contract_portfolio(_contract_v2_fixture())
        self.assertEqual(result.works_count, 1)
        self.assertEqual(len(result.records), 1)
        record = result.records[0]
        self.assertEqual(record.source_schema, "contrato-v2")
        self.assertEqual(record.coverage, "16/16")
        self.assertEqual(record.values["numero_contrato"], "A-117/2025")
        self.assertEqual(record.full_values["tipo_contrato"], "A PRECIOS UNITARIOS Y TIEMPO DETERMINADO")
        self.assertEqual(record.full_values["representante_tecnico"], "ING. CÉSAR RAMÍREZ")
        self.assertEqual(record.full_values["fuente_financiamiento"], "Recursos Municipales")
        self.assertEqual(record.participants[0]["pagina"], 22)
        self.assertEqual(record.normative_scope, "Estatal (citado; por verificar)")
        self.assertEqual(record.missing_fields, ())

    def test_v2_literal_values_not_rewritten_or_normalized(self):
        data = _contract_v2_fixture()
        doc = data["DatosContratoV2"][1]
        idx = 3 + CONTRACT_V2_FIELDS.index("contratista")
        original = "  CO.NST, S.A. DE C.V.  "
        doc[idx] = original
        source = json.loads(data["Extracciones"][-1][10])
        source["contratista"]["valor"] = original
        data["Extracciones"][-1][10] = json.dumps(source, ensure_ascii=False)
        record = prepare_contract_portfolio(data).records[0]
        self.assertEqual(record.full_values["contratista"], original)

    def test_v2_mismatch_between_derived_row_and_json_is_detected(self):
        data = _contract_v2_fixture()
        idx = 3 + CONTRACT_V2_FIELDS.index("monto_contrato")
        data["DatosContratoV2"][1][idx] = "$3,000,000.00"
        with self.assertRaises(PortfolioError):
            prepare_contract_portfolio(data)

    def test_old_and_new_document_formats_coexist(self):
        data = _contract_v2_fixture()
        data["Obras"].append([
            "oldFolder", "Obra con contrato antiguo", "", "1", "0",
            "0", "", "SI", "1",
        ])
        original = data["Documentos"][1].copy()
        original[0], original[1], original[13] = "oldDoc", "oldFolder", "oldCache"
        data["Documentos"].append(original)
        row = data["DatosContrato"][1].copy()
        row[0], row[1], row[2] = "oldCache", "oldFolder", "oldDoc"
        data["DatosContrato"].append(row)
        prev = data["Extracciones"][1].copy()
        prev[0], prev[2], prev[3] = "oldCache", "oldDoc", "oldFolder"
        data["Extracciones"].append(prev)
        result = prepare_contract_portfolio(data)
        self.assertEqual(result.works_count, 2)
        self.assertEqual(len(result.records), 2)


class _Request:
    def __init__(self, payload):
        self.payload = payload
    def execute(self):
        return self.payload


class _Values:
    def __init__(self):
        self.called = False
    def batchGet(self, **kwargs):
        self.called = True
        data = dataset()
        return _Request({
            "valueRanges": [
                {"values": data[name]}
                for name in HEADERS
            ]
        })
    def batchUpdate(self, **kwargs):
        raise AssertionError("El dashboard jamás debe escribir en Google Sheets")


class _Sheets:
    def __init__(self):
        self.value_object = _Values()
    def spreadsheets(self):
        return self
    def values(self):
        return self.value_object


class PortfolioReadTests(unittest.TestCase):
    def test_portfolio_reads_sheet_only(self):
        sheets = _Sheets()
        result = read_contract_portfolio(sheets, "id-sheet")
        self.assertTrue(sheets.value_object.called)
        self.assertEqual(result.works_count, 1)


if __name__ == "__main__":
    unittest.main()
