# AuditorIA — Adjudicaciones Directas

Piloto para la revisión documental y pruebas de auditoría de adjudicación directa de obra pública en Guanajuato.

## Estado actual
**Etapa 5: extracción especializada de PUC, DICTAMEN_AD, NOTIFICACION_AD y ORDEN_AD.**
Google Drive y Google Sheets están conectados, la clasificación documental
se realiza por nombre y se guarda en la hoja maestra. El extractor
`PUC-v1` obtiene 18 campos literales y la lista de especialidades,
con página y evidencia, en `DatosPUC` y `Extracciones`.
PUC, DICTAMEN_AD, NOTIFICACION_AD y ORDEN_AD tienen extractores independientes; CONTRATO y CATALOGO permanecen pendientes.

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

## Extracción contractual ampliada (v2)

La extracción contractual fija de 16 campos conserva literalmente los valores del contrato (incluidas mayúsculas, puntuación, importes y fechas), incorpora una lista de personas participantes y registra la legislación citada y la fuente de financiamiento. La clasificación federal, estatal o municipal es **preliminar y derivada**, no un dictamen sobre límites de adjudicación.

Los resultados nuevos se guardan en `DatosContratoV2` y en el JSON de `Extracciones`, sin alterar `DatosContrato` v1. En **Resultados**, la tabla muestra todos los campos contractuales en columnas y reúne las personas participantes en una celda; seleccionar una obra actualiza su ficha con datos, participantes, legislación y evidencias. El enlace **Ver PDF en Drive** aparece debajo de la consulta del análisis guardado en **Expedientes**. [Ver instrucciones](docs/EXTRACCION_CONTRATOS_V2.md).


## Cruce documental de contratos y PUC

En **Resultados** cada contrato seleccionado presenta también el bloque
**Cruce documental de la obra seleccionada**. Se muestran el PUC y los demás
documentos del mismo expediente, sus estados de extracción y las referencias
de evidencia conservadas en Google Sheets. El cruce PUC-comparado presenta
RFC, número de registro, razón social, representantes y vencimiento;
adicionalmente muestra capital, especialidad y representación técnica cuando
figuran en la extracción.

Las coincidencias de datos no son determinaciones jurídicas de cumplimiento.
No se vuelve a llamar a Gemini ni se mezclan documentos de obras distintas.

[Guía del cruce documental](docs/CRUCE_DOCUMENTAL_CONTRATO_PUC.md).


## Etapa 1 — Clasificación automática de documentos por nombre

Al sincronizar Google Drive, AuditorIA asigna directamente los códigos
`CONTRATO`, `PUC`, `CATALOGO`, `DICTAMEN_AD`, `NOTIFICACION_AD` y
`ORDEN_AD` según el nombre estándar y su extensión. No verifica el
contenido del documento, no requiere confirmación manual y no utiliza
Gemini en esta etapa. Los documentos con nombres no reconocidos se muestran
como `POR_IDENTIFICAR`.

El tipo asignado se guarda en `Documentos.tipo_documental` durante
**Actualizar Google Drive**; la pantalla de verificación por contenido fue
retirada. La IA solo se ejecuta bajo demanda para PUC, DICTAMEN_AD, NOTIFICACION_AD y ORDEN_AD; el resto
permanece sin extractor especializado.

[Reglas de nomenclatura e instrucciones](docs/ETAPA_01_CLASIFICACION_DOCUMENTAL.md).

## Etapa 2 — PUC-v1

La interfaz permite analizar `PUC.pdf` de una obra,
reutilizar la caché y consultar capital contable, fechas PUC, representación
técnica y especialidades. Esto **no determina todavía cumplimiento** ni
realiza cruces automáticos. Los dictámenes nunca se envían al extractor de PUC: usan su propio
esquema DICTAMEN_AD-v1. [Guía para probar](docs/ETAPA_02_EXTRACCION_PUC.md).


## Etapa 3 — DICTAMEN_AD-v1

El extractor `DICTAMEN_AD-v1` guarda 19 campos literales y listas de
fundamentos jurídicos, motivaciones, soportes citados y firma aparente.
Se almacenan en `DatosDictamenAD` y `Extracciones`, sin alterar
`DatosPUC`. Las afirmaciones del dictamen no se consideran acreditadas:
**todavía no se ejecutan pruebas de cumplimiento ni cruces legales**.
[Guía de prueba](docs/ETAPA_03_EXTRACCION_DICTAMEN_AD.md).


## Eliminar análisis y volver a analizar un archivo

En **Expedientes → Consultar análisis guardado** puede eliminarse la
extracción de un PDF específico sin borrar el archivo de Google Drive.
La eliminación requiere escribir `ELIMINAR`, retira su caché y fichas
asociadas, lo deja **Pendiente** y registra el evento en **Historial**.
Una nueva extracción es voluntaria y puede generar consumo de Gemini.
[Procedimiento y medidas de seguridad](docs/ELIMINAR_ANALISIS.md).


## Etapa 4 — NOTIFICACION_AD-v1

El extractor `NOTIFICACION_AD-v1` conserva 21 campos literales,
separa la fecha de emisión de la fecha efectiva de recepción, distingue
el registro PUC del contratista del correspondiente a supervisión externa,
y extrae las obligaciones, los plazos textuales, el evento que inicia su
cómputo, las personas designadas y las referencias jurídicas.

Los resultados quedan en `DatosNotificacionAD` y `Extracciones`,
con evidencia y caché por archivo/modelo/versión. El botón para eliminar
el análisis también cubre este tipo documental.
No se calculan todavía fechas límite ni se aplican pruebas de auditoría.
[Guía de extracción y validación](docs/ETAPA_04_EXTRACCION_NOTIFICACION_AD.md).


## Etapa 5 — ORDEN_AD-v1

La orden de adjudicación es **opcional** en el expediente. Si existe
`ORDEN_AD.pdf`, su extractor obtiene 22 campos literales y listas
de personal designado, instrucciones, plazos, fundamentos y documentos
citados. Se guardan con página y evidencia en `DatosOrdenAD` y
`Extracciones`. La eliminación de análisis también se aplica a este
tipo documental. No se emiten todavía pruebas de cumplimiento.

[Guía de extracción y prueba de la orden](docs/ETAPA_05_EXTRACCION_ORDEN_AD.md).
