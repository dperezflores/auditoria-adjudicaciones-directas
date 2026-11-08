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

## Etapa Gemini: extracción de contrato ficticio bajo demanda

La integración de Gemini está programada para la **prueba exclusiva con el contrato ficticio**, bajo pulsación y confirmación del usuario. El análisis comprueba la caché persistente en Google Sheets antes de enviar el PDF. En ausencia de resultados, reserva un registro e invoca el modelo configurado en Streamlit Secrets. Las pestañas `Extracciones` y `DatosContrato` conservan los resultados. Gemini no se ejecuta automáticamente al sincronizar Drive. Consulta [el manual de la primera prueba de Gemini](docs/PRUEBA_GEMINI_CONTRATO.md).


## Cotejo manual por campo

El dashboard permite registrar la revisión humana de cada campo del contrato
con decisión `Confirmado`, `Corregido` o `No localizado`, y una referencia
a la página y evidencia del PDF. Los eventos se guardan en la hoja
`RevisionesContrato` sin sobrescribir los datos extraídos por Gemini.
Consulta [la guía de cotejo manual](docs/COTEJO_MANUAL_CONTRATOS.md).

## Interfaz operativa (expedientes de Google Drive)

La pantalla principal ya no es la demostración: ahora muestra **Expedientes**, **Resultados** y **Pruebas de adjudicación**. Desde Expedientes se ven carpetas y archivos, el estado de análisis por PDF y carpeta, y se pueden seleccionar **un PDF, varios PDFs o una carpeta completa** para analizarlos en una misma ejecución con Gemini. Los análisis se almacenan en Google Sheets y se reutilizan cuando ya existe un resultado compatible. No se generan análisis al navegar.

Lee [el manual operativo](docs/INTERFAZ_OPERATIVA_EXPEDIENTES.md) antes de conectar expedientes reales. La raíz actual de Drive sigue siendo la carpeta anteriormente configurada; para trabajar en otro repositorio, comparte la nueva carpeta con la cuenta de servicio y actualiza solo `[drive].root_folder_id` en los secretos de Streamlit. **Las pruebas normativas cruzadas todavía están por implementar.**
