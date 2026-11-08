"""Tabla contractual: 16 campos + personas en una celda, sin modificar textos."""
from __future__ import annotations

from decimal import Decimal
import unittest

from services.contract_table import contract_table_rows, participant_cell
from services.contract_portfolio import ContractRecord
from services.contract_v2 import FIELD_LABELS_V2


def make_record(*, modern: bool = True) -> ContractRecord:
    literals = {
        "numero_contrato": "  A-001/2026  ",
        "obra_servicio": "REHABILITACIÓN DE CAMINOS, 2A ETAPA.",
        "tipo_contrato": "A PRECIOS UNITARIOS Y TIEMPO DETERMINADO",
        "contratista": "CONSTRUCTORA DEL BAJÍO, S.A. DE C.V.",
        "registro_puc": "SOPI/PUC:123.2025",
        "rfc": "ABCD012345EF1",
        "representante_legal": "ARQ. MARÍA LÓPEZ",
        "representante_tecnico": "ING. JOSÉ RAMÍREZ",
        "modalidad_adjudicacion": "ADJUDICACIÓN DIRECTA.",
        "monto_contrato": "$1,234,567.89 (I.V.A. incluido)",
        "fecha_inicio_contractual": "02 de JUNIO de 2026",
        "fecha_termino_contractual": "30 de SEPTIEMBRE del 2026",
        "fecha_firma_contrato": "4 de Mayo del año 2026",
        "anticipo": "30.00%",
        "fuente_financiamiento": "RECURSO MUNICIPAL, EJERCICIO 2026",
        "legislacion_citada": "LEY DE OBRA PÚBLICA Y SERVICIOS RELACIONADOS CON LA MISMA",
    }
    legacy = {
        "numero_contrato": literals["numero_contrato"],
        "nombre_obra": literals["obra_servicio"],
        "contratista": literals["contratista"],
        "fecha_firma": literals["fecha_firma_contrato"],
        "fecha_inicio": literals["fecha_inicio_contractual"],
        "fecha_termino": literals["fecha_termino_contractual"],
        "monto_con_iva": literals["monto_contrato"],
        "porcentaje_anticipo": literals["anticipo"],
    }
    return ContractRecord(
        obra_id="work", documento_id="doc", cache_key="cache",
        nombre_carpeta="Folder", documento="CNT_DIR_CNT.pdf",
        values=legacy, evidence={}, observations=("No se encontró firma al pie.",),
        state="COMPLETADO", extracted_at="2026-11-08",
        completeness=16 if modern else 8,
        amount=Decimal("1234567.89"), currency="MXN", signature_year="2026",
        source_schema="contrato-v2" if modern else "contrato-v1",
        full_values=literals if modern else None,
        participants=(
            {
                "nombre": "ARQ. MARÍA LÓPEZ",
                "cargo_o_caracter": "REPRESENTANTE LEGAL.",
                "representacion": "CONSTRUCTORA DEL BAJÍO, S.A. DE C.V.",
                "pagina": 10,
                "evidencia": "REPRESENTANTE LEGAL.",
            },
            {
                "nombre": "ING. JOSÉ RAMÍREZ",
                "cargo_o_caracter": "RESPONSABLE TÉCNICO",
                "representacion": "LA CONTRATISTA",
                "pagina": 11,
                "evidencia": "ING. JOSÉ RAMÍREZ",
            },
        ) if modern else (),
        normative_scope="Estatal (citado; por verificar)",
    )


class ContractTableTests(unittest.TestCase):
    def test_every_v2_field_is_a_column_in_specified_order(self):
        row = contract_table_rows((make_record(),))[0]
        self.assertEqual(
            list(row)[:len(FIELD_LABELS_V2)],
            [label for _, label in FIELD_LABELS_V2],
        )
        self.assertEqual(len(FIELD_LABELS_V2), 16)
        self.assertIn("Personas que participan en el contrato", row)
        self.assertEqual(row["Número de contrato"], "  A-001/2026  ")
        self.assertEqual(row["Monto del contrato"], "$1,234,567.89 (I.V.A. incluido)")
        self.assertEqual(row["Anticipo"], "30.00%")
        self.assertEqual(row["Legislación citada en el contrato"],
                         "LEY DE OBRA PÚBLICA Y SERVICIOS RELACIONADOS CON LA MISMA")

    def test_participants_stay_together_in_one_cell(self):
        row = contract_table_rows((make_record(),))[0]
        value = row["Personas que participan en el contrato"]
        self.assertIn("ARQ. MARÍA LÓPEZ | Cargo: REPRESENTANTE LEGAL.", value)
        self.assertIn("ING. JOSÉ RAMÍREZ | Cargo: RESPONSABLE TÉCNICO", value)
        self.assertIn("Representa a: LA CONTRATISTA", value)
        self.assertIn("; ", value)
        self.assertNotIn("Página", value)

    def test_legacy_contract_does_not_fabricate_new_fields(self):
        row = contract_table_rows((make_record(modern=False),))[0]
        self.assertEqual(row["Número de contrato"], "  A-001/2026  ")
        self.assertEqual(row["Registro PUC"] if "Registro PUC" in row else
                         row["Número de registro PUC"], "—")
        self.assertEqual(row["Representante técnico"], "—")
        self.assertEqual(row["Personas que participan en el contrato"], "—")
        self.assertEqual(row["Ámbito normativo preliminar"], "No determinado (versión anterior)")

    def test_multiple_records_stay_one_row_per_contract(self):
        rows = contract_table_rows((make_record(), make_record(modern=False)))
        self.assertEqual(len(rows), 2)
        self.assertEqual(list(rows[0]), list(rows[1]))

    def test_empty_participants_are_a_blank_placeholder(self):
        self.assertEqual(participant_cell(()), "—")


if __name__ == "__main__":
    unittest.main()
