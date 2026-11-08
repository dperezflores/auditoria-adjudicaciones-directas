# Eliminación y repetición de una extracción en AuditorIA

## Alcance
La opción **Eliminar análisis guardado de este archivo** se encuentra en
**Expedientes → Consultar análisis guardado**, debajo de la ficha extraída
del documento seleccionado.

La acción es **por documento**, no por carpeta. Se identifican el ID de
Drive del PDF, su obra, nombre, tipo MIME y huella MD5; también se comprueba
que la ficha que vio el usuario siga vigente. Solo una persona autenticada
puede solicitarla.

## Qué se elimina
- Filas de **Extracciones** asociadas con ese archivo, incluidas las
  reservas incompletas que no estén en proceso.
- Filas correspondientes al mismo documento de **DatosPUC**,
  **DatosDictamenAD**, **DatosContrato**, **DatosContratoV2** y
  **RevisionesContrato**, si las hay.
- Las referencias al análisis en **Documentos** (versión de extractor,
  resultado y último error). Se deja su estado en **Pendiente**.

No se elimina ni modifica el PDF ni se borran otras carpetas, otros
documentos, los encabezados de Sheets o la configuración de la aplicación.
La acción no llama a Gemini.

## Trazabilidad y prevención de errores
Se añade un evento en **Historial** con ID, fecha, documento, obra,
resultado anterior, estado nuevo y correo de la persona que solicitó la
eliminación. Se conservará ese evento aunque se repita el análisis.
Las filas eliminadas **no pueden restaurarse desde la propia aplicación**:
si se necesita recuperar la extracción hay que acudir al respaldo del
archivo maestro, si existe.

La acción exige escribir literalmente `ELIMINAR` como confirmación.
No se permite borrar una extracción con estado `EN_PROCESO`.
Si el PDF ha cambiado, si pertenece a otra obra o si el ID del
resultado difiere del de la pantalla, se bloquea sin modificar Sheets.

Tras eliminar, se puede analizar de nuevo desde **Extracción documental**,
siempre que exista un extractor habilitado para el tipo de archivo.
Una nueva llamada a Gemini puede consumir tokens o generar un cargo adicional.
No hay reanálisis automático como consecuencia del borrado.

## Caso específico: notificación procesada como dictamen
El 8 de noviembre de 2026 se retiró la extracción incorrecta del archivo
`DICTAMEN_AD.pdf` de la obra `00_591_25_ParqueUyepac`.
Se guardó una copia previa del maestro en la carpeta de respaldos y
se verificó que `DatosPUC` y su extracción anterior permanecen intactos.

**Aún debe corregirse el archivo en Google Drive**: el PDF que contiene
la notificación debe renombrarse a `NOTIFICACION_AD.pdf` y el dictamen
verdadero debe cargarse con el nombre `DICTAMEN_AD.pdf`.
`NOTIFICACION_AD` no tiene extractor activo en esta etapa; por eso
no debe analizarse hasta incorporar su esquema propio.

## Procedimiento de usuario
1. Seleccionar la carpeta y el PDF en **Consultar análisis guardado**.
2. Expandir **Eliminar análisis guardado de este archivo**.
3. Revisar el nombre exacto y la advertencia.
4. Escribir `ELIMINAR` y pulsar **Eliminar análisis de este documento**.
5. Confirmar el mensaje de éxito y el nuevo estado **Pendiente**.
6. Si el error fue el nombre de archivo, corregirlo en Drive primero
   y pulsar **Actualizar Google Drive**.
7. Analizar nuevamente solo el documento correcto, aceptando el
   consumo de Gemini que esto pueda ocasionar.
