"""Normalización GENERAL de representantes legales y fechas, sin Gemini.

Se utilizan variaciones contractuales de la muestra existente en Sheets,
además de variantes sintéticas y negativas para evitar falsos positivos.
No se agregan excepciones por carpeta, nombre o número de contrato.
"""
from __future__ import annotations

from dataclasses import replace
import unittest

from services.contract_display import short_date
from services.contract_role_rules import (
    authorized_legal_role, record_representation_fields,
)
from services.contract_table import contract_table_rows
from tests.test_contract_table import make_record


class GeneralLegalRoleTests(unittest.TestCase):
    def test_common_legal_designations_are_all_recognized(self):
        samples = (
            (
                "ING. HORACIO GONZALEZ GUTIERREZ",
                "Que el ING. HORACIO GONZALEZ GUTIERREZ está facultado para "
                "representarla legalmente en este acto, acreditando su "
                "personalidad como ADMINISTRADOR ÚNICO.",
            ),
            (
                "MIGUEL ANGEL NAVA ROMERO",
                "MIGUEL ANGEL NAVA ROMERO, en su carácter de "
                "SOCIO ADMINISTRADOR ÚNICO.",
            ),
            (
                "LIC. MARIA DE LOURDES MANILLA MATEOS",
                "C. LIC. MARIA DE LOURDES MANILLA MATEOS, en su "
                "carácter de APODERADO LEGAL.",
            ),
            (
                "C. MARIANO ARREOLA CALLEROS",
                "C. MARIANO ARREOLA CALLEROS, en su carácter de "
                "PRESIDENTE CONSEJO DE ADMINISTRACIÓN.",
            ),
            (
                "C. NOE GUILLERMO RAMIREZ SERNA",
                "representada en este acto por el C. NOE GUILLERMO "
                "RAMIREZ SERNA, en su carácter de representante legal.",
            ),
            (
                "LIC. CARLOS ALONSO MARTINEZ",
                "LIC. CARLOS ALONSO MARTINEZ actuando en nombre y "
                "representación de la contratista.",
            ),
            (
                "C. ARTURO INFANTE APOLINAR",
                "El C. ARTURO INFANTE APOLINAR está facultado para "
                "representarla legalmente en este acto.",
            ),
            (
                "ING. ROBERTO MANUEL PEREZ",
                "ING. ROBERTO MANUEL PEREZ, ADMINISTRADOR ÚNICO de la sociedad.",
            ),
        )
        for name, quote in samples:
            with self.subTest(name=name):
                self.assertTrue(
                    authorized_legal_role(name, quote),
                    f"Se ignoró una representación legal explícita: {quote}",
                )

    def test_conditional_representada_por_needs_contractor_in_quote(self):
        contractor="EMPRESA DE EJEMPLO, S.A. DE C.V."
        name="LIC. DANIEL FLORES HERNANDEZ"
        quote=(
            "EMPRESA DE EJEMPLO, S.A. DE C.V., representada en este acto "
            "por el LIC. DANIEL FLORES HERNANDEZ."
        )
        self.assertTrue(authorized_legal_role(name,quote,contractor))
        self.assertFalse(authorized_legal_role(name,quote))

    def test_unverified_roles_are_not_promoted_to_legal_representatives(self):
        name="ING. HORACIO GONZALEZ GUTIERREZ"
        unrelated=(
            "ING. HORACIO GONZALEZ GUTIERREZ firma como TESTIGO. "
            + "La sociedad fue administrada por otra persona. "*16
            + "La persona representante legal no consta en este apartado."
        )
        cases=(
            f"EL LABORATORIO: {name} (FIRMA).",
            f"EL CONTRATISTA: {name}, Ingeniero responsable de proyecto.",
            f"{name} en su carácter de DIRECTOR DE OBRA.",
            "OTRA PERSONA está facultada para representarla legalmente.",
            unrelated,
            "",
        )
        for quote in cases:
            with self.subTest(quote=quote[:45]):
                self.assertFalse(authorized_legal_role(name,quote))

    def test_normalized_results_general_without_overwriting_literal(self):
        record=make_record()
        fields=dict(record.full_values)
        name="MIGUEL ANGEL NAVA ROMERO"
        quote=(
            "MIGUEL ANGEL NAVA ROMERO, en su carácter de "
            "SOCIO ADMINISTRADOR ÚNICO."
        )
        fields["representante_legal"]=name
        current=replace(
            record,
            nombre_carpeta="CARPETA-CUALQUIERA",
            full_values=fields,
            evidence={"representante_legal":{
                "valor":name, "pagina":2,"evidencia":quote,
            }},
        )
        result=contract_table_rows((current,))[0]
        self.assertEqual(result["Representante legal"],name)
        self.assertEqual(current.full_values["representante_legal"],name)


class GeneralContractDateTests(unittest.TestCase):
    def test_prose_date_variants_are_normalized(self):
        valid={
            "27 des del mes de Abril del año de 2024":"27/04/2024",
            "27 de el mes de abril de 2024":"27/04/2024",
            "27 del mes de abril del 2024":"27/04/2024",
            "04 días del mes de Marzo del año de 2024":"04/03/2024",
            "23 del mes de Febrero del año de 2026":"23/02/2026",
            "el 26 del mes de Julio del año de 2025":"26/07/2025",
            "02 de Junio del 2025":"02/06/2025",
            "4 de Mayo del año 2026":"04/05/2026",
            "27/abril/2024":"27/04/2024",
            "27.abril.2024":"27/04/2024",
            "2024-04-27":"27/04/2024",
            "27/04/2024":"27/04/2024",
        }
        for literal,normalized in valid.items():
            with self.subTest(literal=literal):
                self.assertEqual(short_date(literal),normalized)

    def test_calendar_validation_and_ambiguity_remain_strict(self):
        invalid=(
            "31 des del mes de Abril del año de 2024",
            "29 de febrero de 2025",
            "33 del mes de Marzo del año de 2025",
            "04/03/2024 y 27/04/2024",
            "04 de marzo de 2024 y 27 des del mes de abril de 2024",
            "mes de abril del año de 2024",
            "4 de marzo de 24",
            "sin fecha cierta",
        )
        for literal in invalid:
            with self.subTest(literal=literal):
                self.assertEqual(short_date(literal),literal)

    def test_listed_2021_to_2026_dates_remain_valid_and_unmodified(self):
        dates=(
            ("13 del mes de Diciembre del año de 2021","13/12/2021"),
            ("26 del mes de Marzo del año de 2022","26/03/2022"),
            ("18 del mes de Octubre del año de 2025","18/10/2025"),
            ("03 días del mes de Diciembre del año de 2021","03/12/2021"),
            ("05 días del mes de Mayo del año de 2025","05/05/2025"),
            ("27 des del mes de Abril del año de 2024","27/04/2024"),
        )
        for raw,expected in dates:
            with self.subTest(raw=raw):
                self.assertEqual(short_date(raw),expected)


if __name__=="__main__":
    unittest.main()
