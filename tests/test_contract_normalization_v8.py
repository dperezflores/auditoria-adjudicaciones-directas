"""Pruebas del prompt literal 15 campos, normalización y revisiones persistentes."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from unittest.mock import Mock, patch
import unittest

from services.contract_prompt import PROMPT_CONTRATO, PROMPT_VERSION
from services.contract_v2 import (
    CONTRACT_V2_FIELDS, CONTRACT_EXTRACTION_FIELDS,parse_contract_v2,
)
from services.contract_normalization import normalize_advance,normalized_values
from services.contract_verifications import (
    _validate_fields, VerificationError,read_verifications,with_verifications,
    save_verification,
)
from services.contract_portfolio import ContractPortfolio
from services.contract_table import contract_table_rows
from services.award_limits import evaluate
from tests.test_contract_v2 import contract_payload
from tests.test_award_limits import contract,fixture_catalog
from services.award_limits import parse_catalog


def saved_raw(advance: str, iva: str="$1,542,830.55"):
    record=contract(anticipo=advance,monto_contrato=iva)
    return record


class NormalizationV8Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog=parse_catalog(fixture_catalog())

    def test_user_prompt_has_exactly_15_fields_no_technical(self):
        self.assertEqual(PROMPT_VERSION,"contrato-prompt-v8")
        self.assertEqual(len(CONTRACT_EXTRACTION_FIELDS),15)
        self.assertNotIn("representante_tecnico",CONTRACT_EXTRACTION_FIELDS)
        self.assertEqual(len(CONTRACT_V2_FIELDS),16)
        self.assertIn('Genera exactamente 15 entradas',PROMPT_CONTRATO)
        self.assertIn('R2. El valor está contenido en la evidencia',PROMPT_CONTRATO)

    def test_new_extractor_preserves_all_values_even_if_legacy_would_derive(self):
        raw=contract_payload()
        raw["campos"]=[
            row for row in raw["campos"]
            if row["campo"]!="representante_tecnico"
        ]
        # Eliminar el resultado procesado v7, respetar literalmente la respuesta.
        for row in raw["campos"]:
            if row["campo"]=="tipo_contrato":
                row["valor"]="SERVICIO DE PROYECTO EJECUTIVO"
                row["evidencia"]="SERVICIO DE PROYECTO EJECUTIVO"
            if row["campo"]=="monto_contrato":
                row["valor"]="$156,243.81"
                row["evidencia"]=(
                    "$156,243.81 IVA INCLUIDO, con base en precios unitarios."
                )
        extraction=parse_contract_v2(raw,literal_only=True)
        self.assertEqual(extraction.tipo_contrato.valor,"SERVICIO DE PROYECTO EJECUTIVO")
        self.assertEqual(extraction.representante_tecnico.valor,None)
        self.assertNotIn("representante_tecnico",extraction.fields_to_review())
        self.assertEqual(extraction.monto_contrato.valor,"$156,243.81")

    def test_literal_mode_rejects_technical_field_and_missing_fields(self):
        raw=contract_payload()
        with self.assertRaisesRegex(ValueError,"15 campos"):
            parse_contract_v2(raw,literal_only=True)
        raw["campos"]=[row for row in raw["campos"]
            if row["campo"] not in ("representante_tecnico","rfc")]
        with self.assertRaisesRegex(ValueError,"15 campos"):
            parse_contract_v2(raw,literal_only=True)

    def test_advance_zero_when_denial_even_if_percent_appears(self):
        a=normalize_advance(
            "30.00%, no se otorgará porcentaje alguno de anticipo"
        )
        self.assertEqual(a.percent,"0%")
        self.assertIn("prevaleció la negación",a.note)

    def test_advance_percent_with_two_amounts_and_iva(self):
        raw=(
            "30.00% (TRES MILLONES NOVECIENTOS SESENTA Y CUATRO MIL "
            "QUINIENTOS CUARENTA Y SIETE PESOS 27/100 M.N.) IVA INCLUIDO, "
            "que corresponde a $1,189,364.18 IVA INCLUIDO"
        )
        self.assertEqual(normalize_advance(raw).percent,"30%")
        self.assertEqual(normalize_advance("12.50%").percent,"12.5%")
        self.assertEqual(normalize_advance("no se otorgará anticipo").percent,"0%")
        self.assertEqual(normalize_advance("30% y 20%").percent,"—")

    def test_table_contains_folder_and_percent_and_iva_assumption(self):
        record=saved_raw("no se otorgará porcentaje alguno de anticipo")
        result=contract_table_rows([record])[0]
        self.assertEqual(result["Carpeta"],record.nombre_carpeta)
        self.assertEqual(result["Anticipo"],"0%")
        self.assertEqual(result["IVA del importe"],"Con IVA (16%)")
        self.assertIn("SUPUESTO PROVISIONAL",result["Observaciones de extracción"])
        self.assertNotIn("Representante técnico",result)

    def test_contract_without_iva_is_evaluated_provisionally(self):
        rec=saved_raw("30.00%",iva="$1,542,830.55")
        result=evaluate(rec,self.catalog)
        self.assertEqual(result.iva,"Con IVA (16%)")
        self.assertEqual(result.net,Decimal("1330026.34"))
        self.assertEqual(result.state,"Dentro del límite")
        self.assertTrue(any("SUPUESTO" in w for w in result.warnings))

    def test_verified_iva_and_advance_shared_by_results_and_ad06(self):
        rec=saved_raw("30.00%",iva="$1,542,830.55")
        verification={
            "obra_id":rec.obra_id,"documento_id":rec.documento_id,
            "cache_key":rec.cache_key,"estado_revision":"Confirmado",
            "observaciones":"Confirmado contrato, cláusula tercera",
            "campos":{
                "iva":"Sin IVA",
                "anticipo":"0%",
                "regimen":"Estatal",
                "ejercicio":"2025",
                "modalidad_adjudicacion":"ADJUDICACIÓN DIRECTA",
                "tipo_contrato":"Precios Unitarios",
            },
        }
        current=replace(rec,verification=verification)
        normalized,notes=normalized_values(current)
        self.assertEqual(normalized["anticipo"],"0%")
        self.assertEqual(normalized["iva"],"Sin IVA")
        self.assertEqual(contract_table_rows([current])[0]["Estado de verificación"],"Confirmado")
        result=evaluate(current,self.catalog)
        self.assertEqual(result.regime,"Estatal")
        self.assertEqual(result.net,Decimal("1542830.55"))
        self.assertFalse(any("SUPUESTO PROVISIONAL" in n for n in notes))

    def test_review_attaches_only_to_original_identity_and_cache(self):
        record=saved_raw("30%")
        portfolio=ContractPortfolio((record,))
        correct={
            "cache_key":record.cache_key,"obra_id":record.obra_id,
            "documento_id":record.documento_id,"campos":{"anticipo":"0%"},
        }
        verified=with_verifications(portfolio,{record.cache_key:correct})
        self.assertEqual(verified.records[0].verification["campos"]["anticipo"],"0%")
        different={**correct,"documento_id":"otro"}
        self.assertIsNone(with_verifications(
            portfolio,{record.cache_key:different},
        ).records[0].verification)
        self.assertIsNone(record.verification)

    def test_invalid_manual_inputs_are_blocked(self):
        for data in (
            {"iva":"Supuesta"},
            {"ejercicio":"2027"},
            {"anticipo":"se dará 30 por ciento"},
            {"tipo_contrato":"Proyecto Ejecutivo"},
            {"modalidad_adjudicacion":"AD"},
        ):
            with self.subTest(data=data):
                with self.assertRaises(VerificationError):
                    _validate_fields(data)

    def test_history_reader_keeps_last_revision(self):
        sheet=Mock()
        sheet.spreadsheets.return_value.get.return_value.execute.return_value={
            "sheets":[{"properties":{"title":"VerificacionesContrato"}}]
        }
        from services.contract_verifications import HEADERS
        one=["first","obra","doc","key","2026-11-19","auditor",
             "Pendiente",'{"anticipo":"30%"}',"Primera"]
        two=["second","obra","doc","key","2026-11-19T23:10Z","auditor",
             "Confirmado",'{"anticipo":"0%"}',"Segunda"]
        # Aquí campos_json se lee como objeto con las claves manuales.
        sheet.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value={
            "values":[list(HEADERS),one,two]
        }
        got=read_verifications(sheet,"spreadsheet123456789000")
        self.assertEqual(got["key"]["revision_id"],"second")
        self.assertEqual(got["key"]["campos"]["anticipo"],"0%")

    def test_save_only_appends_to_review_sheet_no_source_edits(self):
        record=saved_raw("30%")
        mock=Mock()
        mock.spreadsheets.return_value.get.return_value.execute.return_value={
            "sheets":[{"properties":{"title":"VerificacionesContrato"}}]
        }
        from services.contract_verifications import HEADERS
        mock.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value={
            "values":[list(HEADERS)]
        }
        mock.spreadsheets.return_value.values.return_value.append.return_value.execute.return_value={
            "updates":{"updatedRows":1}
        }
        with patch("services.contract_verifications.read_contract_portfolio",
                   return_value=ContractPortfolio((record,))):
            revision=save_verification(
                mock,"spreadsheet123456789000",obra_id=record.obra_id,
                documento_id=record.documento_id,cache_key=record.cache_key,
                auditor="auditor@example.com",estado="Confirmado",
                campos={"anticipo":"0%","iva":"Con IVA (16%)"},
                observaciones="Cotejé cláusula de anticipo, página 4.",
            )
        self.assertTrue(revision)
        args=mock.spreadsheets.return_value.values.return_value.append.call_args.kwargs
        self.assertIn("VerificacionesContrato",args["range"])
        mock.spreadsheets.return_value.values.return_value.update.assert_not_called()


if __name__=="__main__":
    unittest.main()
