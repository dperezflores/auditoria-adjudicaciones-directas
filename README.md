# AuditorIA — Adjudicaciones Directas

Piloto para la revisión documental y pruebas de auditoría de adjudicación directa de obra pública en Guanajuato.

## Estado actual
**Etapa 1: base de código y demostración de Streamlit.**
Las tres vistas originales usan datos ficticios. Ya existe un explorador Drive independiente y de solo lectura, **pendiente de configurar** con una cuenta de servicio y acceso exclusivo a la carpeta piloto. Todavía no hay Gemini ni registros persistentes.

## Objetivo
1. Detectar obras y documentos PDF en una carpeta central de Google Drive.
2. Extraer con Gemini datos del contrato, PUC, dictamen, notificación y catálogo.
3. Conservar las extracciones y evitar repetir procesamiento de PDF sin cambios.
4. Ejecutar cinco pruebas: capital contable, especialidad, vigencia PUC, responsable técnico y secuencia de fechas.
5. Mostrar resultados por obra y dashboard de la muestra.

## Tecnología
Python, Streamlit, Google Drive API, Google Sheets API, Gemini API, Pydantic, Pandas y Plotly.

## Ejecutar una demostración local

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

## Publicar en Streamlit
En [Streamlit Community Cloud](https://share.streamlit.io/) selecciona este repositorio, rama `main`, archivo principal `app.py` y despliega.

## Seguridad
El repositorio está público temporalmente. No subir credenciales, tokens OAuth, contraseñas, archivos confidenciales ni expedientes. Para trabajar con documentación real se necesitará repositorio privado, autenticación y autorización institucional. Los secretos se administrarán fuera de GitHub.

## Próximos hitos
- Conexión OAuth y sincronización incremental de Google Drive.
- Persistencia en Google Sheets.
- Análisis PDF con Gemini y caché persistente.
- Pruebas AD-01 a AD-05.
- Dashboard, trazabilidad y exportación.

El prototipo visual no debe confundirse con un dictamen de auditoría ni con una herramienta de fiscalización en producción.

## Configuración de Google Cloud

El proyecto preparado para las siguientes integraciones es `auditoria-ad-piloto`. La guía detallada para habilitar Drive y Sheets y preparar posteriormente OAuth está en [docs/CONFIGURACION_GOOGLE_CLOUD.md](docs/CONFIGURACION_GOOGLE_CLOUD.md).

**Nota:** todavía no se han habilitado ni verificado las APIs desde esta aplicación, y las credenciales no están configuradas. No cargues archivos reales mientras la versión publicada sea una demostración pública.

## Sincronización inicial de Google Drive

El módulo `services/drive_service.py` lista carpetas y metadatos PDF con la cuenta de servicio. `services/sync_engine.py` y `services/sheets_service.py` registran obras y documentos en Google Sheets mediante el botón **Actualizar Google Drive**, una vez configurada la sección `[storage]` en Streamlit Secrets. No descarga archivos ni ejecuta IA. Consulta [la guía de conexión central de Drive](docs/CONEXION_DRIVE_CUENTA_SERVICIO.md) antes de configurar credenciales.

**Limitación:** Google Sheets conserva el historial, pero no admite escrituras transaccionales concurrentes desde varias réplicas. Se utiliza un único proceso escritor durante este piloto y las actualizaciones son manuales.

## Activar persistencia

Sigue [la guía de registro persistente](docs/REGISTRO_PERSISTENTE_SHEETS.md) para añadir a Streamlit Secrets el ID de la hoja ya creada. **Nunca compartas las claves privadas de la cuenta de servicio.**
