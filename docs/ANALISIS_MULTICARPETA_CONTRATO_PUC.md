# Análisis multicarpeta de CONTRATO y PUC

## Alcance

Función de la **app original** de AuditorIA, dentro de **Expedientes >
Extracción documental > Modalidad de análisis > Varias carpetas**.
El modo «Una carpeta» sigue operando como antes. La app visual de pruebas
(`ui/fase1-explorador`) no se modifica.

Esta función automatiza una selección repetitiva sobre el inventario de
**Google Drive ya sincronizado**. No cambia los PDFs, ni los prompts,
ni los extractores, ni los esquemas de Google Sheets. Tampoco
modifica pruebas legales de adjudicación.

## Uso

1. Entrar en **Expedientes**. Si has añadido carpetas o PDFs desde la
   última visita, pulsar **Actualizar Google Drive**.
2. Elegir **Varias carpetas**.
3. En «Carpetas a incluir», seleccionar **Todas las carpetas** o
   **Seleccionar varias carpetas** y buscar por nombre. La carpeta
   `Recursos` se excluye porque aloja archivos de referencia y no es obra.
4. En «Documentos a analizar en cada carpeta», seleccionar una o ambas:
   `CONTRATO.pdf`, `PUC.pdf`.
5. Revisar los indicadores de documentos pendientes, ya analizados,
   bloqueados y faltantes; desplegar **«Ver documentos y estado por
   carpeta»** para identificar cada caso.
6. El sistema muestra los **primeros 10 PDF pendientes compatibles**
   como próximo bloque, en el orden estable del inventario de Drive.
7. Marcar la casilla que confirma el posible consumo de Gemini y pulsar
   **«Analizar siguiente bloque de N PDF(s)»**.
8. Consultar el registro de cada archivo del último bloque, ahora con
   columna **Carpeta**. Si hay más pendientes, repetir la confirmación
   y ejecutar el siguiente bloque. No se repiten los correctamente
   guardados.

## Reglas de protección

- Cada ejecución admite **como máximo 10 PDFs**. La selección puede
  abarcar más carpetas, pero el proceso avanza **por bloques explícitos**,
  nunca automáticamente ni en segundo plano.
- Cada PDF se procesa con el **extractor existente de su propio tipo**;
  no se envía el PUC al prompt de contrato.
- El sistema utiliza la misma validación de Drive por obra,
  pertenencia del archivo, huella MD5, MIME y tamaño máximo de 50 MB,
  así como el cerrojo de escritura y las tablas de caché de Sheets.
- Los archivos con extracción especializada vigente aparecen como
  **Ya analizado** y no generan una nueva llamada a Gemini, aunque
  el prompt se haya actualizado. Para una actualización intencional de
  un contrato antiguo existe la función individual de actualización.
- Intentos **EN_PROCESO / REQUIERE_REVISION**, PDF ausentes o con nombre
  no canónico, registro de Drive/Sheets discordante, archivos demasiado
  grandes, o varios `CONTRATO.pdf` / `PUC.pdf` dentro de la misma obra
  no se procesan automáticamente.
- La confirmación se invalida al cambiar cualquier carpeta, tipo,
  contenido del bloque o después de ejecutar un bloque.
- No se inician solicitudes a Gemini al cambiar la selección, consultar
  estados, listar archivos o navegar entre páginas.
- El resumen de último bloque contiene **Carpeta, Documento, Tipo,
  Resultado**. Las vistas **Resultados** y **AD-06** se actualizan a
  partir de Sheets después de una ejecución.

## Limitaciones del piloto

El análisis es **secuencial**, no concurrente. Se conserva el límite
de 10 PDF por ejecución para controlar latencia, gastos API y errores
incompletos. Para tratar 100 documentos hay que solicitar diez bloques;
el sistema muestra cuántos faltan sin repetir los ya confirmados.

Los registros de la tabla de historial permanecen en las hojas
existentes y no se crea una cola o automatización en segundo plano.
Este flujo no compara todavía el contenido entre dos documentos
de una misma obra: únicamente extrae y guarda sus datos por separado.
