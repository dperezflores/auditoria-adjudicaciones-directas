"""Prueba AD-06: reglas de límites por importe, sin Drive ni Gemini reales."""
from __future__ import annotations
from dataclasses import replace
from decimal import Decimal
from io import BytesIO
import unittest
from unittest.mock import Mock

from openpyxl import Workbook
from services.award_limits import (
    LimitsError, PILOT_MUNICIPALITY, parse_catalog, evaluate, infer_regime, infer_iva,
    infer_municipality, money, read_drive_catalog,
)
from services.contract_portfolio import prepare_contract_portfolio
from tests.test_contract_portfolio import _contract_v2_fixture

MUNICIPALITIES = (
    "Abasolo", "Acámbaro", "Apaseo el Alto", "Apaseo el Grande", "Atarjea",
    "Celaya", "Comonfort", "Coroneo", "Cortazar", "Cuerámaro", "Doctor Mora",
    "Dolores Hidalgo Cuna de la Independencia Nacional", "Guanajuato",
    "Huanímaro", "Irapuato", "Jaral del Progreso", "Jerécuaro", "León",
    "Manuel Doblado", "Moroleón", "Ocampo", "Pénjamo", "Pueblo Nuevo",
    "Purísima del Rincón", "Romita", "Salamanca", "Salvatierra",
    "San Diego de la Unión", "San Felipe", "San Francisco del Rincón",
    "San José Iturbide", "San Luis de la Paz", "San Miguel de Allende",
    "Santa Catarina", "Santa Cruz de Juventino Rosas", "Santiago Maravatío",
    "Silao de la Victoria", "Tarandacuao", "Tarimoro", "Tierra Blanca",
    "Uriangato", "Valle de Santiago", "Victoria", "Villagrán", "Xichú", "Yuriria",
)


def fixture_catalog():
    wb = Workbook()
    m = wb.active
    m.title = "Base municipal"
    m.append(["Año","Municipio","Municipio_normalizado","Grupo",
        "Clave_Año_Municipio","AD_max_sin_IVA","LS_min_sin_IVA",
        "LS_max_sin_IVA","LP_min_sin_IVA","Decreto",
        "Referencia_poblacion","Fuente_URL"])
    s = wb.create_sheet("Base estatal")
    s.append(["Año","AD mín. sin IVA","AD máx. sin IVA","LS desde sin IVA",
        "LS máx. sin IVA","LP desde sin IVA","Decreto","Artículo",
        "Fuente oficial (URL)"])
    for year in range(2021, 2027):
        for muni in MUNICIPALITIES:
            from services.award_limits import fold
            norm=fold(muni).upper()
            group = "C" if muni=="León" else "B"
            if muni=="Cortazar":
                group = "B" if year <= 2022 else "C"
            m.append([year,muni,norm,group,f"{year}|{norm}",
                3445834.13,3445834.14,6202501.43,6202501.44,55,
                "CONAPO 2023","https://congresogto.gob.mx/example"])
        s.append([year,0.01,3546779.31,3546779.32,15414848.54,
                  15414848.55,58,76,"https://finanzas.guanajuato.gob.mx/example"])
    buf=BytesIO()
    wb.save(buf)
    return buf.getvalue()


def contract(**overrides):
    record = prepare_contract_portfolio(_contract_v2_fixture()).records[0]
    fields = {
        **(record.full_values or {}),
        "legislacion_citada": (
            "Ley de Obra Pública y Servicios Relacionados con la Misma "
            "para el Estado y los Municipios de Guanajuato (LOPYSRM)"
        ),
        "fuente_financiamiento": "RECURSO MUNICIPAL",
        "obra_servicio": "REHABILITACIÓN DE CAMINOS EN EL MUNICIPIO DE LEÓN, GTO.",
        "fecha_firma_contrato": "15 de diciembre de 2025",
        "modalidad_adjudicacion": "ADJUDICACIÓN DIRECTA",
        "monto_contrato": "$2,172,571.00 (IVA incluido)",
    }
    fields.update(overrides)
    return replace(record,full_values=fields)


class LimitsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = parse_catalog(fixture_catalog())

    def test_six_years_46_municipalities_and_canonical_key(self):
        self.assertEqual(len(self.catalog.municipal),276)
        self.assertEqual(len(self.catalog.estatal),6)
        self.assertEqual(self.catalog.municipal[(2025,"LEON")].group,"C")
        self.assertEqual(self.catalog.municipal[(2022,"CORTAZAR")].group,"B")
        self.assertEqual(self.catalog.municipal[(2023,"CORTAZAR")].group,"C")

    def test_municipal_lopysrm_resources_and_iva(self):
        r=evaluate(contract(),self.catalog)
        self.assertEqual(r.regime,"Municipal")
        self.assertEqual(r.year,2025)
        self.assertEqual(r.municipality,"León")
        self.assertEqual(r.method,"ADJUDICACIÓN DIRECTA")
        self.assertEqual(r.net,Decimal("1872906.03"))
        self.assertEqual(r.state,"Dentro del límite")
        self.assertEqual(r.row.sheet,"Base municipal")
        self.assertEqual(r.row.group,"C")
        self.assertEqual(r.row.decree,"55")

    def test_state_funding_picks_state_sheet(self):
        r=evaluate(contract(fuente_financiamiento="RECURSO ESTATAL"),self.catalog)
        self.assertEqual(r.regime,"Estatal")
        self.assertEqual(r.row.sheet,"Base estatal")
        self.assertEqual(r.row.article,"76")

    def test_ad_at_max_and_one_cent_over(self):
        r=evaluate(contract(monto_contrato="$3,445,834.13 sin IVA"),self.catalog)
        self.assertEqual(r.state,"Dentro del límite")
        above=evaluate(contract(monto_contrato="$3,445,834.14 sin IVA"),self.catalog)
        self.assertEqual(above.state,"Excede el límite")
        self.assertEqual(above.margin,Decimal("-0.01"))

    def test_simplified_and_public_tiers(self):
        a=contract(modalidad_adjudicacion="Licitación simplificada",
                   monto_contrato="$6,202,501.43 sin IVA")
        self.assertEqual(evaluate(a,self.catalog).state,"Dentro del límite")
        b=contract(modalidad_adjudicacion="Licitación simplificada",
                   monto_contrato="$6,202,501.44 sin IVA")
        self.assertEqual(evaluate(b,self.catalog).state,"Excede el límite")
        c=contract(modalidad_adjudicacion="Licitación pública",
                   monto_contrato="$6,202,501.44 sin IVA")
        self.assertEqual(evaluate(c,self.catalog).state,"Dentro del rango de LP")
        d=contract(modalidad_adjudicacion="Licitación pública",
                   monto_contrato="$1,500,000.00 sin IVA")
        self.assertEqual(evaluate(d,self.catalog).state,"Procedimiento más competitivo")

    def test_unknown_iva_never_assumed(self):
        r=evaluate(contract(monto_contrato="$2,172,571.00"),self.catalog)
        self.assertEqual(r.state,"Requiere revisión")
        self.assertIsNone(r.net)
        override=evaluate(contract(monto_contrato="$2,172,571.00"),self.catalog,
                          iva="Con IVA (16%)")
        self.assertEqual(override.state,"Dentro del límite")
        self.assertTrue(any("manualmente" in x for x in override.warnings))

    def test_usd_and_eur_must_not_be_compared_with_peso_thresholds(self):
        for literal in ("USD 2,000,000.00 sin IVA", "€2,000,000.00 sin IVA"):
            with self.subTest(literal=literal):
                r=evaluate(contract(monto_contrato=literal),self.catalog)
                self.assertEqual(r.state,"Requiere revisión")
                self.assertIsNone(r.net)
                self.assertTrue(any("divisa" in x for x in r.warnings))

    def test_mixed_federal_and_inconclusive_are_not_approved(self):
        self.assertEqual(infer_regime("Ley de Obras Públicas y Servicios Relacionados "
                                     "con las Mismas", "Recurso municipal"),
                         "Federal (fuera de estas bases)")
        self.assertEqual(infer_regime("LOPYSRM","Recurso estatal y municipal"),
                         "Por confirmar")
        self.assertEqual(infer_regime("LOPYSRM","FAISM Ramo 33"),
                         "Por confirmar")
        self.assertEqual(evaluate(contract(fuente_financiamiento="Ramo 33"),self.catalog).state,
                         "Requiere revisión")

    def test_municipality_is_fixed_to_leon_when_contract_does_not_mention_it(self):
        self.assertEqual(PILOT_MUNICIPALITY, "León")
        for object_text in (
            "",
            "Rehabilitación de caminos rurales",
            "Rehabilitación en el municipio de Cortazar",
        ):
            with self.subTest(object_text=object_text):
                result = evaluate(contract(obra_servicio=object_text), self.catalog)
                self.assertEqual(result.municipality, "León")
                self.assertEqual(result.row.municipality, "León")
                self.assertEqual(result.row.group, "C")
                self.assertEqual(result.row.sheet, "Base municipal")
                self.assertEqual(result.state, "Dentro del límite")
                self.assertFalse(
                    any("Municipio no identificable" in w for w in result.warnings)
                )

    def test_leon_historical_group_is_selected_by_fiscal_year(self):
        for year in range(2021, 2027):
            with self.subTest(year=year):
                result = evaluate(contract(
                    fecha_firma_contrato=f"15 de diciembre de {year}",
                    obra_servicio="Sin referencia territorial",
                ), self.catalog)
                self.assertEqual(result.year, year)
                self.assertEqual(result.row.key, f"{year}|LEON")
                self.assertEqual(result.row.group, "C")

    def test_state_regime_is_independent_of_leon_group(self):
        result = evaluate(contract(
            fuente_financiamiento="RECURSO ESTATAL",
            obra_servicio="No indica municipio",
        ), self.catalog)
        self.assertEqual(result.municipality, "León")
        self.assertEqual(result.row.sheet, "Base estatal")
        self.assertEqual(result.row.group, "")

    def test_unsupported_year_and_missing_specialized_data(self):
        self.assertEqual(
            evaluate(contract(fecha_firma_contrato="1 de enero de 2027"),self.catalog).state,
            "Requiere revisión",
        )
        old=replace(contract(),full_values=None)
        self.assertEqual(evaluate(old,self.catalog).state,"Requiere revisión")

    def test_catalog_rejects_missing_sheet_and_discontinuous_ranges(self):
        wb=Workbook()
        wb.active.title="Base municipal"
        b=BytesIO()
        wb.save(b)
        with self.assertRaises(LimitsError):
            parse_catalog(b.getvalue())
        from services.award_limits import _check
        bad=replace(self.catalog.estatal[2025],lp_min=Decimal("15.00"))
        with self.assertRaises(LimitsError):
            _check(bad)

    def test_root_folder_security_no_cross_drives(self):
        service=Mock()
        root="A"*20
        # Sin carpeta Recursos no accede a ningún archivo externo.
        service.files.return_value.list.return_value.execute.return_value={"files":[]}
        with self.assertRaisesRegex(LimitsError,"Recursos"):
            read_drive_catalog(service,root)
        self.assertFalse(service.files.return_value.get_media.called)


if __name__ == "__main__":
    unittest.main()
