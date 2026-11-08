# Configuración de Google Cloud para AuditorIA — piloto

> **Estado:** guía de preparación. No indica que las API, OAuth o Drive estén conectados. Se utilizarán únicamente archivos ficticios y autorizados.

## Proyecto seleccionado

- ID de proyecto: `auditoria-ad-piloto`
- Aplicación pública de demostración: https://auditoria-adjudicaciones-directas.streamlit.app/
- Repositorio: https://github.com/dperezflores/auditoria-adjudicaciones-directas

El **ID de proyecto no es una credencial**. No publiques secretos de OAuth, tokens, claves API, JSON de credenciales, archivos de auditoría, ni los pegues en un chat o incidencia de GitHub.

## Paso siguiente: habilitar API de Drive y Sheets (sin crear credenciales)

1. Accede a [Google Drive API](https://console.cloud.google.com/apis/library/drive.googleapis.com?project=auditoria-ad-piloto) en Google Cloud y confirma que el proyecto seleccionado es `auditoria-ad-piloto`.
2. Si aparece **Habilitar**, púlsalo. Si aparece **Administrar**, normalmente ya está habilitada.
3. Repite en [Google Sheets API](https://console.cloud.google.com/apis/library/sheets.googleapis.com?project=auditoria-ad-piloto).
4. Confirma que ambas figuran habilitadas en **APIs y servicios > APIs y servicios habilitados**.

Google: https://developers.google.com/workspace/drive/api/quickstart/python y https://developers.google.com/workspace/sheets/api/quickstart/python

En este paso **no es necesario configurar facturación, crear claves ni autorizaciones OAuth**. Si alguna pantalla exige vincular un método de pago o una organización, detente y revisamos la configuración antes de aceptar.

## Etapa posterior (NO realizar todavía): OAuth para Streamlit

La cuenta de Google Drive propietaria de la carpeta piloto es personal. Por ello, al configurar Google Auth Platform/Consent, la audiencia deberá ser **Externa** (no "Interna", que corresponde a organizaciones Workspace). Durante las pruebas solo se autorizará al usuario de prueba. El flujo destinado a Streamlit Cloud será de **Aplicación web**, con URI de redirección registrado exactamente como lo exija el código definitivo y HTTPS; no usar el ejemplo de OAuth de escritorio de los tutoriales de línea de comandos.

Permisos a evaluar con mínimos privilegios:
- Drive: lectura de metadatos y, cuando se requiera procesar documentos, lectura de contenido de los archivos autorizados.
- Sheets: edición de la hoja maestra de resultados para el usuario central.

Los permisos se decidirán tras revisar el diseño técnico: existen diferencias entre los permisos `drive.file` y `drive.readonly` cuando se necesitan listar y descargar archivos existentes de carpetas no creadas por la app. Ciertos permisos pueden requerir requisitos adicionales de verificación, especialmente antes de uso público.

**Importante:** el conector de Google Drive conectado a ChatGPT no autoriza automáticamente a una aplicación Streamlit independiente. Las credenciales de la aplicación se configurarán más adelante en Streamlit Secrets, nunca en GitHub.

## IDs y secretos

- `GOOGLE_CLOUD_PROJECT`: ID público del proyecto, `auditoria-ad-piloto`.
- `GOOGLE_DRIVE_ROOT_FOLDER_ID`: configurar mediante secretos al integrar Drive; no es necesario ponerlo en el repositorio.
- `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`: se crearán después, no ahora.
- `GOOGLE_OAUTH_REFRESH_TOKEN`: si el diseño utiliza autorización central, se almacenará como secreto, nunca en el repositorio.

## Condiciones antes de usar documentación real

1. Repositorio privado y aplicación con acceso autenticado.
2. Autorización organizacional para tratar datos de fiscalización y utilizar proveedores externos.
3. Protección de tokens y registros, trazabilidad de accesos y aislamiento por expediente.
4. Validación funcional usando solo PDF ficticios hasta cumplir las anteriores.
