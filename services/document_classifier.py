"""Codificación documental por nombre de archivo, sin verificar su contenido.

La política aprobada de AuditorIA exige nombres canónicos por expediente.
NO se lee el PDF/Excel para asignar un tipo ni se invoca Gemini.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath

PDF_MIME = "application/pdf"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

DOCUMENT_CODES = (
    "CONTRATO",
    "PUC",
    "CATALOGO",
    "DICTAMEN_AD",
    "NOTIFICACION_AD",
    "ORDEN_AD",
)
PDF_CODES = tuple(code for code in DOCUMENT_CODES if code != "CATALOGO")

# Los códigos están vinculados a la extensión real y al tipo MIME de Drive.
# Se ignoran únicamente diferencias de mayúsculas/minúsculas en el nombre.
FILENAME_CODES: dict[tuple[str, str], str] = {
    **{(f"{code}.PDF", PDF_MIME): code for code in PDF_CODES},
    ("CATALOGO.XLSX", XLSX_MIME): "CATALOGO",
}


@dataclass(frozen=True)
class Classification:
    code: str | None
    status: str
    detail: str
    confirmed: bool = False

    @property
    def label(self) -> str:
        return self.code or "POR_IDENTIFICAR"


def code_from_filename(name: str, mime_type: str) -> str | None:
    """Resolver el tipo EXCLUSIVAMENTE por nombre y MIME, sin leer el archivo.

    Ejemplo: 'PUC.pdf' -> 'PUC'. 'DICTAMEN TECNICO.pdf' -> None:
    es diferente de un DICTAMEN_AD, así que debe renombrarse correctamente.
    """
    basename = PurePath(name).name.strip().upper()
    return FILENAME_CODES.get((basename, mime_type))


def guess_from_name(name: str, mime_type: str) -> Classification:
    """Compatibilidad con la UI original, ahora con asignación automática.

    El campo 'confirmed' aquí significa *aceptado según nombre*, NO
    validado por contenido. Nunca debe presentarse como cotejo técnico.
    """
    code = code_from_filename(name, mime_type)
    if code:
        return Classification(
            code, "Asignado por nombre",
            "Código asignado por convención de nombre y formato; "
            "el contenido no fue verificado.",
            True,
        )
    return Classification(
        None, "Sin código",
        "El archivo no tiene un nombre estándar reconocido. "
        "Renómbralo usando uno de los seis códigos establecidos.",
        False,
    )
