"""Regresión y equivalencia de elegibilidad antigua versus explorador nuevo.

El oráculo legacy() replica el bucle de ui/expedientes.py en main; cualquier
cambio en quién se envía a Gemini/Excel debe fallar aquí antes del despliegue.
"""
from __future__ import annotations

import unittest
from dataclasses import replace

from services.analysis_catalog import FileStatus
from services.document_classifier import XLSX_MIME, code_from_filename
from services.drive_service import DocumentRecord, MAX_PDF_BYTES, MAX_XLSX_BYTES
from services.selection_rules import MAX_BATCH, plan_work_selection

WORK = "workABC123456"
PDF = "application/pdf"
SCHEMAS = {
    "CONTRATO": "contrato-v2", "PUC": "puc-v1",
    "DICTAMEN_AD": "dictamen-ad-v1",
    "NOTIFICACION_AD": "notificacion-ad-v1",
    "ORDEN_AD": "orden-ad-v1",
    "CATALOGO": "catalogo-xlsx-v1",
}


def doc(identifier, name, *, size=1_000_000, mime=PDF, md5="unchanged"):
    return DocumentRecord(
        id=identifier, name=name, size_bytes=size, mime_type=mime,
        md5_checksum=md5,
    )


def setup_cases():
    docs = [
        doc("pending", "CONTRATO.pdf"),
        doc("done", "PUC.pdf"),
        doc("pendingOld", "DICTAMEN_AD.pdf"),
        doc("blocked", "NOTIFICACION_AD.pdf"),
        doc("catalog", "CATALOGO.xlsx", mime=XLSX_MIME),
        doc("size", "ORDEN_AD.pdf", size=MAX_PDF_BYTES + 1),
        doc("zero", "PUC .pdf", size=0),
        doc("wrong", "No_Identificado.pdf"),
        doc("outdated", "CONTRATO.pdf", md5="new-checksum"),
        doc("no_reg", "PUC.pdf"),
        doc("wrong_work", "PUC.pdf"),
        doc("inactive", "PUC.pdf"),
    ]
    registered = {
        item.id: {
            "documento_id": item.id, "obra_id": WORK, "activo": "SI",
            "md5_checksum": item.md5_checksum,
            "tipo_documental": code_from_filename(item.name, item.mime_type),
            "resultado_id": "",
        } for item in docs if item.id not in {"no_reg"}
    }
    registered["done"]["resultado_id"] = "cacheDone"
    registered["blocked"]["resultado_id"] = "cacheBlocked"
    registered["pendingOld"]["resultado_id"] = "old-v1"
    registered["wrong_work"]["obra_id"] = "anotherWork"
    registered["inactive"]["activo"] = "NO"
    registered["outdated"]["md5_checksum"] = "old-checksum"
    extractions = {
        "cacheDone": {
            "cache_key": "cacheDone", "version_esquema": "puc-v1",
            "estado": "COMPLETADO", "resultado_json": '{"ok":true}',
            "documento_id": "done", "obra_id": WORK,
        },
        "cacheBlocked": {
            "cache_key": "cacheBlocked", "version_esquema": "notificacion-ad-v1",
            "estado": "EN_PROCESO", "resultado_json": "",
            "documento_id": "blocked", "obra_id": WORK,
        },
        "old-v1": {
            "cache_key": "old-v1", "version_esquema": "documento-schema-v1",
            "estado": "COMPLETADO", "resultado_json": '{"old":true}',
            "documento_id": "pendingOld", "obra_id": WORK,
        },
    }
    states = {
        item.id: FileStatus(item.id, "Analizado" if item.id == "done" else "Pendiente", "", "")
        for item in docs
    }
    return docs, registered, extractions, states


def legacy(docs, registered, extractions, states):
    """Oráculo copiado fielmente del tramo original de ui/expedientes.py."""
    eligible = [
        d for d in docs
        if code_from_filename(d.name, d.mime_type) in SCHEMAS
    ]
    to_process = []
    reused = 0
    blocked = 0
    needs_sync = 0
    for d in eligible:
        limit = MAX_XLSX_BYTES if d.mime_type == XLSX_MIME else MAX_PDF_BYTES
        if not (0 < d.size_bytes <= limit):
            continue
        row = registered.get(d.id)
        if not row or row["obra_id"] != WORK or row["activo"] != "SI":
            continue
        code = code_from_filename(d.name, d.mime_type)
        schema = SCHEMAS.get(code)
        if row["md5_checksum"] != d.md5_checksum or row["tipo_documental"] != code:
            needs_sync += 1
            continue
        pending_attempt = any(
            e["documento_id"] == d.id and e["obra_id"] == WORK
            and e["version_esquema"] == schema
            and e["estado"] in ("EN_PROCESO", "REQUIERE_REVISION")
            for e in extractions.values()
        )
        if pending_attempt:
            blocked += 1
            continue
        saved = extractions.get(row["resultado_id"])
        if (
            saved and saved["version_esquema"] == schema
            and states[d.id].label == "Analizado"
            and saved["estado"] == "COMPLETADO" and saved["resultado_json"]
            and saved["documento_id"] == d.id and saved["obra_id"] == WORK
        ):
            reused += 1
            continue
        if states[d.id].label != "Sin registrar":
            to_process.append(d)
    return tuple(to_process[:MAX_BATCH]), tuple(to_process), reused, blocked, needs_sync


class EligibilityParity(unittest.TestCase):
    def test_all_legacy_classifications_match_real_selection(self):
        docs, registered, extractions, states = setup_cases()
        old_batch, old_all, reused, blocked, needs_sync = legacy(
            docs, registered, extractions, states
        )
        new = plan_work_selection(
            WORK, docs, registered, extractions, states,
            SCHEMAS, extraction_rows=tuple(extractions.values()),
        )
        self.assertEqual([x.id for x in new.batch], [x.id for x in old_batch])
        self.assertEqual([x.id for x in new.eligible], [x.id for x in old_all])
        self.assertEqual(len(new.reused), reused)
        self.assertEqual(len(new.blocked), blocked)
        self.assertEqual(len(new.needs_sync), needs_sync)
        self.assertEqual([x.id for x in new.batch], ["pending", "pendingOld", "catalog"])
        self.assertIn("done", [x.id for x in new.reused])
        self.assertEqual(len(new.not_registered), 3)
        self.assertEqual(set(x.id for x in new.ignored), {"size", "zero", "wrong"})
        self.assertEqual(new.decisions["done"].selectable, False)
        self.assertTrue(new.decisions["catalog"].selectable)

    def test_incomplete_same_schema_blocks_but_old_schema_does_not(self):
        docs, registered, extractions, states = setup_cases()
        extractions["cacheBlocked"]["estado"] = "REQUIERE_REVISION"
        current = plan_work_selection(WORK, docs, registered, extractions, states, SCHEMAS)
        self.assertEqual(len(current.blocked), 1)
        self.assertEqual(current.decisions["pendingOld"].disposition, "eligible")

    def test_closure_over_more_than_ten_and_order_preserved(self):
        docs, registered, extractions, states = setup_cases()
        docs = docs[:1] + [
            doc(f"puc{i}", "PUC.pdf") for i in range(14)
        ]
        for item in docs[1:]:
            registered[item.id] = {
                "documento_id": item.id, "obra_id": WORK, "activo": "SI",
                "md5_checksum": item.md5_checksum, "tipo_documental": "PUC",
                "resultado_id": "",
            }
            states[item.id] = FileStatus(item.id, "Pendiente", "", "")
        plan = plan_work_selection(WORK, docs, registered, extractions, states, SCHEMAS)
        old_batch, _, _, _, _ = legacy(docs, registered, extractions, states)
        self.assertEqual([d.id for d in plan.batch], [d.id for d in old_batch])
        self.assertEqual(len(plan.batch), MAX_BATCH)
        self.assertEqual(len(plan.eligible), 15)
        self.assertTrue(plan.has_next_batch)

    def test_missing_expected_file_cannot_be_selected(self):
        docs, registered, extractions, states = setup_cases()
        plan = plan_work_selection(WORK, docs, registered, extractions, states, SCHEMAS)
        self.assertNotIn("missing-puc", plan.decisions)
        self.assertNotIn("missing-puc", plan.eligible_ids)

    def test_modified_checksum_and_cache_version_rejected(self):
        docs, registered, extractions, states = setup_cases()
        plan = plan_work_selection(WORK, docs, registered, extractions, states, SCHEMAS)
        self.assertEqual(plan.decisions["outdated"].disposition, "needs_sync")
        self.assertEqual(plan.decisions["pendingOld"].disposition, "eligible")
        extractions["cacheDone"]["documento_id"] = "other-document"
        plan = plan_work_selection(WORK, docs, registered, extractions, states, SCHEMAS)
        self.assertEqual(plan.decisions["done"].disposition, "eligible")

    def test_limit_still_ten_and_different_work_is_not_eligible(self):
        docs, registered, extractions, states = setup_cases()
        with self.assertRaises(ValueError):
            plan_work_selection(WORK, docs, registered, extractions, states, SCHEMAS,
                                max_batch=11)
        plan = plan_work_selection("different", docs, registered, extractions, states, SCHEMAS)
        self.assertFalse(plan.eligible)
        self.assertFalse(plan.reused)
        self.assertEqual(plan.decisions["pending"].disposition, "not_registered")

    def test_missing_or_unrecognised_are_not_permitted(self):
        docs, registered, extractions, states = setup_cases()
        plan = plan_work_selection(WORK, docs, registered, extractions, states, SCHEMAS)
        for identifier in ("wrong", "size", "zero", "no_reg", "wrong_work", "inactive"):
            self.assertFalse(plan.decisions[identifier].selectable)

    def test_catalog_never_requires_gemini_and_different_format_is_not_allowed(self):
        docs, registered, extractions, states = setup_cases()
        plan = plan_work_selection(WORK, docs, registered, extractions, states, SCHEMAS)
        self.assertEqual(plan.decisions["catalog"].schema, "catalogo-xlsx-v1")
        self.assertEqual(next(d for d in plan.batch if d.id == "catalog").mime_type, XLSX_MIME)
        modified = [replace(d, mime_type=PDF) if d.id == "catalog" else d for d in docs]
        plan = plan_work_selection(WORK, modified, registered, extractions, states, SCHEMAS)
        self.assertEqual(plan.decisions["catalog"].disposition, "ignored")


if __name__ == "__main__":
    unittest.main()
