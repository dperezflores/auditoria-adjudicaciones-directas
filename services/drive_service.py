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


@dataclass(frozen=True)
class WorkRecord:
    id: str
    name: str
    pdfs: tuple[DocumentRecord, ...] = field(default_factory=tuple)
    url: str = ""


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
                if item.get("mimeType") != PDF_MIME or item["id"] in seen_files:
                    continue
                seen_files.add(item["id"])
                if len(seen_files) > 3000:
                    raise DriveConnectionError("Hay demasiados PDF en una sola obra.")
                pdfs.append(DocumentRecord(
                    id=item["id"],
                    name=item.get("name", "Sin nombre"),
                    modified_time=item.get("modifiedTime") or "",
                    md5_checksum=item.get("md5Checksum") or "",
                    size_bytes=int(item.get("size") or 0),
                    url=item.get("webViewLink") or "",
                    parent_id=parent_id,
                    relative_path=relative,
                ))
        pdfs.sort(key=lambda f: (f.relative_path.casefold(), f.name.casefold(), f.id))
        works.append(WorkRecord(
            id=folder["id"],
            name=folder.get("name") or "Obra sin nombre",
            pdfs=tuple(pdfs),
            url=folder.get("webViewLink") or "",
        ))
    works.sort(key=lambda x: (x.name.casefold(), x.id))
    return DriveInventory(
        root_id=root_folder_id,
        root_name=root.get("name") or "Expedientes",
        works=tuple(works),
        synced_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


MAX_PILOT_PDF_BYTES = 20 * 1024 * 1024


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
    if not 0 < size <= MAX_PILOT_PDF_BYTES:
        raise DriveConnectionError("El PDF supera el límite operativo de 20 MB.")
    if metadata.get("md5Checksum") != doc.md5_checksum:
        raise DriveConnectionError("El PDF cambió desde la última consulta. Actualiza Drive.")
    result = service.files().get_media(fileId=doc.id).execute()
    if not isinstance(result, bytes) or not result.startswith(b"%PDF-"):
        raise DriveConnectionError("No se recibió un PDF válido.")
    if len(result) > MAX_PILOT_PDF_BYTES or len(result) != size:
        raise DriveConnectionError("El tamaño del PDF cambió; actualiza Drive.")
    digest = hashlib.md5(result).hexdigest()  # Solo verificación de integridad con Drive.
    if digest != metadata.get("md5Checksum"):
        raise DriveConnectionError("El PDF fue modificado durante la descarga.")
    return result
