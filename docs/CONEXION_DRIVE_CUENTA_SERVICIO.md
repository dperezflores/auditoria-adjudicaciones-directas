# Conexión central de Google Drive — cuenta de servicio (Fase 1)

**Estado:** módulo Python preparado, pendiente de permisos y secretos privados.
La app ya usa `st.login()` para verificar quién accede. La cuenta de servicio
es **otra identidad**, empleada solo por el servidor para leer la carpeta piloto.

## 1. Crear la identidad

En el proyecto de Google Cloud `auditoria-ad-piloto`, abre:
https://console.cloud.google.com/iam-admin/serviceaccounts?project=auditoria-ad-piloto

Pulsa **Crear cuenta de servicio** y define:
- Nombre: `AuditorIA - lector Drive piloto`
- ID: `auditoria-drive-reader` (si está disponible)
- Descripción: `Lectura de carpetas y archivos autorizados del piloto AuditorIA`

Pulsa **Crear y continuar**, omite los roles generales de IAM del proyecto,
pasa las asignaciones opcionales y termina con **Listo**.
El resultado es un correo similar a
`auditoria-drive-reader@auditoria-ad-piloto.iam.gserviceaccount.com`.
No otorga por sí mismo permisos para ver una carpeta de Google Drive.
No es necesario generar claves en este primer paso.

Documentación: https://docs.cloud.google.com/iam/docs/service-accounts-create

## 2. Compartir solo la carpeta piloto (paso posterior)

En Google Drive, comparte como **Lector** exclusivamente la carpeta
`AUDITORIA_AD_PILOTO` con el correo EXACTO de la cuenta de servicio.
No compartas toda tu unidad personal, ni documentos reales, ni la carpeta
`Datos_AuditorIA_PILOTO` en esta etapa.

La cuenta verá solo los archivos compartidos, independientemente de los
permisos de IAM del proyecto de Google Cloud.

## 3. Clave privada y Streamlit Secrets (paso posterior)

En la ficha de la cuenta de servicio abre **Claves > Agregar clave >
Crear nueva clave > JSON**. Descarga el archivo a un lugar privado y no lo
subas ni compartas. Las políticas de organización podrían bloquear claves
descargables; en ese caso se evaluará otra forma de acceso, sin desactivar
controles de seguridad.

En los secretos privados de Streamlit, preservando las secciones `[auth]`
y `[access]` que ya funcionan, añade:

```toml
[drive]
root_folder_id = "ID_DE_LA_CARPETA_PILOTO"

[gcp_service_account]
type = "service_account"
project_id = "auditoria-ad-piloto"
private_key_id = "VALOR_DEL_JSON_PRIVADO"
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "CORREO_REAL_DE_CUENTA_DE_SERVICIO"
client_id = "VALOR_DEL_JSON"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "URL_DEL_JSON"
universe_domain = "googleapis.com"
```

Copia los valores **directamente del JSON generado**. Los textos de arriba son
marcadores ilustrativos y no secretos utilizables. En TOML los `\n` deben
interpretarse como saltos de línea en `private_key` (comillas normales, no simples).
Nunca pegues el JSON completo en un mensaje de ChatGPT.

## 4. Qué hace el módulo

- `services/drive_service.py`: consulta el nombre de la carpeta principal,
  lista TODAS sus subcarpetas (obras), luego lista sus PDF, con paginación.
- Guarda solo el inventario en memoria de la sesión de Streamlit. No descarga
  PDFs ni ejecuta Gemini.
- Muestra IDs estables de Google Drive, fecha de modificación y checksum MD5,
  cuando Google lo proporciona.
- `ui/drive_explorer.py`: añade una pestaña «Google Drive (piloto)»
  que solo consulta expedientes si el inicio de sesión está aprobado y
  los secretos de servicio están completos.

## 5. Limitaciones y seguridad

- Esta versión **NO** almacena el inventario en Google Sheets: el seguimiento
  persistente y la detección histórica de eliminaciones/modificaciones se
  desarrollarán después. Si actualizas, consulta de nuevo el estado actual.
- La lectura central no implica que todos los usuarios de Google Drive estén
  autorizados: el acceso a AuditorIA está controlado mediante `[access]`.
- No se ha configurado la conexión real todavía. Evita subir expedientes
  sujetos a fiscalización hasta contar con autorización institucional y
  seguridad validada.
- La cuenta de servicio no necesita rol `Owner`, `Editor` o `Viewer`
  sobre el proyecto en IAM para leer una carpeta explícitamente compartida.
- El permiso del API en el código es de **solo lectura**:
  `https://www.googleapis.com/auth/drive.readonly`.
