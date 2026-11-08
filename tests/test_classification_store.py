"""Persistencia de clasificación confirmada sin IA ni otros cambios."""
import unittest

from services.classification_store import ClassificationStoreError, save_confirmed_type
from services.document_classifier import Classification, PDF_MIME, XLSX_MIME
from services.drive_service import DocumentRecord
from services.sync_engine import HEADERS

DOCUMENT_ID = "documentTest100"
WORK = "folderTest100"


class Request:
    def __init__(self, obj):
        self.obj = obj
    def execute(self):
        return self.obj


class Values:
    def __init__(self):
        self.rows = [list(HEADERS["Documentos"]), [
            DOCUMENT_ID, WORK, "PUC.pdf", "", PDF_MIME, "abc123",
            "2026-11-08", "35000", "Pendiente", "now", "now",
            "SI", "", "", "", "1",
        ]]
        self.write = None

    def get(self, **kwargs):
        return Request({"values": self.rows})

    def update(self, **kwargs):
        self.write = kwargs
        return Request({"updatedCells": 1})


class Sheets:
    def __init__(self):
        self.v = Values()

    def spreadsheets(self):
        return self

    def values(self):
        return self.v


class ClassificationStorageTests(unittest.TestCase):
    def setUp(self):
        self.sheets = Sheets()
        self.doc = DocumentRecord(
            id=DOCUMENT_ID, name="PUC.pdf", mime_type=PDF_MIME,
            md5_checksum="abc123",
        )

    def test_saves_confirmed_code_only_at_type_column(self):
        confirmed = Classification("PUC", "Confirmado", "Contenido legible", True)
        save_confirmed_type(
            self.sheets, "sheetTest100", self.doc, WORK, confirmed
        )
        call = self.sheets.v.write
        self.assertEqual(call["range"], "'Documentos'!D2")
        self.assertEqual(call["body"]["values"], [["PUC"]])
        self.assertEqual(call["valueInputOption"], "RAW")

    def test_unconfirmed_and_invalid_do_not_write(self):
        with self.assertRaises(ClassificationStoreError):
            save_confirmed_type(
                self.sheets, "sheetTest100", self.doc, WORK,
                Classification("PUC", "Sugerido", "Por nombre", False)
            )
        self.assertIsNone(self.sheets.v.write)

    def test_wrong_folder_or_md5_does_not_write(self):
        confirmed = Classification("PUC", "Confirmado", "Contenido", True)
        for doc, work in [
            (self.doc, "anotherFolder"),
            (DocumentRecord(id=DOCUMENT_ID, name="PUC.pdf",
                            md5_checksum="different"), WORK),
        ]:
            with self.assertRaises(ClassificationStoreError):
                save_confirmed_type(self.sheets, "sheetTest100", doc, work, confirmed)
        self.assertIsNone(self.sheets.v.write)

    def test_excel_mime_must_match_registered_format(self):
        excel = DocumentRecord(
            id=DOCUMENT_ID, name="CATALOGO.xlsx", mime_type=XLSX_MIME,
            md5_checksum="abc123",
        )
        with self.assertRaises(ClassificationStoreError):
            save_confirmed_type(
                self.sheets, "sheetTest100", excel, WORK,
                Classification("CATALOGO", "Confirmado", "Excel", True),
            )


if __name__ == "__main__":
    unittest.main()
