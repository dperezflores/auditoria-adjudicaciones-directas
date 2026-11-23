"""CC-01: cálculo y trazabilidad histórica sin PDF/Gemini/Drive."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock
import ast
import unittest

from services.capital_contable import (
    AssignmentEvidence, CapitalSourceError, CapitalSources,
    PucEntry, evaluate_capital, read_capital_sources,
)
from services.contract_portfolio import ContractRecord
from services.puc_history import make_puc_review
from services.dictamen_schema import DICTAMEN_HEADERS
from services.extraction_store import EXTRACTION_HEADERS
from services.puc_schema import PUC_HEADERS, parse_puc
from services.sync_engine import HEADERS as INVENTORY_HEADERS
from tests.test_award_limits import contract
from tests.test_puc_schema import sample_puc


WORK = "obraABC00001"
DOC = "pucDOC000001"
KEY = "pucCache000001"


def _contract(**overrides) -> ContractRecord:
    data={
        "monto_contrato":"$1,000,000.00 IVA INCLUIDO",
        "rfc":"GUGA940107FJ3",
        "registro_puc":"GTO-SOP/PUC-5455-2023",
        "fecha_firma_contrato":"15 de diciembre de 2025",
    }
    data.update(overrides)
    return replace(contract(**data),obra_id=WORK,nombre_carpeta="009_Parque")


def _puc(**overrides) -> PucEntry:
    fields={
        "obra_id":WORK,"documento_id":DOC,"cache_key":KEY,
        "nombre":"GUTIERREZ GUTIERREZ DE VELASCO ALEJANDRO",
        "rfc":"GUGA940107FJ3","registro":"GTO-SOP/PUC-5455-2023",
        "capital_text":"$352,203.00","capital":Decimal("352203.00"),
        "capital_page":1,"capital_evidence":"CAPITAL CONTABLE $352,203.00",
        "fecha_validacion":"7 de abril de 2025",
        "fecha_impresion":"5 de diciembre de 2025",
        "vigencia_desde":"","vigencia_hasta":"16 de mayo de 2026",
        "estado_registro":"REFRENDADO","version":"puc-prompt-v1",
    }
    fields.update(overrides)
    return PucEntry(**fields)


def _sources(puc: PucEntry | None = None, *, date: str = "10 de diciembre de 2025",
             issued_amount: str = "$1,000,000.00") -> CapitalSources:
    return CapitalSources(
        puc_by_work={WORK:puc} if puc is not None else {},
        issues_by_work={},
        assignments={
            WORK:AssignmentEvidence(
                fecha=date,fuente="Dictamen AD (fecha preliminar)",
                monto=issued_amount,
            )
        } if date else {},
    )


def _flat(headers, fields):
    return [fields.get(name,"") for name in headers]


def _sheets_fixture(*, analyzed=True, duplicate=False, changed=False,
                    invalid_json=False, with_dictamen=True):
    puc=parse_puc(sample_puc())
    docs=[]
    docs.append(_flat(INVENTORY_HEADERS["Documentos"],{
        "documento_id":DOC,"obra_id":WORK,"nombre_archivo":"PUC.pdf",
        "tipo_documental":"PUC","mime_type":"application/pdf",
        "md5_checksum":"hash123","activo":"SI",
        "estado_procesamiento":("Modificado desde el último análisis" if changed
                                else "Analizado"),
        "resultado_id":KEY if analyzed else "",
    }))
    if duplicate:
        docs.append(_flat(INVENTORY_HEADERS["Documentos"],{
            "documento_id":"otherPUC00001","obra_id":WORK,
            "nombre_archivo":"PUC.pdf","tipo_documental":"PUC",
            "mime_type":"application/pdf","activo":"SI",
        }))
    extra=[_flat(EXTRACTION_HEADERS,{
        "cache_key":KEY,"obra_id":WORK,"documento_id":DOC,
        "version_esquema":"puc-v1","version_prompt":"puc-prompt-v1",
        "estado":"COMPLETADO",
        "resultado_json":("{broken" if invalid_json else puc.model_dump_json()),
    })]
    flat_puc=[_flat(PUC_HEADERS,{
        "cache_key":KEY,"obra_id":WORK,"documento_id":DOC,
        **dict(zip([
            "contratista","rfc","numero_registro_puc","capital_contable",
        ],[
            puc.contratista.valor,puc.rfc.valor,puc.numero_registro_puc.valor,
            puc.capital_contable.valor,
        ])),
    })]
    dict_data=[]
    if with_dictamen:
        dd="dictamenDOC0001"; kk="dictamenCache0001"
        docs.append(_flat(INVENTORY_HEADERS["Documentos"],{
            "documento_id":dd,"obra_id":WORK,
            "nombre_archivo":"DICTAMEN_AD.pdf","tipo_documental":"DICTAMEN_AD",
            "activo":"SI","resultado_id":kk,
        }))
        extra.append(_flat(EXTRACTION_HEADERS,{
            "cache_key":kk,"obra_id":WORK,"documento_id":dd,
            "version_esquema":"dictamen-ad-v1","estado":"COMPLETADO",
            "resultado_json":'{"saved":true}',
        }))
        dict_data.append(_flat(DICTAMEN_HEADERS,{
            "cache_key":kk,"obra_id":WORK,"documento_id":dd,
            "fecha_emision":"10 de diciembre de 2025",
            "monto_asignado":"$1,000,000.00",
        }))
    return [
        [list(INVENTORY_HEADERS["Documentos"]),*docs],
        [list(EXTRACTION_HEADERS),*extra],
        [list(PUC_HEADERS),*flat_puc],
        [list(DICTAMEN_HEADERS),*dict_data],
    ]


class CapitalContableTests(unittest.TestCase):
    def test_capital_above_30_and_valid_preliminary_puc(self):
        r=evaluate_capital(_contract(),_sources(_puc()))
        self.assertEqual(r.requirement,Decimal("300000.00"))
        self.assertEqual(r.capital,Decimal("352203.00"))
        self.assertEqual(r.difference,Decimal("52203.00"))
        self.assertEqual(r.comparison,"Cubre el 30%")
        self.assertEqual(r.coverage,Decimal("35.22"))
        self.assertEqual(r.state,"Cubre el 30% (revisión inicial)")
        self.assertIn("opcional",r.historical)
        self.assertEqual(r.assignment.fecha,"15/12/2025")
        self.assertEqual(r.vigencia_puc,"Vigente en fecha de firma")
        self.assertEqual(r.vigencia_desde,"16/05/2025")

    def test_capital_less_than_30_is_detected_not_falsely_approved(self):
        r=evaluate_capital(_contract(),_sources(
            _puc(capital=Decimal("299999.99"))
        ))
        self.assertEqual(r.difference,Decimal("-0.01"))
        self.assertEqual(r.comparison,"Capital inferior al 30%")
        self.assertEqual(r.state,"Capital inferior al 30% (revisión inicial)")

    def test_30_percent_uses_total_not_net_after_iva(self):
        r=evaluate_capital(_contract(),_sources(_puc()))
        self.assertEqual(r.requirement,Decimal("300000.00"))
        # Si se dividiera erróneamente entre 1.16 sería ≈258,620.69.
        self.assertNotEqual(r.requirement,Decimal("258620.69"))

    def test_no_puc_not_misidentified_as_failure(self):
        r=evaluate_capital(_contract(),_sources())
        self.assertEqual(r.state,"Pendiente de PUC")
        self.assertIsNone(r.requirement)
        self.assertIsNone(r.capital)
        self.assertIn("No existe PUC",r.notes[-1])

    def test_other_procedures_do_not_use_direct_award_manual(self):
        for mode in ("LICITACIÓN SIMPLIFICADA","LICITACIÓN PÚBLICA"):
            r=evaluate_capital(_contract(modalidad_adjudicacion=mode),_sources(_puc()))
            self.assertEqual(r.state,"No aplica")
            self.assertIsNone(r.requirement)

    def test_unknown_method_does_not_assume_direct_award(self):
        r=evaluate_capital(_contract(modalidad_adjudicacion=""),_sources(_puc()))
        self.assertEqual(r.state,"Requiere revisión")
        self.assertEqual(r.historical,"Modalidad no identificada")

    def test_after_award_puc_print_is_historical_pending(self):
        r=evaluate_capital(_contract(),_sources(_puc(
            fecha_impresion="16 de diciembre de 2025",
        )))
        self.assertEqual(r.comparison,"Cubre el 30%")
        self.assertEqual(r.state,"Cubre el 30% (revisión inicial)")
        self.assertEqual(r.vigencia_puc,"Vigente en fecha de firma")

    def test_after_award_puc_validation_is_pending(self):
        r=evaluate_capital(_contract(),_sources(_puc(
            fecha_validacion="20 de diciembre de 2025",
        )))
        self.assertEqual(r.state,"Cubre el 30% (revisión inicial)")
        self.assertEqual(r.vigencia_puc,"Vigente en fecha de firma")

    def test_puc_expired_or_suspended_is_flagged(self):
        expired=evaluate_capital(
            _contract(),_sources(_puc(vigencia_hasta="1 de diciembre de 2025"))
        )
        self.assertEqual(expired.state,"PUC fuera de vigencia en fecha de firma")
        self.assertEqual(expired.comparison,"Cubre el 30%")
        suspended=evaluate_capital(
            _contract(),_sources(_puc(estado_registro="SUSPENDIDO"))
        )
        self.assertEqual(suspended.state,"Requiere revisión de vigencia PUC")

    def test_missing_dictamen_uses_contract_signature_as_assignment(self):
        r=evaluate_capital(_contract(),_sources(_puc(),date=""))
        self.assertEqual(r.state,"Cubre el 30% (revisión inicial)")
        self.assertEqual(r.assignment.fecha,"15/12/2025")
        self.assertIn("Firma del contrato",r.assignment.fuente)

    def test_mismatched_rfc_and_registration_require_cotejo(self):
        for revised in (
            _contract(rfc="OTRO020202AB1"),
            _contract(registro_puc="GTO-SOP/PUC-0000-2023"),
        ):
            r=evaluate_capital(revised,_sources(_puc()))
            self.assertEqual(r.state,"Requiere revisión de identidad")
            self.assertEqual(r.comparison,"Cubre el 30%")

    def test_unparseable_or_foreign_amounts_stay_undetermined(self):
        for raw in ("$10,000.00 Y $9,000.00","USD 1,000,000.00"):
            r=evaluate_capital(_contract(monto_contrato=raw),_sources(_puc()))
            self.assertEqual(r.state,"Requiere revisión de importes")
            self.assertIsNone(r.requirement)

    def test_duplicate_puc_is_not_chosen_arbitrarily(self):
        tables=_sheets_fixture(duplicate=True)
        client=Mock()
        client.spreadsheets.return_value.values.return_value.batchGet.return_value.execute.return_value={
            "valueRanges":[{"values":v} for v in tables],
        }
        sources=read_capital_sources(client,"sheet_id")
        self.assertNotIn(WORK,sources.puc_by_work)
        self.assertIn("varios",sources.issues_by_work[WORK])

    def test_current_puc_and_dictamen_read_by_full_cache_identity(self):
        client=Mock()
        tables=_sheets_fixture()
        client.spreadsheets.return_value.values.return_value.batchGet.return_value.execute.return_value={
            "valueRanges":[{"values":v} for v in tables],
        }
        src=read_capital_sources(client,"sheet_id")
        self.assertEqual(src.puc_by_work[WORK].capital,Decimal("352203.00"))
        self.assertEqual(src.puc_by_work[WORK].capital_page,1)
        self.assertEqual(src.assignments[WORK].fecha,"10 de diciembre de 2025")
        args=client.spreadsheets.return_value.values.return_value.batchGet.call_args.kwargs
        self.assertEqual(len(args["ranges"]),4)

    def test_puc_not_analyzed_or_modified_does_not_use_historical_data(self):
        for kwargs in ({"analyzed":False},{"changed":True},{"invalid_json":True}):
            with self.subTest(kwargs=kwargs):
                client=Mock()
                tables=_sheets_fixture(**kwargs)
                client.spreadsheets.return_value.values.return_value.batchGet.return_value.execute.return_value={
                    "valueRanges":[{"values":v} for v in tables],
                }
                sources=read_capital_sources(client,"sheet_id")
                self.assertNotIn(WORK,sources.puc_by_work)
                self.assertIn(WORK,sources.issues_by_work)

    def test_different_dictamen_amount_is_note_not_bulk_blocker(self):
        r=evaluate_capital(_contract(),_sources(
            _puc(),issued_amount="$900,000.00"
        ))
        self.assertEqual(r.state,"Cubre el 30% (revisión inicial)")
        self.assertTrue(any("dictamen" in n.casefold() for n in r.notes))

    def test_missing_capital_evidence_requires_cotejo(self):
        r=evaluate_capital(_contract(),_sources(
            _puc(capital_page=None,capital_evidence="")
        ))
        self.assertEqual(r.state,"Requiere revisión de evidencia del capital")

    def test_saved_verification_changes_amount_without_rewriting_extraction(self):
        rec=_contract()
        confirmed=replace(rec,verification={
            "campos":{"monto_contrato":"$1,100,000.00"},
            "estado_revision":"Confirmado","observaciones":"Cotejo del contrato",
        })
        r=evaluate_capital(confirmed,_sources(
            _puc(),issued_amount="$1,100,000.00",
        ))
        self.assertEqual(r.requirement,Decimal("330000.00"))
        self.assertEqual(r.comparison,"Cubre el 30%")
        self.assertEqual(rec.full_values["monto_contrato"],"$1,000,000.00 IVA INCLUIDO")

    def _historical_review(self, **overrides):
        values = dict(
            obra_id=WORK, contrato_documento_id=_contract().documento_id,
            contrato_cache_key=_contract().cache_key,
            puc_documento_id=DOC, puc_cache_key=KEY,
            auditor="auditor@example.com",
            fecha_asignacion="10/12/2025",
            capital_historico="275000.00",
            fecha_registro_capital="01/05/2025",
            alcance_capital="Historial completo hasta asignación",
            fuente="Certificación de movimientos del PUC",
            referencia="Oficio de padrón 123/2025, folio 4",
            observaciones="Capital oficialmente registrado antes de asignar.",
        )
        values.update(overrides)
        return make_puc_review(**values)

    def test_historical_capital_under_30_replaces_current_provisional_amount(self):
        contract = _contract()
        reviewed = self._historical_review(
            contrato_documento_id=contract.documento_id,
            contrato_cache_key=contract.cache_key,
        )
        result = evaluate_capital(contract, _sources(_puc()), reviewed)
        self.assertTrue(result.capital_historico_acreditado)
        self.assertEqual(result.capital_constancia, Decimal("352203.00"))
        self.assertEqual(result.capital, Decimal("275000.00"))
        self.assertEqual(result.requirement, Decimal("300000.00"))
        self.assertEqual(result.state, "Capital inferior al 30% (historial SOP)")

    def test_later_capital_update_cannot_apply_retroactively(self):
        contract = _contract()
        reviewed = self._historical_review(
            contrato_documento_id=contract.documento_id,
            contrato_cache_key=contract.cache_key,
            capital_historico="900000.00",
            fecha_registro_capital="20/12/2025",
        )
        result = evaluate_capital(contract, _sources(_puc()), reviewed)
        self.assertFalse(result.capital_historico_acreditado)
        self.assertEqual(result.state, "Requiere revisión de actualización posterior")
        self.assertIn("posterior", result.historical)
        self.assertEqual(result.capital, result.capital_constancia)

    def test_single_movement_does_not_prove_last_registered_capital(self):
        contract = _contract()
        reviewed = self._historical_review(
            contrato_documento_id=contract.documento_id,
            contrato_cache_key=contract.cache_key,
            capital_historico="950000.00",
            alcance_capital="Movimiento aislado: último valor sin acreditar",
        )
        result = evaluate_capital(contract, _sources(_puc()), reviewed)
        self.assertFalse(result.capital_historico_acreditado)
        self.assertEqual(result.state, "Cubre el 30% (revisión inicial)")
        self.assertEqual(result.capital, result.capital_constancia)

    def test_print_after_assignment_does_not_block_certified_prior_capital(self):
        contract = _contract()
        reviewed = self._historical_review(
            contrato_documento_id=contract.documento_id,
            contrato_cache_key=contract.cache_key,
            capital_historico="950000.00",
            fecha_registro_capital="01/06/2025",
        )
        result = evaluate_capital(
            contract, _sources(_puc(fecha_impresion="18 de diciembre de 2025")),
            reviewed,
        )
        self.assertTrue(result.capital_historico_acreditado)
        self.assertEqual(result.state, "Cubre el 30% (historial SOP)")

    def test_review_is_not_reused_after_contract_or_puc_replacement(self):
        contract = _contract()
        reviewed = self._historical_review(
            contrato_documento_id=contract.documento_id,
            contrato_cache_key=contract.cache_key,
            capital_historico="1000000.00",
        )
        replaced = replace(contract, cache_key="contract_new_version")
        result = evaluate_capital(replaced, _sources(_puc()), reviewed)
        self.assertFalse(result.capital_historico_acreditado)
        self.assertEqual(result.state, "Cubre el 30% (revisión inicial)")

    def test_contract_signature_not_dictamen_controls_puc_interval(self):
        # Dictamen 10/12/25 y firma 15/12/25. Cédula empieza 12/12/25.
        puc=_puc(vigencia_desde="",vigencia_hasta="12/12/2026")
        result=evaluate_capital(
            _contract(),_sources(puc,date="10 de diciembre de 2025")
        )
        self.assertEqual(result.vigencia_desde,"12/12/2025")
        self.assertEqual(result.assignment.fecha,"15/12/2025")
        self.assertEqual(result.state,"Cubre el 30% (revisión inicial)")

    def test_no_capital_history_is_not_default_incumplimiento(self):
        result=evaluate_capital(_contract(),_sources(_puc()))
        self.assertEqual(result.state,"Cubre el 30% (revisión inicial)")
        self.assertFalse(result.capital_historico_acreditado)
        self.assertEqual(result.capital_constancia,result.capital)
        self.assertNotIn("por acreditar",result.state.casefold())

    def test_no_signature_cannot_be_approved_with_current_certificate(self):
        result=evaluate_capital(
            _contract(fecha_firma_contrato=""),_sources(_puc())
        )
        self.assertEqual(result.state,"Pendiente de vigencia PUC")
        self.assertIsNone(result.assignment)
        self.assertEqual(result.comparison,"Cubre el 30%")

    def test_no_puc_expiration_cannot_be_approved(self):
        result=evaluate_capital(
            _contract(),_sources(_puc(vigencia_desde="",vigencia_hasta=""))
        )
        self.assertEqual(result.state,"Pendiente de vigencia PUC")
        self.assertEqual(result.comparison,"Cubre el 30%")

    def test_identity_and_vigencia_are_independent_of_30_percent(self):
        result=evaluate_capital(
            _contract(),_sources(_puc(vigencia_hasta="01/12/2025"))
        )
        self.assertEqual(result.comparison,"Cubre el 30%")
        self.assertEqual(result.state,"PUC fuera de vigencia en fecha de firma")

    def test_prior_effective_assignment_date_in_manual_review_is_respected(self):
        # El cálculo masivo usa firma; una revisión complementaria con
        # asignación anterior al movimiento debe impedir aprobación histórica.
        contract=_contract()
        historical=self._historical_review(
            contrato_documento_id=contract.documento_id,
            contrato_cache_key=contract.cache_key,
            fecha_asignacion="10/12/2025",
            fecha_registro_capital="12/12/2025",
            capital_historico="950000.00",
        )
        result=evaluate_capital(contract,_sources(_puc()),historical)
        self.assertEqual(result.assignment.fecha,"15/12/2025")
        self.assertEqual(
            result.state,"Requiere revisión de actualización posterior"
        )
        self.assertFalse(result.capital_historico_acreditado)

    def test_tabs_keep_existing_limits_and_render_capital_without_gemini(self):
        base=Path(__file__).resolve().parents[1]
        screen=(base/"ui"/"pruebas_adjudicacion.py").read_text(encoding="utf-8")
        capital=(base/"ui"/"capital_contable.py").read_text(encoding="utf-8")
        ast.parse(screen)
        ast.parse(capital)
        self.assertIn('st.tabs([',screen)
        self.assertIn('"Verificación de límites de adjudicación"',screen)
        self.assertIn('"Verificación de capital contable"',screen)
        self.assertIn('"Verificación de vigencia del PUC"',screen)
        self.assertIn('_render_limits_tab()',screen)
        self.assertIn('render_capital_test()',screen)
        self.assertIn('render_verification_form(record,prefix="capital")',capital)
        self.assertIn('"Exportar resultados de capital contable (CSV)"',capital)
        self.assertNotIn('extract_or_reuse',capital)


if __name__=="__main__":
    unittest.main()
