"""Lectura exclusivamente de metadatos de carpetas y PDF en Google Drive.

La cuenta de servicio únicamente necesita acceso de LECTOR a la carpeta piloto.
Este módulo NO descarga PDF, NO usa Gemini y NO escribe en Drive.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from datetime import datetime, timezone
import re
from typing import Any, Mapping

FOLDER_MIME = "application/vnd.google-apps.folder"
PDF_MIME = "application/pdf"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
_ID = re.compile(r"^[A-Za-z0-9_-]{10,}$")
_FILE_FIELDS = "nextPageToken,files(id,name,mimeType,modifiedTime,md5Checksum,size,webViewLink,trashed)"


class DriveConfigurationError(Exception):
    """Faltan secretos o parámetros de Drive."""


class DriveConnectionError(Exception):
    """Google Drive no respondió correctamente."""


@dataclass(frozen=True)
class DocumentRecord:
    id: str
    name: str
    modified_time: str = ""
    md5_checksum: str = ""
    size_bytes: int = 0
    url: str = ""
    parent_id: str = ""
    relative_path: str = ""
    mime_type: str = PDF_MIME


@dataclass(frozen=True)
class WorkRecord:
    id: str
    name: str
    pdfs: tuple[DocumentRecord, ...] = field(default_factory=tuple)
    url: str = ""
    other_files: tuple[DocumentRecord, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DriveInventory:
    root_id: str
    root_name: str
    works: tuple[WorkRecord, ...]
    synced_at: str

    @property
    def pdf_total(self) -> int:
        return sum(len(work.pdfs) for work in self.works)


def validate_id(value: str) -> str:
    """Un ID validado se puede incluir con seguridad en un query de Drive."""
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise DriveConfigurationError("ID de carpeta Google Drive inválido.")
    return value


def is_configured(settings: Mapping[str, Any]) -> bool:
    """Las credenciales deben venir solamente de secretos privados."""
    try:
        drive = settings.get("drive", {})
        service = settings.get("gcp_service_account", {})
        return bool(drive.get("root_folder_id") and service.get("client_email")
                    and service.get("private_key") and service.get("token_uri"))
    except (AttributeError, TypeError):
        return False


def create_drive_client(service_account_data: Mapping[str, Any]) -> Any:
    """Construye el cliente con permisos de lectura de Drive, no de escritura."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    info = dict(service_account_data)
    credentials = service_account.Credentials.from_service_account_info(
        info, scopes=[DRIVE_SCOPE]
    )
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def _list_children(service: Any, parent_id: str) -> list[dict[str, Any]]:
    parent_id = validate_id(parent_id)
    files: list[dict[str, Any]] = []
    page_token: str | None = None

    for _ in range(1000):
        args = {
            "q": f"'{parent_id}' in parents and trashed = false",
            "fields": _FILE_FIELDS,
            "pageSize": 1000,
            "supportsAllDrives": True,
            "includeItemsFromAllDrives": True,
        }
        if page_token:
            args["pageToken"] = page_token
        response = service.files().list(**args).execute()
        files.extend(f for f in response.get("files", []) if not f.get("trashed"))
        page_token = response.get("nextPageToken")
        if not page_token:
            return files
    raise DriveConnectionError("Se excedió el límite de páginas al explorar Drive.")


def scan_drive(service: Any, root_folder_id: str) -> DriveInventory:
    """Una obra equivale a cada subcarpeta directa del directorio raíz."""
    root_folder_id = validate_id(root_folder_id)
    root = service.files().get(
        fileId=root_folder_id,
        fields="id,name,mimeType,trashed",
        supportsAllDrives=True,
    ).execute()
    if root.get("trashed") or root.get("mimeType") != FOLDER_MIME:
        raise DriveConnectionError("La carpeta raíz no existe o no es una carpeta válida.")

    works = []
    for folder in _list_children(service, root_folder_id):
        if folder.get("mimeType") != FOLDER_MIME:
            continue
        pdfs = []
        other_files = []
        # Explorar también subcarpetas de expediente (p. ej. PUC, Contratos,
        # Dictámenes) sin salir del directorio de la obra autorizada.
        pending = [(folder["id"], "", 0)]
        seen_folders: set[str] = set()
        seen_files: set[str] = set()
        while pending:
            parent_id, relative, depth = pending.pop()
            if parent_id in seen_folders:
                continue
            seen_folders.add(parent_id)
            if depth > 6 or len(seen_folders) > 1500:
                raise DriveConnectionError("El expediente excede la profundidad o cantidad permitida.")
            for item in _list_children(service, parent_id):
                if item.get("mimeType") == FOLDER_MIME:
                    pending.append((
                        item["id"],
                        f"{relative}/{item.get('name', 'Subcarpeta')}".lstrip("/"),
                        depth + 1,
                    ))
                    continue
                if item["id"] in seen_files:
                    continue
                seen_files.add(item["id"])
                if len(seen_files) > 3000:
                    raise DriveConnectionError("Hay demasiados archivos en una sola obra.")
                record = DocumentRecord(
                    id=item["id"],
                    name=item.get("name", "Sin nombre"),
                    modified_time=item.get("modifiedTime") or "",
                    md5_checksum=item.get("md5Checksum") or "",
                    size_bytes=int(item.get("size") or 0),
                    url=item.get("webViewLink") or "",
                    parent_id=parent_id,
                    relative_path=relative,
                    mime_type=item.get("mimeType") or "",
                )
                if record.mime_type == PDF_MIME:
                    pdfs.append(record)
                else:
                    other_files.append(record)
        pdfs.sort(key=lambda f: (f.relative_path.casefold(), f.name.casefold(), f.id))
        other_files.sort(key=lambda f: (f.relative_path.casefold(), f.name.casefold(), f.id))
        works.append(WorkRecord(
            id=folder["id"],
            name=folder.get("name") or "Obra sin nombre",
            pdfs=tuple(pdfs),
            url=folder.get("webViewLink") or "",
            other_files=tuple(other_files),
        ))
    works.sort(key=lambda x: (x.name.casefold(), x.id))
    return DriveInventory(
        root_id=root_folder_id,
        root_name=root.get("name") or "Expedientes",
        works=tuple(works),
        synced_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


# Google Gemini admite PDF de hasta 50 MB; usamos MB decimales.
# Mantener este límite en Drive y en la interfaz para evitar llamadas inválidas.
MAX_PDF_BYTES = 50_000_000
# Alias de compatibilidad para consumidores anteriores.
MAX_PILOT_PDF_BYTES = MAX_PDF_BYTES


def check_pdf_size(size_bytes: int) -> None:
    """Validar tamaño antes de descargar o consultar Gemini."""
    if not isinstance(size_bytes, int) or size_bytes <= 0:
        raise DriveConnectionError(
            "Drive no informa un tamaño válido para el PDF. "
            "Actualiza el inventario antes de analizar."
        )
    if size_bytes > MAX_PDF_BYTES:
        raise DriveConnectionError(
            f"El PDF mide {size_bytes / 1_000_000:.2f} MB y supera el límite "
            "admitido de 50 MB. Reduce o divide el documento antes de analizarlo."
        )





def download_verified_pdf(
    service: Any, doc: DocumentRecord, expected_folder_id: str
) -> bytes:
    """Lee un PDF todavía presente en el expediente autorizado.

    Verifica pertenencia a la carpeta, tipo, tamaño y contenido MD5 antes de
    enviar datos a una API externa. No modifica Drive.
    """
    expected_folder_id = validate_id(expected_folder_id)
    validate_id(doc.id)
    metadata = service.files().get(
        fileId=doc.id,
        fields="id,name,mimeType,size,md5Checksum,parents,trashed",
        supportsAllDrives=True,
    ).execute()
    parent_id = validate_id(doc.parent_id or expected_folder_id)
    if (
        metadata.get("trashed")
        or metadata.get("mimeType") != PDF_MIME
        or parent_id not in metadata.get("parents", [])
    ):
        raise DriveConnectionError("El PDF ya no pertenece a la carpeta seleccionada.")
    if parent_id != expected_folder_id:
        # Verificar la cadena de padres en Drive EN EL MOMENTO DE LEER,
        # no solo confiar en una ruta obtenida del inventario antiguo.
        current = parent_id
        for _ in range(7):
            ancestor = service.files().get(
                fileId=current, fields="id,mimeType,parents,trashed",
                supportsAllDrives=True,
            ).execute()
            if ancestor.get("trashed") or ancestor.get("mimeType") != FOLDER_MIME:
                raise DriveConnectionError("La subcarpeta ya no es válida.")
            ancestors = ancestor.get("parents") or []
            if expected_folder_id in ancestors:
                break
            if not ancestors:
                raise DriveConnectionError("El PDF no pertenece a la obra autorizada.")
            current = validate_id(ancestors[0])
        else:
            raise DriveConnectionError("No se pudo verificar la ruta de la subcarpeta.")
    size = int(metadata.get("size") or 0)
    check_pdf_size(size)
    if metadata.get("md5Checksum") != doc.md5_checksum:
        raise DriveConnectionError("El PDF cambió desde la última consulta. Actualiza Drive.")
    result = service.files().get_media(fileId=doc.id).execute()
    if not isinstance(result, bytes) or not result.startswith(b"%PDF-"):
        raise DriveConnectionError("No se recibió un PDF válido.")
    check_pdf_size(len(result))
    if len(result) != size:
        raise DriveConnectionError("El tamaño del PDF cambió; actualiza Drive.")
    digest = hashlib.md5(result).hexdigest()  # Solo verificación de integridad con Drive.
    if digest != metadata.get("md5Checksum"):
        raise DriveConnectionError("El PDF fue modificado durante la descarga.")
    return result


MAX_XLSX_BYTES = 15_000_000


def download_verified_xlsx(
    service: Any, doc: DocumentRecord, expected_folder_id: str
) -> bytes:
    """Descarga Excel real con comprobación de pertenencia, MIME y MD5.

    Se ejecuta únicamente cuando el usuario solicita verificar el tipo;
    no utiliza IA ni permisos de escritura en Drive.
    """
    expected_folder_id = validate_id(expected_folder_id)
    validate_id(doc.id)
    if doc.mime_type != XLSX_MIME:
        raise DriveConnectionError("El documento seleccionado no es un XLSX.")
    metadata = service.files().get(
        fileId=doc.id,
        fields="id,name,mimeType,size,md5Checksum,parents,trashed",
        supportsAllDrives=True,
    ).execute()
    parent_id = validate_id(doc.parent_id or expected_folder_id)
    if (
        metadata.get("trashed")
        or metadata.get("mimeType") != XLSX_MIME
        or parent_id not in metadata.get("parents", [])
    ):
        raise DriveConnectionError("El Excel ya no pertenece a la carpeta seleccionada.")
    if parent_id != expected_folder_id:
        current = parent_id
        for _ in range(7):
            ancestor = service.files().get(
                fileId=current, fields="id,mimeType,parents,trashed",
                supportsAllDrives=True,
            ).execute()
            if ancestor.get("trashed") or ancestor.get("mimeType") != FOLDER_MIME:
                raise DriveConnectionError("La subcarpeta del Excel ya no es válida.")
            ancestors = ancestor.get("parents") or []
            if expected_folder_id in ancestors:
                break
            if not ancestors:
                raise DriveConnectionError("El Excel no pertenece a la obra autorizada.")
            current = validate_id(ancestors[0])
        else:
            raise DriveConnectionError("No se verificó la ruta de la subcarpeta.")
    size = int(metadata.get("size") or 0)
    if size <= 0 or size > MAX_XLSX_BYTES:
        raise DriveConnectionError("El Excel no tiene un tamaño admisible (máximo 15 MB).")
    if not doc.md5_checksum or doc.md5_checksum != metadata.get("md5Checksum"):
        raise DriveConnectionError("El Excel cambió desde la última consulta a Drive.")
    raw = service.files().get_media(fileId=doc.id).execute()
    if (
        not isinstance(raw, bytes) or not raw.startswith(b"PK")
        or len(raw) != size or hashlib.md5(raw).hexdigest() != doc.md5_checksum
    ):
        raise DriveConnectionError("El Excel no coincide con los metadatos verificados.")
    return raw
