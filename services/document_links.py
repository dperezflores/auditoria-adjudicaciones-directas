"""Documentos complementarios y cruces con contratos, SIN invocar IA.

Se enlazan por obra_id del inventario de Google Sheets. La identidad del
contratista se comprueba aparte mediante identificadores y no se presume
por compartir carpeta. La evidencia proviene solo de resultados completos
para la versión actual del PDF; jamás se reconstruye desde resultados
históricos o datos de otras obras.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import re
import unicodedata
from typing import Any, Mapping, Sequence

from services.contract_v2 import CONTRACT_V2_FIELDS, ContractExtractionV2
from services.document_analysis import GeneralAnalysis
from services.puc_schema import PUC_FIELDS, PucExtractionV1
from services.dictamen_schema import DICTAMEN_FIELDS, DictamenAdV1
from services.notificacion_schema import NOTIFICACION_FIELDS, NotificacionAdV1
from services.orden_schema import ORDEN_FIELDS, OrdenAdV1


_SPECIALIZED = {
    "puc-v1": ("PUC", PucExtractionV1, PUC_FIELDS),
    "dictamen-ad-v1": ("DICTAMEN_AD", DictamenAdV1, DICTAMEN_FIELDS),
    "notificacion-ad-v1": ("NOTIFICACION_AD", NotificacionAdV1, NOTIFICACION_FIELDS),
    "orden-ad-v1": ("ORDEN_AD", OrdenAdV1, ORDEN_FIELDS),
}


@dataclass(frozen=True)
class SupportingDocument:
    obra_id: str
    documento_id: str
    nombre: str
    tipo: str
    estado: str
    esquema: str = ""
    resumen: str = ""
    campos: tuple[Mapping[str, Any], ...] = ()
    alertas: tuple[str, ...] = ()
    extraido_utc: str = ""
    is_puc: bool = False

    @property
    def analysed(self) -> bool:
        return self.estado == "Analizado"


@dataclass(frozen=True)
class Comparison:
    dato: str
    contrato: str
    documento: str
    resultado: str
    detalle: str = ""
    pagina: int | None = None


def _normalize(value: str) -> str:
    n = unicodedata.normalize("NFKD", value.casefold())
    return " ".join(
        "".join(ch if ch.isalnum() else " " for ch in n if not unicodedata.combining(ch)).split()
    )


def _field_key(value: str) -> str:
    return _normalize(value).replace(" ", "_")


def _is_puc(name: str, document_type: str) -> bool:
    n = _normalize(name + " " + document_type)
    return (
        bool(re.search(r"\bpuc\b", n))
        or "padron unico de contratistas" in n
        or "constancia de inscripcion en el padron" in n
    )


def build_supporting_documents(
    works: Sequence[Mapping[str, str]],
    documents: Sequence[Mapping[str, str]],
    analyses: Sequence[Mapping[str, str]],
) -> tuple[SupportingDocument, ...]:
    """Leer PDFs de obras activas, con o sin extracción.

    Incluye únicamente la extracción asociada a resultado_id del documento
    activo, evitando resultados caducados y versiones anteriores.
    """
    active_works = {w["obra_id"] for w in works if w["activo"] == "SI"}
    by_key = {r["cache_key"]: r for r in analyses}
    seen: set[str] = set()
    result: list[SupportingDocument] = []
    for doc in documents:
        document_id = doc["documento_id"]
        obra_id = doc["obra_id"]
        if (
            doc["activo"] != "SI" or obra_id not in active_works
            or doc["mime_type"] != "application/pdf"
        ):
            continue
        if document_id in seen:
            raise ValueError("Documento duplicado en el inventario.")
        seen.add(document_id)
        name = doc["nombre_archivo"]
        candidate = by_key.get(doc["resultado_id"])
        state = "Sin análisis"
        kind = "Documento"
        summary = ""
        fields: tuple[Mapping[str, Any], ...] = ()
        notes: tuple[str, ...] = ()
        schema = ""
        updated = ""
        # Nunca emplear un resultado que pertenezca a otra obra, PDF o versión.
        if doc["estado_procesamiento"] == "Modificado desde el último análisis":
            state = "Desactualizado"
        elif candidate and candidate["documento_id"] == document_id and candidate["obra_id"] == obra_id:
            if candidate["estado"] == "COMPLETADO" and candidate["resultado_json"]:
                schema = candidate["version_esquema"]
                updated = candidate["actualizado_utc"]
                try:
                    if schema == "documento-schema-v1":
                        saved = GeneralAnalysis.model_validate_json(candidate["resultado_json"])
                        kind = saved.tipo_documental
                        summary = saved.resumen
                        fields = tuple(f.model_dump(mode="json") for f in saved.campos)
                        notes = tuple(saved.alertas)
                        state = "Analizado"
                    elif schema == "contrato-v2":
                        saved = ContractExtractionV2.model_validate_json(candidate["resultado_json"])
                        kind = "Extracción con plantilla contractual (16 campos)"
                        fields = tuple(
                            {
                                "campo": key,
                                "valor": getattr(saved, key).valor,
                                "pagina": getattr(saved, key).pagina,
                                "evidencia": getattr(saved, key).evidencia,
                            }
                            for key in CONTRACT_V2_FIELDS if getattr(saved, key).valor
                        )
                        notes = tuple(saved.observaciones)
                        state = "Analizado"
                    elif schema in _SPECIALIZED:
                        kind, model, field_names = _SPECIALIZED[schema]
                        saved = model.model_validate_json(candidate["resultado_json"])
                        fields = tuple({
                            "campo": key,
                            "valor": getattr(saved, key).valor,
                            "pagina": getattr(saved, key).pagina,
                            "evidencia": getattr(saved, key).evidencia,
                        } for key in field_names if getattr(saved, key).valor is not None)
                        notes = tuple(saved.observaciones)
                        if schema == "puc-v1" and saved.especialidades:
                            fields += tuple({
                                "campo": "especialidad",
                                "valor": " / ".join(filter(None, [item.categoria, item.actividad, item.tipo_marcado])),
                                "pagina": item.pagina,
                                "evidencia": item.evidencia,
                            } for item in saved.especialidades)
                        state = "Analizado"
                    elif schema == "contrato-v1":
                        kind = "Contrato (esquema anterior)"
                        state = "Analizado"
                except (ValueError, TypeError):
                    state = "Extracción ilegible"
            elif candidate["estado"] in ("EN_PROCESO", "REQUIERE_REVISION"):
                state = "Revisar extracción"
        result.append(SupportingDocument(
            obra_id=obra_id, documento_id=document_id,
            nombre=name, tipo=kind, estado=state, esquema=schema,
            resumen=summary, campos=fields, alertas=notes,
            extraido_utc=updated, is_puc=_is_puc(name, kind),
        ))
    result.sort(key=lambda d: (d.obra_id, not d.analysed, d.nombre.casefold(), d.documento_id))
    return tuple(result)


# Sinónimos específicos que aparecen en el PUC de León.
_PUC_ALIASES = {
    "contratista": ("nombre_contratista", "contratista", "razon_social", "nombre_razon_social"),
    "registro_puc": ("numero_de_registro", "numero_registro_puc", "registro_puc", "numero_de_registro_puc"),
    "rfc": ("rfc", "registro_federal_de_contribuyentes"),
    "representante_legal": ("representante_legal", "representacion_legal"),
    "representante_tecnico": ("representacion_tecnica", "representante_tecnico", "responsable_tecnico"),
    "vigencia_hasta": ("vigencia_hasta", "fecha_de_vencimiento", "vigencia_al", "vigencia"),
    "capital_contable": ("capital_contable",),
    "especialidad": ("especialidad", "especialidades"),
}


def puc_values(puc: SupportingDocument) -> dict[str, Mapping[str, Any]]:
    candidates = {}
    for item in puc.campos:
        key = _field_key(str(item.get("campo") or ""))
        if key and key not in candidates:
            candidates[key] = item
    return {
        key: next(
            (candidates[alias] for alias in aliases
             if alias in candidates and candidates[alias].get("valor")),
            {},
        )
        for key, aliases in _PUC_ALIASES.items()
    }


def _spanish_date(raw: str) -> date | None:
    """Fecha informativa para comparar vencimiento, sin inferir validez legal."""
    if not raw:
        return None
    s = _normalize(raw)
    months = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
        "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
        "septiembre": 9, "setiembre": 9, "octubre": 10,
        "noviembre": 11, "diciembre": 12,
    }
    years = re.findall(r"\b(?:19|20)\d{2}\b", s)
    day = re.search(r"\b([0-3]?\d)\b", s)
    month = next((month for word, month in months.items() if re.search(rf"\b{word}\b", s)), None)
    if not years or not day or month is None or len(set(years)) != 1:
        return None
    try:
        return date(int(years[0]), month, int(day.group(1)))
    except ValueError:
        return None


def compare_puc(contract: Any, document: SupportingDocument) -> tuple[Comparison, ...]:
    """Resultado documental, NO hallazgo normativo ni verificación automática."""
    fields = puc_values(document)
    source = contract.full_values or {}
    contract_values = {
        "contratista": source.get("contratista") or contract.values.get("contratista", ""),
        "registro_puc": source.get("registro_puc", ""),
        "rfc": source.get("rfc", ""),
        "representante_legal": source.get("representante_legal", ""),
        "representante_tecnico": source.get("representante_tecnico", ""),
    }
    labels = {
        "contratista": "Nombre o razón social",
        "registro_puc": "Registro PUC",
        "rfc": "RFC",
        "representante_legal": "Representante legal",
        "representante_tecnico": "Representante técnico",
    }
    comparisons: list[Comparison] = []
    for key, label in labels.items():
        original = str(contract_values.get(key) or "")
        field = fields.get(key) or {}
        other = str(field.get("valor") or "")
        if not original or not other:
            status = "Sin dato para comparar"
            note = "Falta en el contrato o en la extracción del PUC."
        elif _normalize(original) == _normalize(other):
            status = "Coincide"
            note = "Coincidencia textual normalizada; pendiente de cotejo con originales."
        elif key in ("representante_legal", "representante_tecnico") and sorted(_normalize(original).split()) == sorted(_normalize(other).split()):
            status = "Posible correspondencia"
            note = "Los nombres contienen las mismas palabras en distinto orden; revisar identidad."
        else:
            status = "Diferente"
            note = "Los valores extraídos no coinciden; no implica incumplimiento."
        comparisons.append(Comparison(
            dato=label, contrato=original or "—", documento=other or "—",
            resultado=status, detalle=note,
            pagina=field.get("pagina") if isinstance(field.get("pagina"), int) else None,
        ))

    expiry = fields.get("vigencia_hasta") or {}
    expiry_text = str(expiry.get("valor") or "")
    signing = source.get("fecha_firma_contrato") or contract.values.get("fecha_firma", "")
    date_end, date_signed = _spanish_date(expiry_text), _spanish_date(signing)
    if date_end and date_signed:
        status = "Fecha posterior a firma" if date_end >= date_signed else "Vencimiento anterior a firma"
        detail = "Solo compara vencimiento y firma; NO demuestra inicio de vigencia, inscripción válida ni cumplimiento."
    else:
        status = "Sin cotejo de fechas"
        detail = "Fechas ausentes o no interpretables; validar vigencia documental."
    comparisons.append(Comparison(
        dato="Vencimiento PUC vs firma", contrato=signing or "—",
        documento=expiry_text or "—", resultado=status, detalle=detail,
        pagina=expiry.get("pagina") if isinstance(expiry.get("pagina"), int) else None,
    ))
    return tuple(comparisons)


def candidate_puc_documents(contract: Any, documents: Sequence[SupportingDocument]) -> tuple[SupportingDocument, ...]:
    """Evitar cruzar PUC de otra obra; ordenar coincidencias identificativas."""
    candidates = [
        d for d in documents
        if d.obra_id == contract.obra_id and d.documento_id != contract.documento_id
        and d.is_puc and d.analysed
    ]
    values = contract.full_values or {}
    def rank(doc: SupportingDocument) -> tuple[int, str]:
        fields = puc_values(doc)
        reg = str((fields["registro_puc"] or {}).get("valor") or "")
        rfc = str((fields["rfc"] or {}).get("valor") or "")
        matched_reg = bool(reg and values.get("registro_puc") and _normalize(reg) == _normalize(values["registro_puc"]))
        matched_rfc = bool(rfc and values.get("rfc") and _normalize(rfc) == _normalize(values["rfc"]))
        return (-(int(matched_reg) + int(matched_rfc)), doc.nombre.casefold())
    return tuple(sorted(candidates, key=rank))


def identification_note(contract: Any, puc: SupportingDocument) -> str:
    fields = puc_values(puc)
    values = contract.full_values or {}
    comparable = []
    for key in ("rfc", "registro_puc"):
        a = values.get(key) or ""
        b = str((fields[key] or {}).get("valor") or "")
        if a and b:
            comparable.append(_normalize(a) == _normalize(b))
    if comparable and all(comparable):
        return "Misma carpeta de obra; identificadores disponibles coinciden en las extracciones."
    if comparable and not all(comparable):
        return "Misma carpeta de obra, pero al menos un identificador NO coincide. Revisar si el PUC corresponde al contratista."
    return "Misma carpeta de obra, pero no hay identificadores suficientes para confirmar la correspondencia."


def documents_for_contract(contract: Any, documents: Sequence[SupportingDocument]) -> tuple[SupportingDocument, ...]:
    return tuple(
        d for d in documents
        if d.obra_id == contract.obra_id and d.documento_id != contract.documento_id
    )
