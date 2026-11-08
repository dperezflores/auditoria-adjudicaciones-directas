"""Identificación documental conservadora, sin llamadas a modelos de IA.

El nombre proporciona solo una SUGERENCIA. La confirmación requiere señales
explícitas del contenido del archivo; PDF escaneado sin texto permanece
pendiente hasta que se habilite clasificación visual específica.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath
import re
import unicodedata

PDF_MIME = "application/pdf"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

DOCUMENT_CODES = (
    "CONTRATO", "PUC", "CATALOGO", "DICTAMEN_AD",
    "NOTIFICACION_AD", "ORDEN_AD",
)
PDF_CODES = tuple(code for code in DOCUMENT_CODES if code != "CATALOGO")


@dataclass(frozen=True)
class Classification:
    code: str | None
    status: str
    detail: str
    confirmed: bool = False

    @property
    def label(self) -> str:
        return self.code or "POR_IDENTIFICAR"


def _normal(text: str) -> str:
    raw = unicodedata.normalize("NFKD", text).casefold()
    return " ".join(
        "".join(c if c.isalnum() else " " for c in raw if not unicodedata.combining(c)).split()
    )


def guess_from_name(name: str, mime_type: str) -> Classification:
    """No confundir 'DICTAMEN TÉCNICO' con dictamen de adjudicación."""
    stem = _normal(PurePath(name).stem)
    if mime_type == XLSX_MIME:
        if re.search(r"\b(catalogo|prefiniquito)\b", stem):
            return Classification("CATALOGO", "Sugerido", "Nombre de Excel; falta revisar su estructura.")
        return Classification(None, "No identificado", "Excel sin código documental reconocido.")
    if mime_type != PDF_MIME:
        return Classification(None, "No compatible", "Formato fuera de los seis tipos documentales.")
    if re.search(r"\bnotificacion\b", stem) and (
        "adjudicacion" in stem or re.search(r"\b(ad|directa)\b", stem)
    ):
        return Classification("NOTIFICACION_AD", "Sugerido", "Notificación identificada solo por nombre.")
    if re.search(r"\borden\b", stem) and (
        "adjudicacion" in stem or re.search(r"\b(ad|directa)\b", stem)
    ):
        return Classification("ORDEN_AD", "Sugerido", "Orden identificada solo por nombre.")
    if re.search(r"\bdictamen\b", stem) and (
        "adjudicacion" in stem or re.search(r"\bad\b", stem)
    ):
        return Classification("DICTAMEN_AD", "Sugerido", "Dictamen de adjudicación sugerido por nombre.")
    if re.search(r"\b(puc|padron)\b", stem):
        return Classification("PUC", "Sugerido", "PUC sugerido por nombre.")
    if re.search(r"\bcontrato\b", stem) or re.match(
        r"^(?:cnt|contr) (?:dir|ad|obra|contr|cnt)(?: |$)", stem
    ):
        return Classification("CONTRATO", "Sugerido", "Contrato sugerido por nombre.")
    return Classification(None, "No identificado", "El nombre no basta para identificar el documento.")


# Se buscan títulos/encabezados, no menciones genéricas de antecedentes.
_TITLE_PATTERNS = {
    "NOTIFICACION_AD": (
        r"\bnotificacion de adjudicacion directa\b",
        r"\bnotificacion de asignacion directa\b",
    ),
    "DICTAMEN_AD": (
        r"\bdictamen (?:de )?(?:autorizacion|procedencia) de adjudicacion directa\b",
        r"\bdictamen de adjudicacion directa\b",
    ),
    "ORDEN_AD": (
        r"\borden de adjudicacion directa\b",
        r"\borden de adjudicacion\b",
    ),
    "PUC": (
        r"\binformacion del padron unico de contratistas\b",
        r"\bconstancia de (?:inscripcion|registro) (?:en el )?padron\b",
        r"\bhoja de consulta (?:del )?puc\b",
    ),
    "CONTRATO": (
        r"\bcontrato de obra publica\b",
        r"\bcontrato de obras publicas\b",
        r"\bcontrato de servicios relacionados con (?:la|las) obra",
        r"\bcontrato de obra\b",
        r"\bcontrato a precios unitarios\b",
    ),
}


def _identify_text(text: str) -> str | None:
    normalized = _normal(text)[:4000]
    matches: list[tuple[int, str]] = []
    for code, patterns in _TITLE_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, normalized)
            if match and match.start() < 2600:
                matches.append((match.start(), code))
    if not matches:
        return None
    matches.sort()
    first = matches[0][1]
    # Una referencia legal incidental no debe reemplazar el encabezado.
    # Para textos sin título claro, no escoger entre señales contradictorias
    # que aparecen muy próximas entre sí.
    if any(code != first and pos - matches[0][0] <= 35 for pos, code in matches[1:]):
        return None
    return first


def _reconcile(suggested: Classification, detected: str | None, *, readable: bool) -> Classification:
    if detected is not None and suggested.code is not None and suggested.code != detected:
        return Classification(
            None, "Inconsistente",
            f"Nombre sugiere {suggested.code}, pero el contenido identifica {detected}. "
            "Corregir la codificación antes de analizar.",
        )
    if detected is not None:
        return Classification(
            detected, "Confirmado", "Tipo reconocido por contenido legible; sin Gemini.", True
        )
    if readable:
        return Classification(
            suggested.code, "Por verificar",
            "No se identificó un encabezado inequívoco en el contenido; "
            "la sugerencia de nombre no está confirmada.",
        )
    return Classification(
        suggested.code, "Sin texto legible",
        "No se pudo leer texto suficiente. Puede tratarse de un PDF escaneado; "
        "no se validó el tipo por su contenido.",
    )


def classify_pdf(data: bytes, name: str) -> Classification:
    suggested = guess_from_name(name, PDF_MIME)
    if not data.startswith(b"%PDF-"):
        return Classification(None, "Error de lectura", "El archivo no tiene firma PDF.")
    try:
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(data), strict=False)
        text = " ".join(
            (reader.pages[i].extract_text() or "")[:4500]
            for i in range(min(2, len(reader.pages)))
        )
    except Exception:
        return Classification(
            suggested.code, "Sin texto legible",
            "No se pudo extraer texto localmente del PDF; tipo no confirmado.",
        )
    return _reconcile(suggested, _identify_text(text), readable=bool(text.strip()))


def classify_xlsx(data: bytes, name: str) -> Classification:
    suggested = guess_from_name(name, XLSX_MIME)
    if not data.startswith(b"PK"):
        return Classification(None, "Error de lectura", "El archivo no parece XLSX válido.")
    try:
        from openpyxl import load_workbook
        wb = load_workbook(BytesIO(data), read_only=True, data_only=True)
        try:
            tokens: list[str] = []
            for ws in wb.worksheets[:3]:
                tokens.append(_normal(ws.title))
                for row in ws.iter_rows(
                    min_row=1, max_row=min(ws.max_row, 65),
                    max_col=min(ws.max_column, 24), values_only=True
                ):
                    tokens.extend(_normal(str(v)) for v in row if v is not None)
            vocabulary = set(tokens)
            head = " ".join(tokens[:900])
            column_signals = [
                any(re.search(r"\bclave\b", t) for t in vocabulary),
                any(re.search(r"\bdescripcion\b", t) for t in vocabulary),
                any(re.search(r"\bunidad\b", t) for t in vocabulary),
                any(re.search(r"\b(precio unitario|precio u|p u)\b", t) for t in vocabulary),
            ]
            detected = (
                "CATALOGO" if (
                    "catalogo de conceptos" in head
                    or "prefiniquito" in head
                    or sum(column_signals) >= 3
                ) else None
            )
        finally:
            wb.close()
    except Exception:
        return Classification(
            suggested.code, "Sin estructura legible",
            "No se pudo leer de forma segura la estructura del libro; tipo no confirmado.",
        )
    return _reconcile(suggested, detected, readable=True)
