"""Pruebas de Drive 100% simuladas: sin credenciales, redes ni tokens."""
from __future__ import annotations

import unittest

from services.drive_service import (
    FOLDER_MIME,
    PDF_MIME,
    DriveConfigurationError,
    is_configured,
    scan_drive,
    validate_id,
)

ROOT = "folderROOT123"
WORK = "folderWORK456"


class _Request:
    def __init__(self, response):
        self.response = response

    def execute(self):
        return self.response


class _Files:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def get(self, **kwargs):
        self.calls.append(("get", kwargs))
        return _Request(self.data["root"])

    def list(self, **kwargs):
        self.calls.append(("list", kwargs))
        parent = kwargs["q"].split("'")[1]
        token = kwargs.get("pageToken", "")
        return _Request(self.data["children"].get((parent, token), {"files": []}))


class _Service:
    def __init__(self, data):
        self.client = _Files(data)

    def files(self):
        return self.client


class DriveTests(unittest.TestCase):
    def sample_data(self):
        return {
            "root": {"id": ROOT, "name": "AUDITORIA_AD_PILOTO", "mimeType": FOLDER_MIME},
            "children": {
                (ROOT, ""): {
                    "files": [
                        {"id": WORK, "name": "Obra 001", "mimeType": FOLDER_MIME},
                        {"id": "fileOTHER123", "name": "texto.txt", "mimeType": "text/plain"},
                    ]
                },
                (WORK, ""): {
                    "files": [
                        {"id": "filePDF1111", "name": "PUC.pdf", "mimeType": PDF_MIME,
                         "md5Checksum": "abcd1234", "modifiedTime": "2026-11-07T10:00:00Z"},
                        {"id": "filePDF2222", "name": "Contrato.pdf", "mimeType": PDF_MIME},
                        {"id": "fileOTHER456", "name": "Imagen.jpg", "mimeType": "image/jpeg"},
                    ]
                },
            },
        }

    def test_obras_and_pdf_are_detected(self):
        service = _Service(self.sample_data())
        result = scan_drive(service, ROOT)
        self.assertEqual(len(result.works), 1)
        self.assertEqual(result.works[0].name, "Obra 001")
        self.assertEqual(result.pdf_total, 2)
        self.assertEqual(result.works[0].pdfs[0].name, "Contrato.pdf")
        self.assertEqual(result.works[0].pdfs[1].md5_checksum, "abcd1234")
        self.assertEqual(result.works[0].pdfs[0].id, "filePDF2222")

    def test_pagination_no_documents_lost(self):
        data = self.sample_data()
        data["children"][(WORK, "")] = {
            "files": [{"id": "filePDF1111", "name": "Uno.pdf", "mimeType": PDF_MIME}],
            "nextPageToken": "NEXT",
        }
        data["children"][(WORK, "NEXT")] = {
            "files": [{"id": "filePDF2222", "name": "Dos.pdf", "mimeType": PDF_MIME}]
        }
        service = _Service(data)
        self.assertEqual(scan_drive(service, ROOT).pdf_total, 2)
        self.assertTrue(any(x[1].get("pageToken") == "NEXT" for x in service.client.calls))

    def test_empty_works_are_preserved(self):
        data = self.sample_data()
        data["children"][(WORK, "")] = {"files": []}
        result = scan_drive(_Service(data), ROOT)
        self.assertEqual(len(result.works), 1)
        self.assertEqual(result.pdf_total, 0)

    def test_duplicate_names_have_distinct_ids(self):
        data = self.sample_data()
        data["children"][(WORK, "")] = {"files": [
            {"id": "filePDF1111", "name": "Contrato.pdf", "mimeType": PDF_MIME},
            {"id": "filePDF2222", "name": "Contrato.pdf", "mimeType": PDF_MIME},
        ]}
        result = scan_drive(_Service(data), ROOT)
        self.assertEqual(len({d.id for d in result.works[0].pdfs}), 2)

    def test_reject_invalid_root_id(self):
        with self.assertRaises(DriveConfigurationError):
            validate_id("xyz' and trashed = false")
        with self.assertRaises(DriveConfigurationError):
            scan_drive(_Service(self.sample_data()), "bad")

    def test_incomplete_secrets_are_not_configured(self):
        self.assertFalse(is_configured({}))
        self.assertFalse(is_configured({"drive": {"root_folder_id": ROOT}}))
        self.assertFalse(is_configured({"gcp_service_account": {"client_email": "test"}}))

    def test_nested_pdf_inside_work_is_detected(self):
        data = self.sample_data()
        folder_id = "nestedFOLDER123"
        data["children"][(WORK, "")] = {"files": [
            {"id": folder_id, "name": "01 Contratos", "mimeType": FOLDER_MIME},
        ]}
        data["children"][(folder_id, "")] = {"files": [
            {"id": "nestedPDF00001", "name": "Contrato_obra.pdf",
             "mimeType": PDF_MIME, "md5Checksum": "abc"},
        ]}
        result = scan_drive(_Service(data), ROOT)
        self.assertEqual(result.pdf_total, 1)
        doc = result.works[0].pdfs[0]
        self.assertEqual(doc.parent_id, folder_id)
        self.assertEqual(doc.relative_path, "01 Contratos")

    def test_scan_nested_folders_with_same_name_distinct_ids(self):
        data = self.sample_data()
        a, b = "nestedFOLDER123", "nestedFOLDER234"
        data["children"][(WORK, "")] = {"files": [
            {"id": a, "name": "Anexos", "mimeType": FOLDER_MIME},
            {"id": b, "name": "Anexos", "mimeType": FOLDER_MIME},
        ]}
        data["children"][(a, "")] = {"files": [
            {"id": "nestedPDF00001", "name": "PUC.pdf", "mimeType": PDF_MIME}
        ]}
        data["children"][(b, "")] = {"files": [
            {"id": "nestedPDF00002", "name": "PUC.pdf", "mimeType": PDF_MIME}
        ]}
        result = scan_drive(_Service(data), ROOT)
        self.assertEqual(result.pdf_total, 2)
        self.assertEqual(len({d.id for d in result.works[0].pdfs}), 2)

    def test_invalid_root_type_rejected(self):
        data = self.sample_data()
        data["root"]["mimeType"] = PDF_MIME
        with self.assertRaises(Exception):
            scan_drive(_Service(data), ROOT)


if __name__ == "__main__":
    unittest.main()
