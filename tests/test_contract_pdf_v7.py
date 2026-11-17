"""Regresiones del contrato escaneado de proyecto ejecutivo de León.

Caso real auditado:
- Contrato A-2510-K100313-62201-H/0180/2025.
- Página 5: base en precios unitarios y volúmenes autorizados.
- Página 18: Ing. Juan de Jesús López Urénda firma como TESTIGO,
  Director de Planeación y Proyectos, no técnico de ARRE-VERA S.A. de C.V.
La prueba usa citas de las páginas, sin hacer OCR ni consumir Gemini.
"""
from __future__ import annotations

from dataclasses import replace
import unittest
from pathlib import Path

from services.contract_prompt import PROMPT_CONTRATO, PROMPT_VERSION
from services.contract_v2 import CONTRACT_SCHEMA_V2, CONTRACT_V2_FIELDS, parse_contract_v2
from services.contract_role_rules import (
    authorized_legal_role, authorized_technical_role,
    participant_role_conflicts_with_technical, suggested_display_type,
    record_representation_fields,
)
from services.contract_upgrade import eligible_contract_upgrade
from services.drive_service import DocumentRecord
from services.contract_table import contract_table_rows
from tests.test_contract_v2 import contract_payload
from tests.test_contract_table import make_record


CASE_NAME = "ING. JUAN DE JESÚS LÓPEZ URÉNDA"
CASE_CONTRACT = "A-2510-K100313-62201-H/0180/2025"
CASE_AMOUNT = "$156,243.81 / (CIENTO CINCUENTA Y SEIS MIL DOSCIENTOS CUARENTA Y TRES PESOS 81/100 M.N.) IVA INCLUIDO"
CASE_AMOUNT_EVIDENCE_V5 = (
    "el importe a pagar por los servicios que ofrecerá EL PROYECTISTA "
    "será la cantidad de " + CASE_AMOUNT
)
CASE_PRICE_EVIDENCE = (
    "TERCERA. MONTO DEL CONTRATO. Convienen LAS PARTES que el importe "
    "a pagar por los servicios que ofrecerá EL PROYECTISTA será la cantidad "
    "de $156,243.81 IVA INCLUIDO, cantidad que se fijó como importe total, "
    "con base en los precios unitarios y volúmenes autorizados."
)
CASE_PARTICIPANT = {
    "nombre": CASE_NAME,
    "cargo_o_caracter": "DIRECTOR DE PLANEACIÓN Y PROYECTOS",
    "representacion": None,
    "pagina": 18,
    "evidencia": "ING. JUAN DE JESÚS LÓPEZ URÉNDA, DIRECTOR DE PLANEACIÓN Y PROYECTOS",
}


def _with_fields(**replacements):
    data = contract_payload()
    for key, val in replacements.items():
        row = next(r for r in data["campos"] if r["campo"] == key)
        row.update(val)
    return data


class ContractPdfV7Tests(unittest.TestCase):
    def test_saved_v5_heading_is_nature_not_price_modality(self):
        # El tipo actual guardado en Sheets es el título/naturaleza del servicio.
        saved_type = "CONTRATO DE SERVICIOS RELACIONADOS CON LA OBRA PÚBLICA PROYECTO EJECUTIVO"
        self.assertEqual(
            suggested_display_type(saved_type, CASE_AMOUNT, CASE_AMOUNT_EVIDENCE_V5),
            "—",
        )
        # No inventar «precios unitarios» a partir de un texto que lo omitió.
        self.assertNotIn("precios unitarios", CASE_AMOUNT_EVIDENCE_V5.lower())

    def test_new_quote_recovers_unit_prices_even_when_gemini_returns_heading(self):
        data=_with_fields(
            tipo_contrato={
                "valor": "CONTRATO DE SERVICIOS RELACIONADOS CON LA OBRA PÚBLICA PROYECTO EJECUTIVO",
                "pagina": 1,
                "evidencia": "CONTRATO DE SERVICIOS RELACIONADOS CON LA OBRA PÚBLICA PROYECTO EJECUTIVO",
            },
            monto_contrato={
                "valor": CASE_AMOUNT,
                "pagina": 5,
                "evidencia": CASE_PRICE_EVIDENCE,
            },
        )
        result=parse_contract_v2(data)
        self.assertIn("precios unitarios",result.tipo_contrato.valor.lower())
        self.assertEqual(result.tipo_contrato.pagina,5)
        self.assertEqual(result.tipo_contrato.evidencia,CASE_PRICE_EVIDENCE)
        self.assertEqual(
            suggested_display_type(result.tipo_contrato.valor,CASE_AMOUNT,CASE_PRICE_EVIDENCE),
            "Precios Unitarios",
        )

    def test_juan_is_witness_and_municipal_director_not_contractor_technical(self):
        self.assertFalse(authorized_technical_role(
            CASE_NAME,
            f"TESTIGOS. {CASE_NAME}, DIRECTOR DE PLANEACIÓN Y PROYECTOS. "
            "RESPONSABLE TÉCNICO DE LA CONTRATISTA",
        ))
        self.assertTrue(participant_role_conflicts_with_technical(
            CASE_NAME,[CASE_PARTICIPANT],
        ))
        payload=_with_fields(
            representante_tecnico={
                "valor":CASE_NAME,
                "pagina":18,
                "evidencia":(
                    f"{CASE_NAME}, REPRESENTANTE TÉCNICO DE LA CONTRATISTA."
                ),
            },
        )
        payload["personas"].append(CASE_PARTICIPANT)
        extraction=parse_contract_v2(payload)
        self.assertIsNone(extraction.representante_tecnico.valor)
        self.assertIn(CASE_NAME, [x.nombre for x in extraction.personas_participantes])

    def test_persisted_participant_stays_not_accredited_in_results(self):
        row=make_record()
        fields=dict(row.full_values)
        fields["representante_tecnico"]=CASE_NAME
        row=replace(row,full_values=fields,participants=(CASE_PARTICIPANT,),
                    evidence={
                        "representante_tecnico":{
                            "evidencia":f"{CASE_NAME}, REPRESENTANTE TÉCNICO DE LA CONTRATISTA.",
                            "pagina":18,
                        },
                    })
        self.assertEqual(record_representation_fields(row)[1],"")
        display=contract_table_rows([row])[0]
        self.assertEqual(display["Representante técnico"],"—")
        self.assertIn(CASE_NAME,display["Personas que participan en el contrato"])

    def test_marian_arreola_president_council_is_authorized_role(self):
        self.assertTrue(authorized_legal_role(
            "C. MARIANO ARREOLA CALLEROS",
            "C. MARIANO ARREOLA CALLEROS, en su carácter de "
            "PRESIDENTE CONSEJO DE ADMINISTRACIÓN",
        ))

    def test_contract_upgrade_only_when_old_confirmed_and_same_pdf(self):
        doc=DocumentRecord(id="1UWqjNFMY2YXpDITA8Uz8DLlucD_WftbN",
                           name="CONTRATO.pdf",md5_checksum="f8db665f0c4be748f2b25bf58e03235e",
                           size_bytes=14895978)
        work_id="137t2Ul0fR81S6uJDBk-ZkObnHc77Y9KS"
        reg={
            "documento_id":doc.id, "obra_id":work_id, "activo":"SI",
            "md5_checksum":doc.md5_checksum, "tipo_documental":"CONTRATO",
            "estado_procesamiento":"Requiere validación",
            "resultado_id":"cache_older",
        }
        old={
            "cache_key":"cache_older", "obra_id":work_id,
            "documento_id":doc.id, "version_esquema":"contrato-v2",
            "version_prompt":"contrato-prompt-v5",
            "estado":"COMPLETADO","resultado_json":"{}",
        }
        self.assertTrue(eligible_contract_upgrade(doc,work_id,reg,old,[])[0])
        self.assertFalse(eligible_contract_upgrade(doc,work_id,reg,{
            **old,"version_prompt":PROMPT_VERSION,
        },[])[0])
        self.assertFalse(eligible_contract_upgrade(doc,work_id,{
            **reg,"md5_checksum":"different",
        },old,[])[0])
        self.assertFalse(eligible_contract_upgrade(doc,work_id,reg,old,[{
            **old,"estado":"REQUIERE_REVISION",
        }])[0])

    def test_no_silent_reanalysis_in_ui(self):
        screen=Path(__file__).resolve().parents[1].joinpath("ui","expedientes.py").read_text(encoding="utf-8")
        self.assertIn("_render_contract_upgrade(",screen)
        self.assertIn("Confirmo que deseo volver a analizar",screen)
        self.assertIn("disabled=not accepted",screen)
        self.assertIn('st.session_state.pop("results_portfolio", None)',screen)
        self.assertIn("st.session_state[\"ex_last_run\"] = _analyze(obra, [doc], model)",screen)
        self.assertNotIn("delete_analysis(",screen.split("def _render_contract_upgrade",1)[1].split("def _render_delete_analysis",1)[0])

    def test_prompt_v7_preserves_schema_and_targets_missing_tail(self):
        self.assertEqual(PROMPT_VERSION,"contrato-prompt-v7")
        self.assertEqual(CONTRACT_SCHEMA_V2,"contrato-v2")
        self.assertEqual(len(CONTRACT_V2_FIELDS),16)
        self.assertIn("no cortes el párrafo inmediatamente después",PROMPT_CONTRATO)
        self.assertIn("El encabezado \"CONTRATO DE SERVICIOS",PROMPT_CONTRATO)
        self.assertIn("\"TESTIGOS\"",PROMPT_CONTRATO)


if __name__=="__main__":
    unittest.main()
