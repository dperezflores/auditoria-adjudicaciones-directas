"""Comparador de límites 2021–2026, XLSX de Recursos (lectura solamente)."""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
import hashlib
import re
import unicodedata
from typing import Any

from openpyxl import load_workbook
from services.contract_display import short_date, normalize_award_method
from services.contract_portfolio import parse_amount
from services.amount_iva import identify_contract_amount_iva
from services.drive_service import _list_children, validate_id, FOLDER_MIME, XLSX_MIME

FILENAME = "ADJUDICACION_LIM_2021_2026.xlsx"
# Alcance temporal del piloto: todas las obras evaluadas son del Municipio de León.
# No inferir municipio del objeto contractual, ni permitir seleccionar otro.
PILOT_MUNICIPALITY = "León"
YEARS = range(2021, 2027)
CENT = Decimal("0.01")
MUNICIPAL_FIELDS = ("Año", "Municipio", "Municipio_normalizado", "Grupo",
    "Clave_Año_Municipio", "AD_max_sin_IVA", "LS_min_sin_IVA",
    "LS_max_sin_IVA", "LP_min_sin_IVA", "Decreto", "Referencia_poblacion", "Fuente_URL")
ESTATAL_FIELDS = ("Año", "AD mín. sin IVA", "AD máx. sin IVA",
    "LS desde sin IVA", "LS máx. sin IVA", "LP desde sin IVA",
    "Decreto", "Artículo", "Fuente oficial (URL)")
METHODS = ("ADJUDICACIÓN DIRECTA", "LICITACIÓN SIMPLIFICADA", "LICITACIÓN PÚBLICA")

class LimitsError(ValueError):
    pass

@dataclass(frozen=True)
class Limit:
    year: int
    regime: str
    municipality: str
    group: str
    ad_min: Decimal
    ad_max: Decimal
    ls_min: Decimal
    ls_max: Decimal
    lp_min: Decimal
    decree: str
    article: str
    population: str
    url: str
    sheet: str
    key: str

@dataclass(frozen=True)
class Catalog:
    municipal: dict[tuple[int, str], Limit]
    estatal: dict[int, Limit]
    file_id: str = ""
    md5: str = ""

@dataclass(frozen=True)
class Result:
    state: str
    message: str
    row: Limit | None
    year: int | None
    regime: str
    municipality: str
    method: str
    gross: Decimal | None
    net: Decimal | None
    iva: str
    law: str
    funding: str
    warnings: tuple[str, ...]
    margin: Decimal | None = None

def fold(s: str) -> str:
    a = unicodedata.normalize("NFKD", str(s or "").casefold())
    a = "".join(x for x in a if not unicodedata.combining(x))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", a).split())

def money(v: Decimal | None) -> str:
    return ("$" + f"{v:,.2f}") if v is not None else "—"

def dec(v: Any) -> Decimal:
    try:
        r = Decimal(str(v)).quantize(CENT)
        if not r.is_finite() or r < 0:
            raise ValueError()
        return r
    except Exception as exc:
        raise LimitsError("Monto inválido en la tabla de límites.") from exc

def _rows(book: Any, tab: str, required: tuple[str, ...]) -> list[dict]:
    if tab not in book.sheetnames:
        raise LimitsError("Falta la hoja " + tab)
    rows = book[tab].iter_rows(values_only=True)
    head = next(rows, None)
    if not head:
        raise LimitsError("Hoja sin encabezados: " + tab)
    h = [str(x).strip() if x is not None else "" for x in head]
    nonempty = [col for col in h if col]
    if len(set(nonempty)) != len(nonempty) or not set(required).issubset(h):
        raise LimitsError("Encabezados incompatibles en " + tab)
    index = {k: h.index(k) for k in required}
    return [{k: r[i] if i < len(r) else None for k,i in index.items()}
            for r in rows if len(r) and r[0] is not None]

def _year(v: Any) -> int:
    try:
        year = int(v)
    except (ValueError, TypeError) as exc:
        raise LimitsError("Año inválido") from exc
    if year not in YEARS:
        raise LimitsError("Año fuera de 2021–2026")
    return year

def _check(r: Limit) -> None:
    if not (r.ad_min <= r.ad_max and r.ad_max + CENT == r.ls_min
            and r.ls_min <= r.ls_max and r.ls_max + CENT == r.lp_min):
        raise LimitsError("Rangos discontinuos: " + r.key)

def parse_catalog(binary: bytes, file_id: str = "", md5: str = "") -> Catalog:
    if not binary or len(binary) > 2_000_000:
        raise LimitsError("El XLSX está vacío o supera 2 MB.")
    try:
        book = load_workbook(BytesIO(binary), read_only=True, data_only=True)
    except Exception as exc:
        raise LimitsError("No se pudo abrir el XLSX.") from exc
    try:
        municipal: dict[tuple[int,str],Limit] = {}
        estatal: dict[int,Limit] = {}
        for d in _rows(book, "Base municipal", MUNICIPAL_FIELDS):
            y = _year(d["Año"])
            muni = str(d["Municipio"] or "").strip()
            key = str(d["Clave_Año_Municipio"] or "")
            norm = fold(muni).upper()
            if (not muni or fold(d["Municipio_normalizado"]).upper() != norm
                    or key != f"{y}|{norm}" or d["Grupo"] not in ("A","B","C")):
                raise LimitsError("Identidad municipio/año/grupo inválida: " + key)
            r = Limit(y,"Municipal",muni,d["Grupo"],Decimal("0"),
                dec(d["AD_max_sin_IVA"]),dec(d["LS_min_sin_IVA"]),
                dec(d["LS_max_sin_IVA"]),dec(d["LP_min_sin_IVA"]),
                str(d["Decreto"]), "", str(d["Referencia_poblacion"] or ""),
                str(d["Fuente_URL"] or ""), "Base municipal", key)
            _check(r)
            if (y,norm) in municipal:
                raise LimitsError("Clave duplicada: " + key)
            municipal[y,norm] = r
        for d in _rows(book, "Base estatal", ESTATAL_FIELDS):
            y = _year(d["Año"])
            r = Limit(y,"Estatal","","",dec(d["AD mín. sin IVA"]),
                dec(d["AD máx. sin IVA"]),dec(d["LS desde sin IVA"]),
                dec(d["LS máx. sin IVA"]),dec(d["LP desde sin IVA"]),
                str(d["Decreto"]),str(d["Artículo"]), "",
                str(d["Fuente oficial (URL)"] or ""),"Base estatal",str(y))
            _check(r)
            if y in estatal:
                raise LimitsError("Año estatal duplicado")
            estatal[y] = r
        if len(municipal) != 276 or len(estatal) != 6:
            raise LimitsError("Histórico incompleto: esperado 276 filas municipales y 6 estatales.")
        if any(sum(k[0] == y for k in municipal) != 46 for y in YEARS):
            raise LimitsError("Faltan municipios en algún ejercicio.")
        return Catalog(municipal,estatal,file_id,md5)
    finally:
        book.close()

def read_drive_catalog(service: Any, root_id: str) -> Catalog:
    root = validate_id(root_id)
    folders = [x for x in _list_children(service, root)
               if x.get("name") == "Recursos" and x.get("mimeType") == FOLDER_MIME]
    if len(folders) != 1:
        raise LimitsError("No se encontró una única subcarpeta Recursos en la raíz.")
    folder = validate_id(folders[0]["id"])
    files = [x for x in _list_children(service, folder)
             if x.get("name") == FILENAME and x.get("mimeType") == XLSX_MIME]
    if len(files) != 1:
        raise LimitsError("No se encontró un único " + FILENAME + " en Recursos.")
    id_ = validate_id(files[0]["id"])
    meta = service.files().get(fileId=id_,supportsAllDrives=True,
        fields="id,name,mimeType,parents,size,md5Checksum,trashed").execute()
    if (meta.get("trashed") or folder not in (meta.get("parents") or [])
            or meta.get("mimeType") != XLSX_MIME or meta.get("name") != FILENAME
            or not (0 < int(meta.get("size") or 0) <= 2_000_000)):
        raise LimitsError("Catálogo no válido o movido fuera de Recursos.")
    binary = service.files().get_media(fileId=id_,supportsAllDrives=True).execute()
    checksum = hashlib.md5(binary).hexdigest()
    if len(binary) != int(meta["size"]) or (
        meta.get("md5Checksum") and meta["md5Checksum"].lower() != checksum
    ):
        raise LimitsError("No coincide la huella o el tamaño del catálogo.")
    return parse_catalog(binary, id_, checksum)

def infer_municipality(object_text: str, names: list[str]) -> str:
    s = fold(object_text)
    found = [n for n in names if re.search(
        r"\bmunicipio\s+(?:de\s+)?" + re.escape(fold(n)) + r"\b",s)]
    return found[0] if len(found) == 1 else ""

def infer_regime(law: str, funding: str) -> str:
    l,f = fold(law),fold(funding)
    local = "lopysrm" in l or (
        "ley de obra publica" in l and
        ("guanajuato" in l or "estado y los municipios" in l))
    federal = ("lopsrm" in l or
        "ley de obras publicas y servicios relacionados con las mismas" in l)
    if federal and not local:
        return "Federal (fuera de estas bases)"
    if federal or not local:
        return "Por confirmar"
    m = bool(re.search(r"\bmunicipal(?:es)?\b|\brecursos propios\b",f))
    e = bool(re.search(r"\bestatal(?:es)?\b|\bestado de guanajuato\b",f))
    other = bool(re.search(r"\bfederal(?:es)?\b|\bramo 33\b|\bfaism\b|\bfism\b",f))
    if other or (m and e):
        return "Por confirmar"
    return "Municipal" if m else "Estatal" if e else "Por confirmar"

def infer_iva(raw: str, evidence: str = "") -> str:
    """Reutilizar la evidencia literal ligada al importe para AD-06."""
    return identify_contract_amount_iva(raw, evidence=evidence).basis

def year_from_date(value: str) -> int | None:
    val = short_date(value)
    if re.fullmatch(r"\d{2}/\d{2}/\d{4}",val):
        year = int(val[-4:])
        return year if year in YEARS else None
    return None

def evaluate(record: Any, catalog: Catalog, *, regime: str | None = None,
             iva: str | None = None, year: int | None = None) -> Result:
    fields = record.full_values or {}
    law,funding = fields.get("legislacion_citada",""),fields.get("fuente_financiamiento","")
    original_regime = infer_regime(law,funding)
    regime = regime or original_regime
    # Para este piloto el municipio es un parámetro de alcance institucional,
    # NO un dato que dependa de la calidad de extracción del contrato.
    municipality = PILOT_MUNICIPALITY
    method = normalize_award_method(fields.get("modalidad_adjudicacion",""))
    original_year = year_from_date(fields.get("fecha_firma_contrato",""))
    year = original_year if year is None else year
    raw = fields.get("monto_contrato","")
    gross = parse_amount(raw)
    # Los límites se expresan en pesos mexicanos; divisas expresas distintas
    # no deben compararse contra MXN sin una conversión documental acreditada.
    foreign_currency = bool(re.search(
        r"\b(?:usd|eur|d[oó]lares?|euros?)\b|€", raw, re.IGNORECASE,
    ))
    # La extracción v2 ya conserva página y evidencia de monto_contrato.
    # Un «IVA INCLUIDO» ligado a ese importe permite clasificar incluso si
    # Gemini dejó únicamente la cantidad en monto_contrato.valor.
    amount_evidence = record.evidence.get("monto_contrato", {}) if fields else {}
    quote = (
        str(amount_evidence.get("evidencia") or "")
        if isinstance(amount_evidence, dict) else ""
    )
    iva_detection = identify_contract_amount_iva(raw, evidence=quote)
    inferred_iva = iva_detection.basis
    iva = iva or inferred_iva
    net = None
    if gross is not None and gross > 0 and not foreign_currency:
        if iva == "Sin IVA":
            net = gross.quantize(CENT, rounding=ROUND_HALF_UP)
        elif iva == "Con IVA (16%)":
            net = (gross/Decimal("1.16")).quantize(CENT,rounding=ROUND_HALF_UP)
    warnings = []
    if not fields:
        warnings.append("El contrato no cuenta con extracción especializada de 16 campos.")
    if year is None:
        warnings.append("Fecha de firma ausente, inválida o fuera de 2021–2026.")
    if year is not None and year != original_year:
        warnings.append("El ejercicio fue confirmado manualmente; cotejar fecha del procedimiento.")
    if regime != original_regime:
        warnings.append("Régimen confirmado manualmente: verificar su sustento documental.")
    if regime not in ("Municipal","Estatal"):
        warnings.append("Régimen no determinado por ley citada y recursos.")
    if method not in METHODS:
        warnings.append("Modalidad no reconocida.")
    if foreign_currency:
        warnings.append("El importe cita una divisa distinta de MXN; los límites son en pesos.")
    if net is None:
        warnings.append("Importe comparable sin IVA no determinado.")
    if iva_detection.source == "Indicaciones contradictorias en monto y evidencia":
        warnings.append(
            "El valor del monto y su evidencia contienen indicaciones "
            "contradictorias del IVA; cotejar cláusula original."
        )
    if iva != inferred_iva:
        warnings.append("Tratamiento de IVA confirmado manualmente; verificar el contrato.")
    row = (catalog.municipal.get((year,fold(municipality).upper())) if
           regime == "Municipal" else catalog.estatal.get(year) if
           regime == "Estatal" else None)
    if not row or net is None or method not in METHODS:
        return Result("Requiere revisión",
            "No hay datos suficientes para comparar contra un límite específico.",
            row,year,regime,municipality,method,gross,net,iva,law,funding,tuple(warnings))
    if method == "ADJUDICACIÓN DIRECTA":
        margin = row.ad_max-net
        state = "Dentro del límite" if margin >= 0 else "Excede el límite"
        message = "Comparación con el máximo de adjudicación directa."
    elif method == "LICITACIÓN SIMPLIFICADA":
        margin = row.ls_max-net
        state = ("Excede el límite" if margin < 0 else
                 "Procedimiento más competitivo" if net < row.ls_min else "Dentro del límite")
        message = ("Importe inferior al rango ordinario; no implica irregularidad automática."
                   if net < row.ls_min else "Comparación con el rango de licitación simplificada.")
    else:
        margin = None
        state = "Dentro del rango de LP" if net >= row.lp_min else "Procedimiento más competitivo"
        message = ("La base no establece límite superior para LP; "
                   "usar LP por debajo del umbral no es incumplimiento automático.")
    return Result(state,message,row,year,regime,municipality,method,
                  gross,net,iva,law,funding,tuple(warnings),margin)
