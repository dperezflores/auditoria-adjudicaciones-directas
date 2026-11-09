"""Datos sintéticos SOLO para ver el diseño en una app sin Drive ni Sheets.

No contiene información real, claves, enlaces ni resultados de Gemini.
Ninguna acción del modo de muestra puede abrir Drive o ejecutar análisis.
"""
from __future__ import annotations

from services.drive_service import DocumentRecord, DriveInventory, WorkRecord, PDF_MIME, XLSX_MIME
from services.document_classifier import code_from_filename
from services.analysis_catalog import file_states


def visual_preview():
    def sample(identifier: str, name: str, mb: float, date: str = "2026-10-29T12:30:00Z",
               *, mime: str = PDF_MIME, path: str = "") -> DocumentRecord:
        return DocumentRecord(
            id=identifier, name=name, size_bytes=round(mb*1_000_000),
            mime_type=mime, md5_checksum=f"demo-checksum-{identifier}",
            modified_time=date, relative_path=path,
        )

    work_a = WorkRecord(
        id="DEMO_WORK_A", name="EJEMPLO_001_Rehabilitación_Parque",
        pdfs=(
            sample("DA1", "CONTRATO.pdf", 5.28),
            sample("DA2", "PUC .pdf", 1.86),
            sample("DA3", "DICTAMEN_AD.pdf", 0.83),
            sample("DA4", "NOTIFICACION_AD.pdf", 0.39, path="01_Adjudicación"),
            sample("DA5", "ORDEN_AD.pdf", 0.44, path="01_Adjudicación"),
        ),
        other_files=(
            sample("DA6", "CATALOGO.xlsx", 0.12, mime=XLSX_MIME),
            sample("DA7", "Fotografía_obra.jpg", 1.1, mime="image/jpeg"),
        ),
    )
    work_b = WorkRecord(
        id="DEMO_WORK_B", name="EJEMPLO_002_Rehabilitación_Caminos",
        pdfs=(
            sample("DB1", "CONTRATO.pdf", 14.3),
            sample("DB2", "PUC.pdf", 0.95),
            sample("DB3", "DICTAMEN_AD.pdf", 0.42),
            sample("DB4", "OTRO_DOCUMENTO.pdf", 1.4),
        ),
    )
    work_c = WorkRecord(
        id="DEMO_WORK_C", name="EJEMPLO_003_Construcción_Andador",
        pdfs=(
            sample("DC1", "CONTRATO.pdf", 2.10),
            sample("DC2", "PUC.pdf", 0.86),
            sample("DC3", "DICTAMEN_AD.pdf", 0.35),
            sample("DC4", "NOTIFICACION_AD.pdf", 0.31),
        ),
        other_files=(sample("DC5", "CATALOGO.xlsx", 0.23, mime=XLSX_MIME),),
    )
    inventory = DriveInventory(
        root_id="DEMO_ROOT", root_name="Expedientes demostrativos (ficticios)",
        works=(work_a, work_b, work_c), synced_at="",
    )
    # Espejo mínimo de las celdas que el lector de estados consulta.
    registered: list[dict[str, str]] = []
    extracted: list[dict[str, str]] = []
    processed = {"DA1", "DA2", "DA6", "DC1", "DC2", "DC3", "DC4", "DC5"}
    for work in inventory.works:
        for d in (*work.pdfs, *work.other_files):
            if d.mime_type not in (PDF_MIME, XLSX_MIME):
                continue
            result_id = "SAMPLE_" + d.id if d.id in processed else ""
            registered.append({
                "documento_id": d.id, "obra_id": work.id, "nombre_archivo": d.name,
                "activo": "SI", "md5_checksum": d.md5_checksum,
                "tipo_documental": code_from_filename(d.name, d.mime_type) or "",
                "estado_procesamiento": "Analizado" if result_id else "Pendiente",
                "resultado_id": result_id,
            })
            if result_id:
                extracted.append({
                    "cache_key": result_id, "documento_id": d.id,
                    "obra_id": work.id, "estado": "COMPLETADO",
                    "resultado_json": '{"ejemplo":"No es una extracción real"}',
                    "actualizado_utc": "2026-11-07T13:14:00+00:00",
                    "version_esquema": {
                        "CONTRATO": "contrato-v2", "PUC": "puc-v1",
                        "DICTAMEN_AD": "dictamen-ad-v1",
                        "NOTIFICACION_AD": "notificacion-ad-v1",
                        "ORDEN_AD": "orden-ad-v1", "CATALOGO": "catalogo-xlsx-v1",
                    }.get(code_from_filename(d.name, d.mime_type), ""),
                })
    tables = {"Documentos": registered, "Extracciones": extracted, "DatosContrato": []}
    return inventory, tables, file_states(inventory, tables)
