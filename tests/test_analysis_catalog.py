"""Estados de carpetas/archivos y clasificación sin llamar a Drive ni a IA."""
import unittest

from services.analysis_catalog import file_states, folder_states, suggest_kind
from services.drive_service import DocumentRecord, DriveInventory, WorkRecord
from services.extraction_store import EXTRACTION_HEADERS, CONTRACT_HEADERS
from services.sync_engine import HEADERS

WORK = "folderWORK123"
D1 = "fileDOC12345"
D2 = "fileDOC67890"
KEY = "cachedResult123"


def fixture():
    inventory = DriveInventory(
        root_id="rootFOLDER123", root_name="Expedientes",
        works=(
            WorkRecord(id=WORK, name="Obra de prueba", pdfs=(
                DocumentRecord(id=D1, name="Contrato_AD.pdf", md5_checksum="abc"),
                DocumentRecord(id=D2, name="PUC.pdf", md5_checksum="puc"),
            )),
        ), synced_at="2026-11-08",
    )
    doc = dict(zip(HEADERS["Documentos"], [
        D1, WORK, "Contrato_AD.pdf", "", "application/pdf", "abc",
        "2026-11-08", "200", "Analizado", "2026", "2026",
        "SI", "", KEY, "", "1",
    ]))
    doc2 = dict(zip(HEADERS["Documentos"], [
        D2, WORK, "PUC.pdf", "", "application/pdf", "puc",
        "2026-11-08", "100", "Pendiente", "2026", "2026",
        "SI", "", "", "", "1",
    ]))
    done = dict(zip(EXTRACTION_HEADERS, [
        KEY, "COMPLETADO", D1, WORK, "sha", "gemini-model",
        "contrato-prompt-v3", "contrato-v1", "2026", "2026",
        '{"numero_contrato":{}}', "100", "20", "",
    ]))
    return inventory, {"Documentos":[doc,doc2],"Extracciones":[done],"DatosContrato":[]}


class CatalogTests(unittest.TestCase):
    def test_mixed_status_folder_is_partial(self):
        inv, tables=fixture()
        states=file_states(inv,tables)
        self.assertEqual(states[D1].label,"Analizado")
        self.assertEqual(states[D2].label,"Pendiente")
        folder=folder_states(inv,states)[WORK]
        self.assertEqual(folder.label,"Parcial")
        self.assertEqual((folder.complete,folder.total),(1,2))

    def test_all_analysed(self):
        inv,tables=fixture()
        row=tables["Documentos"][1]
        row["resultado_id"]="cache-puc"
        tables["Extracciones"].append(dict(zip(EXTRACTION_HEADERS,[
            "cache-puc","COMPLETADO",D2,WORK,"sha","gemini-model",
            "documento-prompt-v1","documento-schema-v1","2026",
            "2026",'{"resumen":"ok"}',"100","20",""
        ])))
        self.assertEqual(folder_states(inv,file_states(inv,tables))[WORK].label,"Analizada")

    def test_stale_documents_not_counted(self):
        inv,tables=fixture()
        tables["Documentos"][0]["md5_checksum"]="changed"
        states=file_states(inv,tables)
        self.assertEqual(states[D1].label,"Desactualizado")

    def test_partial_result_with_saved_fields(self):
        inv,tables=fixture()
        tables["Extracciones"][0]["estado"]="REQUIERE_REVISION"
        tables["Extracciones"][0]["resultado_json"]=""
        row = dict(zip(CONTRACT_HEADERS,[KEY,WORK,D1,"AD-001",
                                        "", "", "", "", "", "", "", "","2026"]))
        tables["DatosContrato"].append(row)
        self.assertEqual(file_states(inv,tables)[D1].label,"Parcial")

    def test_missing_registration(self):
        inv,tables=fixture()
        tables["Documentos"]=[]
        self.assertEqual(file_states(inv,tables)[D1].label,"Sin registrar")

    def test_no_pdf_folder(self):
        inv=DriveInventory("rootFOLDER123","Test",(WorkRecord("xFOLDER0001","Obra"),),"now")
        self.assertEqual(folder_states(inv,{})["xFOLDER0001"].label,"Sin PDF")

    def test_heuristic_contrato_and_puc(self):
        self.assertEqual(suggest_kind("CONTRATO-001.pdf"),"contrato")
        self.assertEqual(suggest_kind("PUC_Contratista.pdf"),"documental")
        self.assertEqual(suggest_kind("Convenio_contrato.pdf"),"documental")


if __name__=="__main__":
    unittest.main()
