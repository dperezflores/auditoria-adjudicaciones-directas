"""Regresión de roles y tipo contractual (prompt-v6), sin Gemini ni PDFs reales."""
from __future__ import annotations

from dataclasses import replace
import unittest

from services.contract_prompt import PROMPT_CONTRATO, PROMPT_VERSION
from services.contract_role_rules import (
    NO_APLICA_FISICA, is_persona_fisica, authorized_technical_role,
    suggested_display_type, record_representation_fields,
)
from services.contract_v2 import (
    CONTRACT_V2_FIELDS, CONTRACT_V2_HEADERS, CONTRACT_SCHEMA_V2,
    parse_contract_v2,
)
from services.contract_table import contract_table_rows
from tests.test_contract_v2 import contract_payload
from tests.test_contract_table import make_record


NAME = "ARQ. MARIANO ARREOLA CALLEROS"
CORPORATION = "CONSULTORÍA ESPECIALIZADA DEL BAJÍO, S.A. DE C.V."
QUOTE_FISICA = (
    "EL PROYECTISTA: ARQ. MARIANO ARREOLA CALLEROS, "
    "persona física que comparece por su propio derecho."
)
QUOTE_PU = (
    'TERCERA. MONTO DEL CONTRATO. El importe a pagar a EL PROYECTISTA '
    'será la cantidad de $156,243.81 IVA INCLUIDO, '
    'cantidad que se fijó como importe total, con base en '
    'los precios unitarios y volúmenes autorizados.'
)


def payload(**fields):
    response = contract_payload()
    for name, changes in fields.items():
        entry = next(x for x in response["campos"] if x["campo"] == name)
        entry.update(changes)
    return response


def field(raw: str | None, evidence: str | None = None, page: int = 3) -> dict:
    return {
        "valor": raw,
        "pagina": page if raw is not None or evidence is not None else None,
        "evidencia": evidence,
    }


class ContractRolesV6Tests(unittest.TestCase):
    def test_persona_fisica_records_contracting_person_not_own_legal_rep(self):
        data = payload(
            contratista=field(NAME, QUOTE_FISICA, 1),
            representante_legal=field(None),
        )
        result = parse_contract_v2(data)
        self.assertEqual(result.contratista.valor, NAME)
        self.assertEqual(result.representante_legal.valor, NO_APLICA_FISICA)
        self.assertEqual(result.representante_legal.pagina, 1)
        self.assertEqual(result.representante_legal.evidencia, QUOTE_FISICA)
        self.assertTrue(any("clasificación derivada" in x for x in result.observaciones))
        self.assertEqual(len(result.flat_values()), 16)

    def test_persona_fisica_marked_as_own_representative_is_corrected(self):
        result = parse_contract_v2(payload(
            contratista=field(NAME, QUOTE_FISICA),
            representante_legal=field(NAME, f"{NAME} firma por su propio derecho"),
        ))
        self.assertEqual(result.representante_legal.valor, NO_APLICA_FISICA)

    def test_rfc_and_professional_title_do_not_prove_persona_fisica(self):
        q = f"{NAME} suscribe el contrato."
        self.assertFalse(is_persona_fisica(NAME, q))
        result = parse_contract_v2(payload(
            contratista=field(NAME, q),
            representante_legal=field(NO_APLICA_FISICA, q),
        ))
        self.assertIsNone(result.representante_legal.valor)

    def test_corporation_keeps_explicit_legal_proxy(self):
        legal = "LIC. MARÍA GONZÁLEZ TORRES"
        quote = (
            f"{legal} en su carácter de representante legal de "
            f"{CORPORATION}."
        )
        result = parse_contract_v2(payload(
            contratista=field(CORPORATION, f"LA CONTRATISTA: {CORPORATION}"),
            representante_legal=field(legal, quote),
        ))
        self.assertEqual(result.contratista.valor, CORPORATION)
        self.assertEqual(result.representante_legal.valor, legal)

    def test_physically_individual_may_have_real_separate_attorney(self):
        legal = "LIC. ROSA MARTÍNEZ OCHOA"
        result = parse_contract_v2(payload(
            contratista=field(NAME, QUOTE_FISICA),
            representante_legal=field(
                legal, f"{legal}, apoderada legal de {NAME}."
            ),
        ))
        self.assertEqual(result.representante_legal.valor, legal)

    def test_signing_company_not_sufficient_for_legal_role(self):
        legal = "LIC. MARÍA GONZÁLEZ TORRES"
        result = parse_contract_v2(payload(
            contratista=field(CORPORATION, f"LA CONTRATISTA: {CORPORATION}"),
            representante_legal=field(legal, f"FIRMA: {legal}"),
        ))
        self.assertIsNone(result.representante_legal.valor)

    def test_signing_architect_is_not_automatically_technical_representative(self):
        tech = "ARQ. PEDRO MARTÍNEZ RUIZ"
        data = payload(
            representante_tecnico=field(
                tech, f"POR LA CONTRATISTA: {tech} (FIRMA)."
            )
        )
        data["personas"].append({
            "nombre": tech, "cargo_o_caracter": "FIRMANTE",
            "representacion": "LA CONTRATISTA",
            "pagina": 20, "evidencia": f"{tech} (FIRMA)",
        })
        result = parse_contract_v2(data)
        self.assertIsNone(result.representante_tecnico.valor)
        self.assertEqual(
            result.personas_participantes[-1].nombre, tech
        )
        self.assertTrue(any("designación técnica" in x for x in result.observaciones))

    def test_technical_designation_by_company_is_kept(self):
        tech = "ING. LUIS RAMÍREZ NAVARRO"
        citation = (
            f"{tech}, REPRESENTANTE TÉCNICO DESIGNADO POR "
            "LA CONTRATISTA para la ejecución de la obra."
        )
        self.assertTrue(authorized_technical_role(tech, citation))
        result = parse_contract_v2(payload(
            representante_tecnico=field(tech, citation),
        ))
        self.assertEqual(result.representante_tecnico.valor, tech)

    def test_technical_role_of_municipal_counterparty_is_not_contractor_role(self):
        tech = "ING. LUIS RAMÍREZ NAVARRO"
        result = parse_contract_v2(payload(
            representante_tecnico=field(
                tech, f"{tech}, RESPONSABLE TÉCNICO DE LA CONTRATANTE."
            )
        ))
        self.assertIsNone(result.representante_tecnico.valor)

    def test_role_named_but_not_linked_to_contractor_requires_review(self):
        tech = "ING. LUIS RAMÍREZ NAVARRO"
        self.assertFalse(authorized_technical_role(
            tech, f"{tech}, RESPONSABLE TÉCNICO DE LA OBRA."
        ))
        result = parse_contract_v2(payload(
            representante_tecnico=field(
                tech, f"{tech}, RESPONSABLE TÉCNICO DE LA OBRA."
            )
        ))
        self.assertIsNone(result.representante_tecnico.valor)

    def test_missing_technical_role_remains_null(self):
        result = parse_contract_v2(payload())
        self.assertIsNone(result.representante_tecnico.valor)

    def test_economic_type_is_recovered_from_total_amount_clause(self):
        result = parse_contract_v2(payload(
            tipo_contrato=field(None),
            monto_contrato=field(
                "$156,243.81", QUOTE_PU, page=4,
            ),
        ))
        self.assertIn("precios unitarios", result.tipo_contrato.valor.lower())
        self.assertEqual(result.tipo_contrato.evidencia, QUOTE_PU)
        self.assertEqual(result.tipo_contrato.pagina, 4)
        self.assertTrue(any("frase literal recuperada" in x for x in result.observaciones))

    def test_pricing_in_unrelated_quote_does_not_fill_type(self):
        result = parse_contract_v2(payload(
            tipo_contrato=field(None),
            monto_contrato=field(
                "$156,243.81",
                "El anexo contiene precios unitarios y una oferta por $40,000.00.",
            ),
        ))
        self.assertIsNone(result.tipo_contrato.valor)

    def test_evidence_without_contract_total_does_not_fill_type(self):
        result = parse_contract_v2(payload(
            tipo_contrato=field(None),
            monto_contrato=field(
                "$156,243.81",
                "La oferta de $47,000.00 se hará con base en los precios "
                "unitarios y volúmenes autorizados.",
            ),
        ))
        self.assertIsNone(result.tipo_contrato.valor)

    def test_existing_saved_record_can_display_supported_type_and_persona_fisica(self):
        record = make_record()
        literals = dict(record.full_values)
        literals.update(
            contratista=NAME, representante_legal="",
            representante_tecnico="ARQ. PERSONA QUE SOLO FIRMA",
            tipo_contrato="", monto_contrato="$156,243.81 IVA INCLUIDO",
        )
        from services.contract_portfolio import parse_amount
        record = replace(record,full_values=literals,evidence={
            "contratista": {"evidencia": QUOTE_FISICA, "pagina": 1},
            "monto_contrato": {"evidencia": QUOTE_PU, "pagina": 4},
            "representante_tecnico": {
                "evidencia": "ARQ. PERSONA QUE SOLO FIRMA (FIRMA)",
                "pagina": 20,
            },
        })
        data=contract_table_rows([record])[0]
        self.assertEqual(data["Tipo de contrato"], "Precios Unitarios")
        self.assertEqual(data["Representante legal"], NO_APLICA_FISICA)
        self.assertEqual(data["Representante técnico"], "—")
        self.assertEqual(record.full_values["tipo_contrato"], "")
        self.assertEqual(record.full_values["representante_tecnico"],
                         "ARQ. PERSONA QUE SOLO FIRMA")
        self.assertEqual(
            record_representation_fields(record),
            (NO_APLICA_FISICA, ""),
        )

    def test_prompt_version_and_full_contract_schema_unchanged(self):
        self.assertEqual(PROMPT_VERSION, "contrato-prompt-v6")
        self.assertEqual(CONTRACT_SCHEMA_V2, "contrato-v2")
        self.assertEqual(len(CONTRACT_V2_FIELDS), 16)
        self.assertEqual(len(CONTRACT_V2_HEADERS), 23)
        self.assertIn("por su propio derecho", PROMPT_CONTRATO)
        self.assertIn("TERCERA/MONTO", PROMPT_CONTRATO)
        self.assertIn("Firmar el contrato NO acredita", PROMPT_CONTRATO)


if __name__ == "__main__":
    unittest.main()
