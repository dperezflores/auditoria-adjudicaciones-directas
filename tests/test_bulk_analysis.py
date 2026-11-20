"""Planificación multicarpeta: pruebas sin descargar PDFs ni llamar Gemini."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
import ast
import unittest

from services.analysis_catalog import FileStatus
from services.bulk_analysis import BulkItem, plan_bulk_analysis, BULK_CODES
from services.drive_service import DocumentRecord, DriveInventory, WorkRecord
from services.document_classifier import PDF_MIME


def _pdf(work_id: str, code: str, *, suffix: str = "") -> DocumentRecord:
    return DocumentRecord(
        id=f"{work_id}-{code}{suffix}",name=f"{code}.pdf",
        mime_type=PDF_MIME,parent_id=work_id,
        md5_checksum=f"md5-{work_id}-{code}{suffix}",size_bytes=4000,
    )


def _fixture():
    work1 = WorkRecord(
        id="folder0000001",name="009_Parque",
        pdfs=(_pdf("folder0000001","CONTRATO"),_pdf("folder0000001","PUC")),
    )
    work2 = WorkRecord(
        id="folder0000002",name="010_Rehabilitación",
        pdfs=(_pdf("folder0000002","CONTRATO"),_pdf("folder0000002","PUC")),
    )
    work3 = WorkRecord(id="folder0000003",name="011_Sin PDFs")
    inv=DriveInventory("root00000000","Expedientes",(work1,work2,work3),"2026-11-20")
    docs=[doc for work in inv.works for doc in work.pdfs]
    rows=[]
    for work in inv.works:
        for doc in work.pdfs:
            rows.append({
                "documento_id":doc.id,"obra_id":work.id,"activo":"SI",
                "md5_checksum":doc.md5_checksum,
                "tipo_documental":doc.name.split(".")[0],
                "resultado_id":"","estado_procesamiento":"Pendiente",
            })
    tables={"Documentos":rows,"Extracciones":[],"DatosContrato":[]}
    states={doc.id:FileStatus(doc.id,"Pendiente","Sin análisis","documental")
            for doc in docs}
    return inv,tables,states


class BulkPlannerTests(unittest.TestCase):
    def test_all_folders_both_document_types(self):
        inv,tables,states=_fixture()
        p=plan_bulk_analysis(inv,tables,states,[w.id for w in inv.works],BULK_CODES)
        self.assertEqual(p.folders,3)
        self.assertEqual(p.ready,4)
        self.assertEqual(p.count("No encontrado"),2)
        self.assertEqual(
            [(item.work.name,item.code) for item in p.pending],
            [("009_Parque","CONTRATO"),("009_Parque","PUC"),
             ("010_Rehabilitación","CONTRATO"),("010_Rehabilitación","PUC")],
        )

    def test_subset_and_only_puc_or_contracts(self):
        inv,tables,states=_fixture()
        selected=[inv.works[1].id]
        for typ in BULK_CODES:
            with self.subTest(typ=typ):
                p=plan_bulk_analysis(inv,tables,states,selected,[typ])
                self.assertEqual(p.ready,1)
                self.assertEqual(p.pending[0].code,typ)
                self.assertEqual(p.pending[0].work.id,selected[0])

    def test_cached_specialized_document_is_not_sent_again(self):
        inv,tables,states=_fixture()
        doc=inv.works[0].pdfs[0]
        row=next(r for r in tables["Documentos"] if r["documento_id"]==doc.id)
        row["resultado_id"]="cache00000001"
        tables["Extracciones"].append({
            "cache_key":"cache00000001","version_esquema":"contrato-v2",
            "estado":"COMPLETADO","resultado_json":'{"campos":[]}',
            "documento_id":doc.id,"obra_id":inv.works[0].id,
        })
        states[doc.id]=FileStatus(doc.id,"Analizado","Guardado","contrato",
                                   "cache00000001")
        p=plan_bulk_analysis(inv,tables,states,[inv.works[0].id],["CONTRATO","PUC"])
        self.assertEqual(p.ready,1)
        self.assertEqual(p.pending[0].code,"PUC")
        self.assertEqual(p.count("Ya analizado"),1)

    def test_uncertain_attempt_blocks_even_when_another_extraction_exists(self):
        inv,tables,states=_fixture()
        doc=inv.works[0].pdfs[0]
        tables["Extracciones"].append({
            "cache_key":"pending0001","version_esquema":"contrato-v2",
            "estado":"EN_PROCESO","resultado_json":"",
            "documento_id":doc.id,"obra_id":inv.works[0].id,
        })
        p=plan_bulk_analysis(inv,tables,states,[inv.works[0].id],["CONTRATO"])
        self.assertEqual(p.ready,0)
        self.assertEqual(p.count("Bloqueado"),1)

    def test_stale_registration_and_size_cannot_be_processed(self):
        inv,tables,states=_fixture()
        row=tables["Documentos"][0]
        row["md5_checksum"]="wrong"
        p=plan_bulk_analysis(inv,tables,states,[inv.works[0].id],["CONTRATO"])
        self.assertEqual(p.ready,0)
        self.assertEqual(p.count("Desactualizado"),1)
        row["md5_checksum"]=inv.works[0].pdfs[0].md5_checksum
        work=inv.works[0]
        oversize=replace(work.pdfs[0],size_bytes=50_000_001)
        changed=replace(work,pdfs=(oversize,*work.pdfs[1:]))
        newinv=replace(inv,works=(changed,*inv.works[1:]))
        p=plan_bulk_analysis(newinv,tables,states,[work.id],["CONTRATO"])
        self.assertEqual(p.count("Bloqueado"),1)
        self.assertEqual(p.ready,0)

    def test_duplicate_documents_in_same_work_are_ambiguous(self):
        inv,tables,states=_fixture()
        work=inv.works[0]
        dup=_pdf(work.id,"CONTRATO",suffix="copy")
        changed=replace(work,pdfs=(*work.pdfs,dup))
        newinv=replace(inv,works=(changed,*inv.works[1:]))
        p=plan_bulk_analysis(newinv,tables,states,[work.id],["CONTRATO"])
        self.assertEqual(p.count("Ambiguo"),1)
        self.assertEqual(p.ready,0)

    def test_unrecognized_or_wrong_folder_selection_is_rejected(self):
        inv,tables,states=_fixture()
        for selected,codes in (
            ([],["CONTRATO"]),(["unknown"],["PUC"]),
            ([inv.works[0].id],[]),([inv.works[0].id],["DICTAMEN_AD"]),
        ):
            with self.subTest(selected=selected,codes=codes):
                with self.assertRaises(ValueError):
                    plan_bulk_analysis(inv,tables,states,selected,codes)

    def test_irrelevant_documents_never_enter_bulk_plan(self):
        inv,tables,states=_fixture()
        work=inv.works[0]
        other=DocumentRecord(id="other0000001",name="ORDEN_AD.pdf",
                             md5_checksum="other",size_bytes=900,mime_type=PDF_MIME)
        changed=replace(work,pdfs=(*work.pdfs,other))
        newinv=replace(inv,works=(changed,*inv.works[1:]))
        p=plan_bulk_analysis(newinv,tables,states,[work.id],BULK_CODES)
        self.assertEqual(p.ready,2)
        self.assertTrue(all(item.code in BULK_CODES for item in p.pending))

    def test_ui_keeps_single_folder_mode_and_requires_confirmation(self):
        path=Path(__file__).resolve().parents[1]/"ui"/"expedientes.py"
        source=path.read_text(encoding="utf-8")
        ast.parse(source)
        for phrase in (
            '"Una carpeta", "Varias carpetas"',
            '"Todas las carpetas", "Seleccionar varias carpetas"',
            'key="ex_bulk_selected_folders"',
            'key="ex_bulk_codes"',
            'key="ex_bulk_approve"',
            'key="ex_bulk_analyze"',
            'disabled=disabled, key="ex_bulk_analyze"',
            'batch = plan.pending[:MAX_BATCH]',
            'st.session_state.pop("award_limits_contracts", None)',
            'st.session_state.pop("results_portfolio", None)',
            'st.session_state["ex_last_run"] = _analyze(obra, batch, model)',
        ):
            self.assertIn(phrase,source)

    def test_bulk_runner_preserves_original_analysis_function_per_work(self):
        from ui.expedientes import _run_bulk_batch
        inv,_,_=_fixture()
        b=(
            BulkItem(inv.works[0],inv.works[0].pdfs[0],"CONTRATO"),
            BulkItem(inv.works[0],inv.works[0].pdfs[1],"PUC"),
            BulkItem(inv.works[1],inv.works[1].pdfs[0],"CONTRATO"),
        )
        with patch("ui.expedientes._analyze") as analyze:
            analyze.side_effect=[
                [{"Documento":"CONTRATO.pdf","Resultado":"Analizado y guardado"},
                 {"Documento":"PUC.pdf","Resultado":"Analizado y guardado"}],
                [{"Documento":"CONTRATO.pdf","Resultado":"Analizado y guardado"}],
            ]
            log=_run_bulk_batch(b,"gemini-test")
        self.assertEqual(analyze.call_count,2)
        self.assertEqual(len(analyze.call_args_list[0].args[1]),2)
        self.assertEqual(len(analyze.call_args_list[1].args[1]),1)
        self.assertEqual(len(log),3)
        self.assertEqual(log[-1]["Carpeta"],"010_Rehabilitación")
        with self.assertRaisesRegex(ValueError,"10 PDFs"):
            _run_bulk_batch(b*4,"gemini-test")


if __name__=="__main__":
    unittest.main()
