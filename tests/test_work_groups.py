"""Grupos de obras: migración por mover carpetas preservando IDs y datos.

Todos los escenarios usan metadatos Drive simulados y hojas en memoria.
No hay IA, no se mueve ningún archivo real ni se llama a Google.
"""
from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock
import unittest

from services.drive_service import (
    DriveGroupCatalog, FOLDER_MIME, DriveInventory, scan_drive,
    list_drive_groups,
)
from services.work_groups import (
    ALL_GROUPS, UNGROUPED, catalog_from_inventory, group_options,
    included_work_id, selected_inventory, selected_records,
)
from services.sheets_service import (
    InventoryProtectionError, assert_existing_works_preserved,
    sync_to_sheets,
)
from services.sync_engine import HEADERS, build_plan
from tests.test_drive_service import _Service, ROOT, WORK, DriveTests
from tests.test_sync_engine import snapshot, apply_plan, record


GROUP = "groupFolderABC123"
SECOND = "secondWorkABC123"


def _layout(*, move_work=False, group_prefix="GRUPO_Auditoria"):
    data = DriveTests().sample_data()
    root = list(data["children"][(ROOT, "")]["files"])
    group = {"id": GROUP, "name": group_prefix, "mimeType": FOLDER_MIME}
    data["children"][(ROOT, "")]["files"] = (
        [group, *root[1:]] if move_work else [*root, group]
    )
    data["children"][(GROUP, "")] = {"files": [
        root[0] if move_work else {
            "id": SECOND, "name": "002", "mimeType": FOLDER_MIME,
        }
    ]}
    if not move_work:
        data["children"][(SECOND, "")] = {"files": []}
    return data


class GroupMigrationTests(unittest.TestCase):
    def test_original_work_id_and_pdf_ids_survive_moving_into_group(self):
        source = scan_drive(_Service(DriveTests().sample_data()), ROOT)
        moved = scan_drive(_Service(_layout(move_work=True)), ROOT)
        self.assertEqual(len(source.works), 1)
        self.assertEqual(len(moved.works), 1)
        self.assertEqual(moved.works[0].id, source.works[0].id)
        self.assertEqual(
            tuple(doc.id for doc in moved.works[0].pdfs),
            tuple(doc.id for doc in source.works[0].pdfs),
        )
        self.assertEqual(moved.works[0].group_id, GROUP)
        self.assertEqual(moved.works[0].group_name, "GRUPO_Auditoria")
        self.assertEqual(moved.works[0].name, "Obra 001")

    def test_analyzed_status_and_extraction_key_not_reset_by_move(self):
        old = scan_drive(_Service(DriveTests().sample_data()), ROOT)
        first = apply_plan(snapshot(), build_plan(old, snapshot(), now="first"))
        documents = first["Documentos"]
        for row in documents[1:]:
            row[HEADERS["Documentos"].index("estado_procesamiento")] = "Analizado"
            row[HEADERS["Documentos"].index("resultado_id")] = "cacheSaved0001"
        moved = scan_drive(_Service(_layout(move_work=True)), ROOT)
        assert_existing_works_preserved(moved, first)
        migration_plan = build_plan(moved, first, now="second")
        self.assertEqual(migration_plan.new_works, 0)
        self.assertEqual(migration_plan.new_pdfs, 0)
        self.assertEqual(migration_plan.removed_pdfs, 0)
        after = apply_plan(first, migration_plan)
        for row in after["Documentos"][1:]:
            saved = dict(zip(HEADERS["Documentos"], row))
            self.assertEqual(saved["estado_procesamiento"], "Analizado")
            self.assertEqual(saved["resultado_id"], "cacheSaved0001")
            self.assertEqual(saved["activo"], "SI")
        self.assertEqual(record(after, "Obras", WORK)["activo"], "SI")

    def test_empty_group_is_not_counted_as_an_obra(self):
        data = _layout(move_work=True)
        data["children"][(GROUP, "")] = {"files": []}
        result = scan_drive(_Service(data), ROOT)
        self.assertEqual(len(result.works), 0)
        self.assertEqual(len(result.groups), 1)

    def test_subfolders_inside_an_obra_are_not_treated_as_work_groups(self):
        data = DriveTests().sample_data()
        nested = "docsNested99999"
        data["children"][(WORK, "")]["files"].append({
            "id": nested, "name": "GRUPO_Anexos", "mimeType": FOLDER_MIME,
        })
        data["children"][(nested, "")] = {"files": []}
        result = scan_drive(_Service(data), ROOT)
        self.assertEqual(len(result.works), 1)
        self.assertEqual(result.works[0].group_id, "")

    def test_direct_numbered_folders_remain_works(self):
        data = DriveTests().sample_data()
        data["children"][(ROOT, "")]["files"][0]["name"] = "001"
        result = scan_drive(_Service(data), ROOT)
        self.assertEqual(result.works[0].name, "001")
        self.assertEqual(result.works[0].group_id, "")

    def test_named_group_can_be_declared_by_folder_id(self):
        data = _layout(move_work=True, group_prefix="01 - Auditoria")
        result = scan_drive(_Service(data), ROOT, group_folder_ids=[GROUP])
        self.assertEqual(result.groups[0].name, "01 - Auditoria")
        self.assertEqual(result.works[0].id, WORK)
        self.assertEqual(result.works[0].group_id, GROUP)

    def test_group_catalog_only_lists_folder_metadata(self):
        service = _Service(_layout(move_work=True))
        catalog = list_drive_groups(service, ROOT)
        self.assertEqual(catalog.work_to_group[WORK], GROUP)
        self.assertEqual(catalog.groups[0].name, "GRUPO_Auditoria")
        # No acceder a PDFs dentro de la carpeta de obra para el filtro.
        queried = [
            kwargs["q"] for op, kwargs in service.client.calls if op == "list"
        ]
        self.assertFalse(any(f"'{WORK}'" in q for q in queried))

    def test_filters_preserve_global_overview_and_use_drive_ids(self):
        source = scan_drive(_Service(_layout(move_work=False)), ROOT)
        catalog = catalog_from_inventory(source)
        self.assertEqual(len(source.works), 2)
        self.assertEqual(len(selected_inventory(source, catalog, ALL_GROUPS).works), 2)
        direct = selected_inventory(source, catalog, UNGROUPED)
        grouped = selected_inventory(source, catalog, GROUP)
        self.assertEqual([w.id for w in direct.works], [WORK])
        self.assertEqual([w.id for w in grouped.works], [SECOND])
        self.assertEqual(group_options(catalog), (ALL_GROUPS, UNGROUPED, GROUP))
        self.assertFalse(included_work_id("unknown_id", catalog, GROUP))
        self.assertTrue(included_work_id(WORK, catalog, ALL_GROUPS))
        rows = (
            type("Record", (), {"obra_id": WORK})(),
            type("Record", (), {"obra_id": SECOND})(),
        )
        self.assertEqual(len(selected_records(rows, catalog, GROUP)), 1)
        self.assertEqual(selected_records(rows, catalog, GROUP)[0].obra_id, SECOND)

    def test_missing_original_work_blocks_sync_before_writing(self):
        old = scan_drive(_Service(DriveTests().sample_data()), ROOT)
        existing = apply_plan(snapshot(), build_plan(old, snapshot(), now="initial"))
        # El usuario movió la obra bajo una carpeta ordinaria no declarada
        # como grupo. Si sincronizáramos, la obra se archivaría por error.
        misplaced = scan_drive(
            _Service(_layout(move_work=True, group_prefix="Carpeta desconocida")),
            ROOT,
        )
        with self.assertRaisesRegex(InventoryProtectionError, "bloqueada"):
            assert_existing_works_preserved(misplaced, existing)

    def test_missing_existing_pdf_blocks_sync_without_writes(self):
        old = scan_drive(_Service(DriveTests().sample_data()), ROOT)
        existing = apply_plan(snapshot(), build_plan(old, snapshot(), now="initial"))
        empty_work = replace(old.works[0], pdfs=(), other_files=())
        incomplete = replace(old, works=(empty_work,))
        with self.assertRaises(InventoryProtectionError):
            assert_existing_works_preserved(incomplete, existing)

    def test_sync_preflight_protection_does_not_write_to_sheets(self):
        old = scan_drive(_Service(DriveTests().sample_data()), ROOT)
        existing = apply_plan(snapshot(), build_plan(old, snapshot(), now="initial"))
        missing = replace(old, works=())
        sheets = Mock()
        sheets.spreadsheets.return_value.values.return_value.batchGet.return_value.execute.return_value = {
            "valueRanges": [
                {"values": existing[tab]} for tab in HEADERS
            ],
        }
        with self.assertRaises(InventoryProtectionError):
            sync_to_sheets(sheets, "idSheetABC123456789000", missing, protect_existing=True)
        sheets.spreadsheets.return_value.values.return_value.batchUpdate.assert_not_called()

    def test_global_group_filter_is_applied_in_every_operational_view(self):
        root = Path(__file__).resolve().parents[1]
        app = (root / "app.py").read_text("utf-8")
        self.assertIn('key="work_group_selection"', app)
        self.assertIn("list_drive_groups(", app)
        for path in (
            "ui/expedientes.py", "ui/resultados.py",
            "ui/pruebas_adjudicacion.py", "ui/capital_contable.py",
            "ui/puc_validity.py",
        ):
            text = (root / path).read_text("utf-8")
            with self.subTest(path=path):
                ast.parse(text)
                self.assertIn('st.session_state.get("work_group_selection"', text)
        self.assertIn("protect_existing=True", (root / "ui/expedientes.py").read_text("utf-8"))
        self.assertIn("selected_inventory(", (root / "ui/expedientes.py").read_text("utf-8"))


if __name__ == "__main__":
    unittest.main()
