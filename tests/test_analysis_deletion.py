"""Borrado individual: estados, caché, trazabilidad y documentos ajenos."""
from __future__ import annotations

import unittest

from services.analysis_deletion import _TABLES, delete_analysis
from services.drive_service import DocumentRecord
from services.extraction_store import ExtractionStateError

DOC = "dictamenDocument1234"
PUC = "pucDocument5678"
WORK = "obraPruebaXYZ100"
OTHER = "obraPruebaXYZ200"
CACHE = "cacheDictamenTest1234"
PUC_CACHE = "cachePucTest1234567"


def row_for(name, mapping):
    header = _TABLES[name]
    return [str(mapping.get(col, "")) for col in header]


class Request:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self.data


class FakeSheets:
    def __init__(self):
        self.names = {n: i + 100 for i, n in enumerate(_TABLES)}
        self.reverse = {v: k for k, v in self.names.items()}
        self.data = {name: [list(headers)] for name, headers in _TABLES.items()}
        self.data["Documentos"] += [
            row_for("Documentos", dict(
                documento_id=DOC, obra_id=WORK, nombre_archivo="DICTAMEN_AD.pdf",
                tipo_documental="DICTAMEN_AD", mime_type="application/pdf",
                md5_checksum="md5Actual123", activo="SI",
                estado_procesamiento="Analizado", resultado_id=CACHE,
                version_extractor="gemini:dictamen-ad-prompt-v1", revision="1",
            )),
            row_for("Documentos", dict(
                documento_id=PUC, obra_id=OTHER, nombre_archivo="PUC.pdf",
                tipo_documental="PUC", mime_type="application/pdf",
                md5_checksum="md5Otro", activo="SI",
                estado_procesamiento="Analizado", resultado_id=PUC_CACHE,
                revision="2",
            )),
        ]
        self.data["Extracciones"] += [
            row_for("Extracciones", dict(
                cache_key=CACHE, estado="COMPLETADO", documento_id=DOC,
                obra_id=WORK, version_esquema="dictamen-ad-v1",
                resultado_json='{"irrelevante":"prueba"}',
            )),
            row_for("Extracciones", dict(
                cache_key=PUC_CACHE, estado="COMPLETADO", documento_id=PUC,
                obra_id=OTHER, version_esquema="puc-v1",
                resultado_json='{"puc":"conservar"}',
            )),
        ]
        self.data["DatosDictamenAD"] += [
            row_for("DatosDictamenAD", dict(
                cache_key=CACHE, documento_id=DOC, obra_id=WORK,
                numero_dictamen="DGOP/000/2026",
            )),
        ]
        self.data["DatosPUC"] += [
            row_for("DatosPUC", dict(
                cache_key=PUC_CACHE, documento_id=PUC, obra_id=OTHER,
                contratista="CONTRATISTA DE PRUEBA",
            )),
        ]
        self.data["RevisionesContrato"] += [
            row_for("RevisionesContrato", dict(
                revision_id="revision1", obra_id=WORK,
                documento_id=DOC, cache_key=CACHE, campo="fecha_firma",
                decision="Confirmado",
            )),
        ]
        self.data["Historial"] += [
            row_for("Historial", dict(
                evento_id="eventoViejo", entidad="Documento",
                entidad_id=PUC, obra_id=OTHER, tipo_cambio="Nuevo",
            )),
        ]
        self.calls = 0

    def spreadsheets(self):
        return self

    def values(self):
        return self

    def batchGet(self, **kwargs):
        ranges = kwargs["ranges"]
        return Request({"valueRanges": [
            {"values": self.data[term.split("!")[0].strip("'")]}
            for term in ranges
        ]})

    def get(self, **kwargs):
        return Request({"sheets": [
            {"properties": {
                "sheetId": self.names[name], "title": name,
                "gridProperties": {"rowCount": 1000, "columnCount": 30},
            }}
            for name in _TABLES
        ]})

    def batchUpdate(self, **kwargs):
        requests = kwargs["body"]["requests"]
        self.calls += 1
        for req in requests:
            key, change = next(iter(req.items()))
            if key == "deleteDimension":
                rg = change["range"]
                table = self.data[self.reverse[rg["sheetId"]]]
                del table[rg["startIndex"]:rg["endIndex"]]
            elif key == "updateCells":
                rg = change["range"]
                table = self.data[self.reverse[rg["sheetId"]]]
                vals = change["rows"][0]["values"]
                for j, val in enumerate(vals):
                    table[rg["startRowIndex"]][rg["startColumnIndex"] + j] = (
                        val["userEnteredValue"]["stringValue"]
                    )
            elif key == "repeatCell":
                rg = change["range"]
                table = self.data[self.reverse[rg["sheetId"]]]
                for col in range(rg["startColumnIndex"], rg["endColumnIndex"]):
                    table[rg["startRowIndex"]][col] = ""
            elif key == "appendCells":
                table = self.data[self.reverse[change["sheetId"]]]
                table.append([
                    val["userEnteredValue"]["stringValue"]
                    for val in change["rows"][0]["values"]
                ])
            else:
                raise AssertionError("Solicitud inesperada: " + key)
        return Request({"replies": [{} for _ in requests]})


class DeleteAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeSheets()
        self.doc = DocumentRecord(
            id=DOC, name="DICTAMEN_AD.pdf", mime_type="application/pdf",
            md5_checksum="md5Actual123",
        )

    def delete(self, **options):
        params = dict(
            expected_result_id=CACHE,
            actor_email="auditor@example.com",
        )
        params.update(options)
        return delete_analysis(self.client, "spreadsheet-id", self.doc, WORK, **params)

    def test_deletes_only_target_and_preserves_other_document(self):
        out = self.delete()
        self.assertEqual(out.attempts_deleted, 1)
        self.assertEqual(out.detail_rows_deleted, 1)
        self.assertEqual(out.review_rows_deleted, 1)
        self.assertEqual(len(self.client.data["Extracciones"]), 2)
        self.assertEqual(self.client.data["Extracciones"][1][0], PUC_CACHE)
        self.assertEqual(len(self.client.data["DatosDictamenAD"]), 1)
        self.assertEqual(self.client.data["DatosPUC"][1][3], "CONTRATISTA DE PRUEBA")
        self.assertEqual(self.client.data["Documentos"][1][8], "Pendiente")
        self.assertEqual(self.client.data["Documentos"][1][12:15], ["", "", ""])
        self.assertEqual(self.client.data["Documentos"][2][13], PUC_CACHE)
        self.assertEqual(self.client.data["Historial"][2][6], "Análisis eliminado")
        self.assertIn("auditor@example.com", self.client.data["Historial"][2][9])

    def test_rejects_stale_result_and_wrong_md5_without_writes(self):
        with self.assertRaises(ExtractionStateError):
            self.delete(expected_result_id="otraClave")
        self.doc = DocumentRecord(
            id=DOC, name="DICTAMEN_AD.pdf", mime_type="application/pdf",
            md5_checksum="otroMd5",
        )
        with self.assertRaises(ExtractionStateError):
            self.delete()
        self.assertEqual(self.client.calls, 0)

    def test_in_progress_extraction_cannot_be_deleted(self):
        self.client.data["Extracciones"][1][1] = "EN_PROCESO"
        with self.assertRaises(ExtractionStateError):
            self.delete()
        self.assertEqual(self.client.calls, 0)

    def test_cannot_delete_analysis_twice_without_any_result(self):
        self.delete()
        with self.assertRaises(ExtractionStateError):
            self.delete(expected_result_id="")
        self.assertEqual(self.client.calls, 1)

    def test_removes_multiple_attempts_in_descending_order(self):
        extra = row_for("Extracciones", dict(
            cache_key="oldCacheDictamen", estado="REQUIERE_REVISION",
            documento_id=DOC, obra_id=WORK,
        ))
        # Another file remains between the two target rows.
        self.client.data["Extracciones"].append(extra)
        out = self.delete()
        self.assertEqual(out.attempts_deleted, 2)
        self.assertEqual(len(self.client.data["Extracciones"]), 2)
        self.assertEqual(self.client.data["Extracciones"][1][0], PUC_CACHE)

    def test_actor_email_and_sheet_headers_required(self):
        with self.assertRaises(ExtractionStateError):
            self.delete(actor_email="")
        self.client.data["DatosPUC"][0][0] = "OTHER"
        with self.assertRaises(ExtractionStateError):
            self.delete()
        self.assertEqual(self.client.calls, 0)


if __name__ == "__main__":
    unittest.main()
