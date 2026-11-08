"""Pruebas de persistencia sin Google Cloud ni llamadas a servicios externos."""
from __future__ import annotations

import unittest

from services.drive_service import DocumentRecord, DriveInventory, WorkRecord
from services.sheets_service import storage_configured, sync_to_sheets
from services.sync_engine import HEADERS, MODIFIED, SchemaMismatch, build_plan

WORK_ID = "workFolderTest100"
DOC_ID = "docDriveTest100"


def snapshot():
    return {name: [list(columns)] for name, columns in HEADERS.items()}


def inventory(*, name="Contrato.pdf", checksum="aaa", works=True, pdf=True):
    return DriveInventory(
        root_id="rootDriveTest100",
        root_name="AUDITORIA_AD_PILOTO",
        works=(WorkRecord(
            id=WORK_ID,
            name="Obra 001",
            pdfs=(DocumentRecord(
                id=DOC_ID, name=name, md5_checksum=checksum,
                modified_time="2026-11-07T12:00:00Z", size_bytes=100,
            ),) if pdf else (),
        ),) if works else (),
        synced_at="2026-11-08T01:00:00Z",
    )


def apply_plan(current, plan):
    """Aplica un batch simulado en memoria respetando número de fila."""
    target = {tab: [list(row) for row in rows] for tab, rows in current.items()}
    for write in plan.updates:
        rows = target[write.sheet]
        while len(rows) < write.row_number:
            rows.append([])
        rows[write.row_number - 1] = list(write.values)
    return target


def record(table, tab, ident):
    index = HEADERS[tab].index(HEADERS[tab][0])
    for row in table[tab][1:]:
        if row and row[index] == ident:
            return dict(zip(HEADERS[tab], row))
    raise LookupError(ident)


class SyncEngineTests(unittest.TestCase):
    def test_first_scan_adds_one_work_one_pdf_and_history(self):
        plan = build_plan(inventory(), snapshot(), now="2026-11-08T01:00:00Z", sync_id="first")
        self.assertEqual((plan.new_works, plan.new_pdfs, plan.modified_pdfs), (1, 1, 0))
        self.assertEqual(plan.events, 2)
        tables = apply_plan(snapshot(), plan)
        self.assertEqual(record(tables, "Documentos", DOC_ID)["md5_checksum"], "aaa")
        self.assertEqual(record(tables, "Obras", WORK_ID)["total_pdf"], "1")
        self.assertEqual(len(tables["Sincronizaciones"]), 2)

    def test_second_scan_does_not_duplicate_entities_or_events(self):
        tables = apply_plan(snapshot(), build_plan(inventory(), snapshot(), now="one"))
        plan = build_plan(inventory(), tables, now="two")
        self.assertEqual((plan.new_works, plan.new_pdfs, plan.events), (0, 0, 0))
        next_tables = apply_plan(tables, plan)
        self.assertEqual(len(next_tables["Obras"]), 2)
        self.assertEqual(len(next_tables["Documentos"]), 2)
        self.assertEqual(len(next_tables["Historial"]), len(tables["Historial"]))
        self.assertEqual(len(next_tables["Sincronizaciones"]), 3)
        self.assertEqual(record(next_tables, "Documentos", DOC_ID)["revision"], "1")

    def test_renaming_pdf_keeps_checksum_and_status(self):
        first = apply_plan(snapshot(), build_plan(inventory(), snapshot(), now="one"))
        plan = build_plan(inventory(name="Cambio_de_nombre.pdf"), first, now="two")
        self.assertEqual(plan.modified_pdfs, 0)
        second = apply_plan(first, plan)
        row = record(second, "Documentos", DOC_ID)
        self.assertEqual(row["estado_procesamiento"], "Pendiente")
        self.assertEqual(row["nombre_archivo"], "Cambio_de_nombre.pdf")
        self.assertEqual(row["md5_checksum"], "aaa")

    def test_changed_pdf_sets_flag_without_deleting_extraction(self):
        first = apply_plan(snapshot(), build_plan(inventory(), snapshot(), now="one"))
        row = first["Documentos"][1]
        row[HEADERS["Documentos"].index("estado_procesamiento")] = "Analizado"
        row[HEADERS["Documentos"].index("resultado_id")] = "extraction-123"
        plan = build_plan(inventory(checksum="bbb"), first, now="two")
        self.assertEqual(plan.modified_pdfs, 1)
        second = apply_plan(first, plan)
        result = record(second, "Documentos", DOC_ID)
        self.assertEqual(result["estado_procesamiento"], MODIFIED)
        self.assertEqual(result["resultado_id"], "extraction-123")

    def test_removed_file_remains_in_history_but_inactive(self):
        first = apply_plan(snapshot(), build_plan(inventory(), snapshot(), now="one"))
        plan = build_plan(inventory(pdf=False), first, now="two")
        self.assertEqual(plan.removed_pdfs, 1)
        second = apply_plan(first, plan)
        self.assertEqual(record(second, "Documentos", DOC_ID)["activo"], "NO")
        self.assertEqual(record(second, "Obras", WORK_ID)["total_pdf"], "0")

    def test_removed_folder_is_inactive(self):
        first = apply_plan(snapshot(), build_plan(inventory(), snapshot(), now="one"))
        second = apply_plan(first, build_plan(inventory(works=False), first, now="two"))
        self.assertEqual(record(second, "Obras", WORK_ID)["activo"], "NO")

    def test_reappearing_file_preserves_id_and_first_seen(self):
        first = apply_plan(snapshot(), build_plan(inventory(), snapshot(), now="one"))
        second = apply_plan(first, build_plan(inventory(pdf=False), first, now="two"))
        plan = build_plan(inventory(), second, now="three")
        third = apply_plan(second, plan)
        self.assertEqual(plan.new_pdfs, 0)
        self.assertEqual(record(third, "Documentos", DOC_ID)["activo"], "SI")
        self.assertEqual(record(third, "Documentos", DOC_ID)["primera_deteccion_utc"], "one")

    def test_new_document_does_not_modify_prior_record(self):
        first = apply_plan(snapshot(), build_plan(inventory(), snapshot(), now="one"))
        more = DriveInventory(
            root_id="rootDriveTest100", root_name="Test",
            works=(WorkRecord(id=WORK_ID, name="Obra 001", pdfs=(
                DocumentRecord(id=DOC_ID, name="Contrato.pdf", md5_checksum="aaa",
                               modified_time="2026-11-07T12:00:00Z", size_bytes=100),
                DocumentRecord(id="secondDocument100", name="PUC.pdf", md5_checksum="ccc"),
            )),),
            synced_at="two",
        )
        plan = build_plan(more, first, now="two")
        second = apply_plan(first, plan)
        self.assertEqual(plan.new_pdfs, 1)
        self.assertEqual(record(second, "Documentos", DOC_ID)["revision"], "1")
        self.assertEqual(record(second, "Documentos", "secondDocument100")["nombre_archivo"], "PUC.pdf")

    def test_schema_mismatch_stops_writes(self):
        bad = snapshot()
        bad["Documentos"][0][0] = "bad_header"
        with self.assertRaises(SchemaMismatch):
            build_plan(inventory(), bad)

    def test_duplicate_id_in_existing_sheet_stops(self):
        first = apply_plan(snapshot(), build_plan(inventory(), snapshot(), now="one"))
        first["Documentos"].append(list(first["Documentos"][1]))
        with self.assertRaises(SchemaMismatch):
            build_plan(inventory(), first)


class _Request:
    def __init__(self, result):
        self.result = result

    def execute(self):
        return self.result


class _Values:
    def __init__(self, tabs):
        self.tabs = tabs
        self.last_write = None

    def batchGet(self, **kwargs):
        return _Request({"valueRanges": [{"values": self.tabs[tab]} for tab in HEADERS]})

    def batchUpdate(self, **kwargs):
        self.last_write = kwargs["body"]["data"]
        return _Request({"totalUpdatedRows": len(self.last_write)})


class _Spreadsheets:
    def __init__(self, tabs):
        self.v = _Values(tabs)

    def values(self):
        return self.v


class _Client:
    def __init__(self, tabs):
        self.sheet = _Spreadsheets(tabs)

    def spreadsheets(self):
        return self.sheet


class SheetsServiceTests(unittest.TestCase):
    def test_saves_sync_in_single_batch(self):
        client = _Client(snapshot())
        plan = sync_to_sheets(client, "spreadsheetTest100", inventory())
        self.assertEqual(plan.new_pdfs, 1)
        ranges = [write["range"] for write in client.sheet.v.last_write]
        self.assertTrue(any(r.startswith("'Obras'!A2:") for r in ranges))
        self.assertTrue(any(r.startswith("'Documentos'!A2:") for r in ranges))
        self.assertTrue(any(r.startswith("'Sincronizaciones'!A2:") for r in ranges))

    def test_storage_requires_both_secret_sections(self):
        self.assertFalse(storage_configured({}))
        self.assertFalse(storage_configured({"storage": {"spreadsheet_id": "a" * 30}}))
        self.assertTrue(storage_configured({
            "storage": {"spreadsheet_id": "a" * 30},
            "gcp_service_account": {"client_email": "test", "private_key": "test"},
        }))


if __name__ == "__main__":
    unittest.main()
