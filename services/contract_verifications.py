"""Revisiones manuales de contratos, persistencia append-only y auditabilidad.

Solo anota verificaciones en una pestaña ADICIONAL. No modifica
Extracciones, DatosContratoV2, documentos Drive ni el prompt de Gemini.
El cerrojo de escritura del mismo proceso se gestiona en la interfaz.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from typing import Any, Mapping
from uuid import uuid4

from services.contract_portfolio import read_contract_portfolio, ContractPortfolio
from services.contract_normalization import (
    EDITABLE_FIELDS, EXTRA_FIELDS, IVA_VALUES, REGIMES, CATEGORIES,
    normalize_advance,
)
from services.contract_display import short_date, normalize_award_method, normalize_contract_type
from services.contract_portfolio import parse_amount


SHEET = "VerificacionesContrato"
HEADERS = (
    "revision_id", "obra_id", "documento_id", "cache_key",
    "revision_utc", "auditor", "estado_revision", "campos_json", "observaciones",
)
MAX_NOTE = 1800
MAX_CELL = 5000


class VerificationError(ValueError):
    pass


def _titles(client: Any, spreadsheet_id: str) -> set[str]:
    response = client.spreadsheets().get(
        spreadsheetId=spreadsheet_id,fields="sheets.properties.title",
    ).execute()
    return {
        x.get("properties",{}).get("title","")
        for x in (response.get("sheets") or [])
    }


def read_verifications(client: Any, spreadsheet_id: str) -> dict[str,dict]:
    """Devuelve la última verificación de cada versión de extracción."""
    if SHEET not in _titles(client,spreadsheet_id):
        return {}
    res=client.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,range=f"'{SHEET}'!A1:I",
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    rows=res.get("values") or []
    if not rows or tuple(str(x) for x in rows[0]) != HEADERS:
        raise VerificationError("Encabezados inválidos en VerificacionesContrato.")
    result={}
    for line in rows[1:]:
        if not any(line):
            continue
        padded=[str(x) if x is not None else "" for x in line[:len(HEADERS)]]
        padded+=[""]*(len(HEADERS)-len(padded))
        entry=dict(zip(HEADERS,padded))
        if not (
            entry["revision_id"] and entry["documento_id"]
            and entry["obra_id"] and entry["cache_key"]
        ):
            raise VerificationError("Existe una verificación sin identidad válida.")
        try:
            fields=json.loads(entry["campos_json"])
        except (TypeError,ValueError) as exc:
            raise VerificationError("Una verificación tiene JSON ilegible.") from exc
        if not isinstance(fields,dict):
            raise VerificationError("El contenido de revisión no es un objeto.")
        entry["campos"]=fields
        result[entry["cache_key"]]=entry
    return result


def with_verifications(
    portfolio: ContractPortfolio, verifications: Mapping[str,Mapping],
) -> ContractPortfolio:
    """No heredar correcciones al nuevo PDF / nueva extracción: clave exacta."""
    return replace(
        portfolio,
        records=tuple(
            replace(record,verification=(
                dict(verifications[record.cache_key])
                if record.cache_key in verifications
                and verifications[record.cache_key].get("obra_id")==record.obra_id
                and verifications[record.cache_key].get("documento_id")==record.documento_id
                else None
            )) for record in portfolio.records
        ),
    )


def read_verified_portfolio(client: Any,spreadsheet_id: str) -> ContractPortfolio:
    return with_verifications(
        read_contract_portfolio(client,spreadsheet_id),
        read_verifications(client,spreadsheet_id),
    )


def _validate_fields(changes: Mapping[str,str]) -> dict[str,str]:
    if not isinstance(changes,Mapping):
        raise VerificationError("Los campos manuales deben ser un objeto.")
    if set(changes) - (set(EDITABLE_FIELDS)|set(EXTRA_FIELDS)):
        raise VerificationError("Se recibió una columna manual no permitida.")
    clean={}
    for k, v in changes.items():
        if not isinstance(v,str) or not v.strip():
            continue
        val=v.strip()
        if len(val)>700:
            raise VerificationError(f"Campo demasiado largo: {k}.")
        if k=="anticipo":
            adv=normalize_advance(val)
            if adv.percent=="—" or adv.percent!=val:
                raise VerificationError("El anticipo manual debe ser un porcentaje como 30% o 0%.")
        if k=="monto_contrato" and (
            parse_amount(val) is None or
            any(t in val.casefold() for t in ("usd","eur","€"))
        ):
            raise VerificationError("El monto manual debe expresarse en pesos y ser inequívoco.")
        if k=="iva" and val not in IVA_VALUES:
            raise VerificationError("IVA manual no reconocido.")
        if k=="regimen" and val not in REGIMES:
            raise VerificationError("Régimen manual no reconocido.")
        if k=="ejercicio" and (not val.isdigit() or int(val) not in range(2021,2027)):
            raise VerificationError("Ejercicio fuera del histórico 2021–2026.")
        if k=="tipo_contrato" and val not in CATEGORIES[k]:
            raise VerificationError("Tipo de contrato no reconocido.")
        if k=="modalidad_adjudicacion" and val not in CATEGORIES[k]:
            raise VerificationError("Modalidad de adjudicación no reconocida.")
        if k.startswith("fecha_") and (
            not bool(__import__("re").fullmatch(r"\d{2}/\d{2}/\d{4}",val))
            or short_date(val)!=val
        ):
            raise VerificationError("Las fechas manuales se expresan como DD/MM/AAAA válidas.")
        clean[k]=val
    return clean


def save_verification(
    client: Any, spreadsheet_id: str, *,
    obra_id: str, documento_id: str, cache_key: str,
    auditor: str, estado: str, campos: Mapping[str,str], observaciones: str,
) -> str:
    """Escritura voluntaria; el llamador mantiene get_writer_lock()."""
    if estado not in ("Confirmado","Pendiente"):
        raise VerificationError("Estado de verificación desconocido.")
    auditor=str(auditor or "").strip()
    if not auditor or len(auditor)>250:
        raise VerificationError("No se identificó al auditor que confirma.")
    if not observaciones.strip() or len(observaciones)>MAX_NOTE:
        raise VerificationError(
            "La verificación requiere una observación breve con su sustento."
        )
    values=_validate_fields(campos)
    if not values and estado!="Confirmado":
        raise VerificationError("Indica al menos un dato confirmado o corregido.")
    # Releer la versión vigente para evitar sobrescribir revisiones obsoletas.
    portfolio=read_contract_portfolio(client,spreadsheet_id)
    matches=[
        x for x in portfolio.records if x.obra_id==obra_id
        and x.documento_id==documento_id and x.cache_key==cache_key
    ]
    if len(matches)!=1:
        raise VerificationError(
            "La versión del contrato cambió. Actualiza el listado antes de guardar."
        )
    titles=_titles(client,spreadsheet_id)
    if SHEET not in titles:
        client.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests":[{"addSheet":{"properties":{"title":SHEET}}}]},
        ).execute()
        client.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,range=f"'{SHEET}'!A1:I1",
            valueInputOption="RAW",body={"values":[list(HEADERS)]},
        ).execute()
    else:
        read_verifications(client,spreadsheet_id)  # Validar encabezado existente.
    revision_id=uuid4().hex
    row=[
        revision_id,obra_id,documento_id,cache_key,
        datetime.now(timezone.utc).isoformat(timespec="seconds"),auditor,
        estado,json.dumps(values,ensure_ascii=False,separators=(",",":")),
        observaciones.strip(),
    ]
    if len(row[7])>MAX_CELL:
        raise VerificationError("Se excedió el límite de datos de revisión.")
    result=client.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,range=f"'{SHEET}'!A:I",
        valueInputOption="RAW",insertDataOption="INSERT_ROWS",
        body={"values":[row]},
    ).execute()
    if int((result.get("updates") or {}).get("updatedRows",0))!=1:
        raise VerificationError(
            "Google Sheets no confirmó la revisión. Comprueba el historial antes de repetir."
        )
    return revision_id
