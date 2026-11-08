"""Pruebas de caché, consumo único, reserva y errores (sin red ni Gemini)."""
from __future__ import annotations

import re
import unittest

from services.contract_schema import ExtraccionContrato
from services.drive_service import DocumentRecord
from services.extraction_store import (
    ExtractionStateError, extract_or_reuse, recover_saved_fields,
)
from services.gemini_service import GeminiResult
from services.gemini_errors import GeminiRequestError
from services.extraction_cache import crear_clave_cache
from services.extraction_store import PROMPT_VERSION
from services.contract_schema import SCHEMA_VERSION


EXTRACTION_HEADERS = [
    "cache_key", "estado", "documento_id", "obra_id", "sha256_pdf",
    "modelo", "version_prompt", "version_esquema", "creado_utc",
    "actualizado_utc", "resultado_json", "tokens_entrada",
    "tokens_salida", "ultimo_error",
]
CONTRACT_HEADERS = [
    "cache_key", "obra_id", "documento_id", "numero_contrato", "nombre_obra",
    "contratista", "fecha_firma", "fecha_inicio", "fecha_termino",
    "monto_con_iva", "porcentaje_anticipo", "campos_a_revisar", "extraido_utc",
]
DOCUMENT_HEADERS = [
    "documento_id", "obra_id", "nombre_archivo", "tipo_documental",
    "mime_type", "md5_checksum", "fecha_modificacion_drive", "tamano_bytes",
    "estado_procesamiento", "primera_deteccion_utc", "ultima_deteccion_utc",
    "activo", "version_extractor", "resultado_id", "ultimo_error", "revision",
]

DOC_ID = "docFicticioABC123"
OBRA_ID = "obraFicticiaABC123"
PDF = b"%PDF-1.7 simulated bytes"


def make_extraction():
    fields = {
        k: {"valor": None, "pagina": None, "evidencia": None}
        for k in (
            "numero_contrato", "nombre_obra", "contratista", "fecha_firma",
            "fecha_inicio", "fecha_termino", "monto_con_iva", "porcentaje_anticipo",
        )
    }
    fields["numero_contrato"] = {
        "valor": "AD-001", "pagina": 1, "evidencia": "CONTRATO AD-001"
    }
    fields["observaciones"] = []
    return ExtraccionContrato.model_validate(fields)


class FakeRequest:
    def __init__(self, response):
        self.response = response

    def execute(self):
        return self.response


class FakeValues:
    def __init__(self):
        self.tables = {
            "Extracciones": [EXTRACTION_HEADERS.copy()],
            "DatosContrato": [CONTRACT_HEADERS.copy()],
            "Documentos": [DOCUMENT_HEADERS.copy(), [
                DOC_ID, OBRA_ID, "Contrato_SIMULADO.pdf", "", "application/pdf",
                "md5simulado", "2026-11-08T00:00:00Z", "20",
                "Pendiente", "2026-11-08T00:00:00Z", "2026-11-08T00:00:00Z",
                "SI", "", "", "", "1",
            ]],
        }
        self.writes = 0
        self.simulate_confirmation_failure = False

    def batchGet(self, **kwargs):
        result = []
        for r in kwargs["ranges"]:
            name = r.split("'")[1]
            result.append({"values": self.tables[name]})
        return FakeRequest({"valueRanges": result})

    def batchUpdate(self, **kwargs):
        entries = kwargs["body"]["data"]
        for entry in entries:
            # "'Documentos'!M2:O2" or "'Extracciones'!A2:N2"
            match = re.fullmatch(
                r"'([^']+)'!([A-Z]+)([0-9]+)(?::([A-Z]+)([0-9]+))?",
                entry["range"],
            )
            if not match:
                raise AssertionError(entry["range"])
            name, first_col, first_row, _, _ = match.groups()
            number = int(first_row)
            col = 0
            for char in first_col:
                col = col * 26 + (ord(char) - 64)
            col -= 1
            table = self.tables[name]
            while len(table) < number:
                table.append([])
            row = table[number - 1]
            new_values = entry["values"][0]
            if len(row) < col + len(new_values):
                row.extend([""] * (col + len(new_values) - len(row)))
            row[col:col + len(new_values)] = new_values
        self.writes += 1
        unique_rows = {
            (entry["range"].split("'")[1], re.search(r"[0-9]+", entry["range"]).group())
            for entry in entries
        }
        return FakeRequest({
            "totalUpdatedRows": len(unique_rows),
            "responses": (
                [] if self.simulate_confirmation_failure and len(entries) > 1
                else [
                    {"updatedRows": 1, "updatedRange": entry["range"]}
                    for entry in entries
                ]
            ),
        })


class FakeSheets:
    def __init__(self):
        self.store = FakeValues()

    def spreadsheets(self):
        return self

    def values(self):
        return self.store


class ExtractionStoreTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeSheets()
        self.doc = DocumentRecord(
            id=DOC_ID, name="Contrato_SIMULADO.pdf",
            md5_checksum="md5simulado", modified_time="2026-11-08T00:00:00Z",
            size_bytes=20,
        )
        self.calls = 0

    def invoke(self, payload, key, *, model):
        self.calls += 1
        self.assertEqual(payload, PDF)
        self.assertEqual(model, "gemini-3.5-flash-lite")
        return GeminiResult(make_extraction(), input_tokens=50, output_tokens=20)

    def run_analysis(self, **kwargs):
        return extract_or_reuse(
            self.client, "sheet-123", PDF, self.doc, OBRA_ID, "private-key",
            model="gemini-3.5-flash-lite", invoke=self.invoke, **kwargs
        )

    def test_first_call_and_second_call_from_cache(self):
        first = self.run_analysis()
        self.assertFalse(first.cached)
        self.assertEqual(self.calls, 1)
        self.assertEqual(len(self.client.store.tables["Extracciones"]), 2)
        self.assertEqual(len(self.client.store.tables["DatosContrato"]), 2)
        self.assertEqual(self.client.store.tables["Extracciones"][1][1], "COMPLETADO")
        self.assertEqual(self.client.store.tables["Documentos"][1][8], "Requiere validación")
        second = self.run_analysis()
        self.assertTrue(second.cached)
        self.assertEqual(self.calls, 1)
        self.assertEqual(second.extraction.numero_contrato.valor, "AD-001")
        self.assertEqual(len(self.client.store.tables["Extracciones"]), 2)

    def test_sheets_counts_three_distinct_rows_for_four_ranges(self):
        first = self.run_analysis()
        self.assertFalse(first.cached)
        self.assertEqual(self.calls, 1)
        # Se actualizan Extracciones, DatosContrato y Documentos;
        # dos rangos de Documentos se refieren a LA MISMA fila.
        self.assertEqual(self.client.store.writes, 2)
        self.assertEqual(self.client.store.tables["Extracciones"][1][1], "COMPLETADO")

    def test_recover_partial_saved_fields_without_provider_call(self):
        self.run_analysis()
        previous_calls = self.calls
        attempt = self.client.store.tables["Extracciones"][1]
        attempt[1] = "REQUIERE_REVISION"
        attempt[10] = ""
        attempt[13] = "ExtractionStateError"

        before = repr(self.client.store.tables)
        recovered = recover_saved_fields(
            self.client, "sheet-123", PDF, self.doc, OBRA_ID,
            model="gemini-3.5-flash-lite",
        )
        self.assertIsNotNone(recovered)
        self.assertTrue(recovered.recovered_partial)
        self.assertTrue(recovered.cached)
        self.assertEqual(recovered.extraction.numero_contrato.valor, "AD-001")
        self.assertIsNone(recovered.extraction.numero_contrato.evidencia)
        self.assertIsNone(recovered.extraction.numero_contrato.pagina)
        self.assertEqual(self.calls, previous_calls)
        self.assertEqual(repr(self.client.store.tables), before)

    def test_no_reservation_overwrite_after_unconfirmed_post_write(self):
        self.client.store.simulate_confirmation_failure = True
        with self.assertRaisesRegex(ExtractionStateError, "Gemini devolvió"):
            self.run_analysis()
        attempt = self.client.store.tables["Extracciones"][1]
        self.assertEqual(attempt[1], "COMPLETADO")
        self.assertTrue(attempt[10])
        self.assertEqual(len(self.client.store.tables["DatosContrato"]), 2)
        self.assertEqual(self.calls, 1)
        # La siguiente carga usa el resultado completo ya persistido;
        # no debe generar otra petición.
        self.client.store.simulate_confirmation_failure = False
        cached = self.run_analysis()
        self.assertTrue(cached.cached)
        self.assertEqual(self.calls, 1)

    def test_renaming_keeps_cache(self):
        self.run_analysis()
        self.doc = DocumentRecord(
            id=DOC_ID, name="Contrato_SIMULADO_RENOMBRADO.pdf",
            md5_checksum="md5simulado", modified_time="2026-11-08T00:00:00Z",
            size_bytes=20,
        )
        result = self.run_analysis()
        self.assertTrue(result.cached)
        self.assertEqual(self.calls, 1)

    def test_modified_pdf_gets_new_cache_key(self):
        self.run_analysis()
        self.client.store.tables["Documentos"][1][5] = "nueva-huella"
        self.doc = DocumentRecord(
            id=DOC_ID, name="Contrato_SIMULADO.pdf",
            md5_checksum="nueva-huella",
        )
        result = extract_or_reuse(
            self.client, "sheet-123", b"%PDF-1.7 modified",
            self.doc, OBRA_ID, "private-key", invoke=lambda *_args, **_kwargs: GeminiResult(
                make_extraction(), input_tokens=30, output_tokens=15
            ),
        )
        self.assertFalse(result.cached)
        self.assertEqual(len(self.client.store.tables["Extracciones"]), 3)

    def test_failed_invoke_marks_uncertain_and_blocks_retry(self):
        def bad(_pdf, _key, *, model):
            self.calls += 1
            raise RuntimeError("Provider error sensitive details")

        with self.assertRaisesRegex(ExtractionStateError, "No se confirmó"):
            extract_or_reuse(
                self.client, "sheet-123", PDF, self.doc, OBRA_ID,
                "private-key", invoke=bad,
            )
        self.assertEqual(self.client.store.tables["Extracciones"][1][1], "REQUIERE_REVISION")
        self.assertEqual(self.client.store.tables["Extracciones"][1][13], "RuntimeError")
        with self.assertRaises(ExtractionStateError):
            self.run_analysis()
        self.assertEqual(self.calls, 1)

    def test_api_error_records_only_http_status(self):
        def bad(_pdf, _key, *, model):
            raise GeminiRequestError(400, "INVALID_ARGUMENT")

        with self.assertRaisesRegex(
            ExtractionStateError, "HTTP_400_INVALID_ARGUMENT"
        ):
            extract_or_reuse(
                self.client, "sheet-123", PDF, self.doc,
                OBRA_ID, "private-key", invoke=bad,
            )
        row = self.client.store.tables["Extracciones"][1]
        self.assertEqual(row[1], "REQUIERE_REVISION")
        self.assertEqual(row[13], "HTTP_400_INVALID_ARGUMENT")
        self.assertNotIn("private-key", str(row))
        with self.assertRaises(ExtractionStateError):
            self.run_analysis()
        self.assertEqual(self.calls, 0)

    def test_explicit_retry_after_failure(self):
        def bad(_pdf, _key, *, model):
            raise RuntimeError("not available")
        with self.assertRaises(ExtractionStateError):
            extract_or_reuse(
                self.client, "sheet-123", PDF, self.doc, OBRA_ID,
                "private-key", invoke=bad,
            )
        result = self.run_analysis(allow_retry=True)
        self.assertFalse(result.cached)
        self.assertEqual(self.client.store.tables["Extracciones"][1][1], "COMPLETADO")

    def test_unsynchronized_document_never_calls_model(self):
        self.client.store.tables["Documentos"] = [DOCUMENT_HEADERS.copy()]
        with self.assertRaisesRegex(ExtractionStateError, "Sincroniza Drive"):
            self.run_analysis()
        self.assertEqual(self.calls, 0)

    def test_inactive_document_never_calls_model(self):
        self.client.store.tables["Documentos"][1][11] = "NO"
        with self.assertRaises(ExtractionStateError):
            self.run_analysis()
        self.assertEqual(self.calls, 0)

    def test_inconsistent_md5_never_calls_model(self):
        self.client.store.tables["Documentos"][1][5] = "changed"
        with self.assertRaises(ExtractionStateError):
            self.run_analysis()
        self.assertEqual(self.calls, 0)

    def test_same_pdf_different_model_changes_cache_key(self):
        old = crear_clave_cache(
            PDF, modelo="gemini-3.5-flash-lite",
            version_prompt=PROMPT_VERSION,
            version_esquema=SCHEMA_VERSION,
        )
        new = crear_clave_cache(
            PDF, modelo="gemini-3.6-flash",
            version_prompt=PROMPT_VERSION,
            version_esquema=SCHEMA_VERSION,
        )
        self.assertNotEqual(old.clave, new.clave)


if __name__ == "__main__":
    unittest.main()
