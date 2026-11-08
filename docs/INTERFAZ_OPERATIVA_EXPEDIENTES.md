# AuditorIA — Expedientes y análisis documental

## Interfaz operativa

La pantalla principal usa la estructura real de la carpeta de Google Drive
definida en Streamlit Secrets `[drive].root_folder_id`. Las subcarpetas
inmediatas de esa raíz representan obras; también se recorren sus subcarpetas
internas. Se listan archivos PDF y otros formatos.

La navegación incluye:
- **Expedientes:** lista de carpetas, PDFs, estado de IA por archivo y por
  carpeta; actualización de Drive; análisis de uno, varios o todos los PDFs
  de una obra.
- **Resultados:** dashboard con 16 columnas contractuales, personas
  participantes en una celda y ficha interactiva por fila, desde Sheets
  y sin utilizar Gemini.
- **Pruebas de adjudicación:** sección disponible para implementar las
  reglas normativas específicas; todavía **no** emite determinaciones.

La vista demo dejó de ser la interfaz principal. El formulario de cotejo
humano no se exige ni se muestra en el flujo operativo.

## Formas de analizar

Al seleccionar una obra se puede elegir:
1. **Un archivo:** un PDF específico.
2. **Varios archivos:** uno o más PDFs seleccionados del mismo expediente.
3. **Carpeta completa:** todos los PDFs del expediente, incluyendo subcarpetas.

Máximo **10 PDF por ejecución** para controlar volumen, latencia y costos. Si la carpeta contiene más de diez pendientes, el modo Carpeta completa procesa el siguiente lote de diez; al repetir la acción avanza a los restantes sin repetir los ya analizados.
No se invoca Gemini por abrir la app, consultar o sincronizar. El análisis
solo comienza cuando el usuario pulsa el botón Analizar.

En esta primera versión, «Varios archivos» y «Carpeta completa» ejecutan
un análisis **individual de cada PDF dentro de un mismo lote**. El análisis
**cruzado/comparativo** entre documentos de una adjudicación (PUC vs contrato
vs dictamen, etc.) se implementará después.

## Extractor contractual único

La pantalla de Expedientes **ya no muestra selector de plantilla**: al pulsar
Analizar se utiliza siempre el extractor de contrato v2, que solicita
**16 campos literales y la lista de personas participantes**, junto con
páginas y evidencias. Esto también se aplica a PDFs de nombre abreviado.

Los análisis v1 o generales anteriores siguen consultables. Si un documento
solo tiene una extracción antigua, es posible solicitar una nueva v2
manualmente; esto podría generar consumo, pero no borra la anterior.
Si un documento tiene un resultado v2 vigente se omite; los intentos
v2 inciertos quedan bloqueados sin reintentos automáticos.

Si se selecciona un PDF no contractual, los campos no hallados quedan vacíos;
no se incorpora automáticamente al listado de contratos por el mero hecho
de que aparezca una empresa o RFC aislado. El análisis de cumplimiento
cruzado con PUC, dictámenes y otros expedientes se añadirá después.

En `Consultar análisis guardado`, **Ver PDF en Drive** aparece después
de los datos de extracción, como último control de esa sección.

Los archivos Word, Excel, imágenes y otros formatos aparecen listados,
pero **no son enviados a Gemini** en esta etapa. Tampoco se convierten
silenciosamente a PDF. En el futuro se habilitarán importadores por formato.

## Estados

- **Pendiente:** sin análisis guardado.
- **Analizado:** existe una salida completa de Gemini, almacenada para la
  versión vigente del archivo (sin implicar aprobación de auditoría).
- **Parcial:** existen valores recuperados, pero el análisis no quedó
  completamente conservado.
- **Desactualizado:** documento cambiado o metadatos no coincidentes.
- **Revisar error:** hay intentos incompletos; la app no vuelve a gastar IA
  de forma automática.
- **Sin PDF:** carpeta sin documentos compatibles.

Los estados de carpeta se derivan de sus PDF; el progreso muestra la
proporción `analizados/total PDFs`. Se conserva el historial de cambios,
y cada resultado completo tiene clave de contenido/versiones.

## Primer uso con expedientes autorizados

La carpeta raíz anterior `AUDITORIA_AD_PILOTO` permanece configurada
hasta que el usuario cambie `[drive].root_folder_id` en Streamlit Secrets
por el ID de una nueva carpeta compartida con la cuenta de servicio.
El usuario también puede añadir obras dentro de la raíz actual.

Para usar una carpeta distinta:
1. Compartir la nueva carpeta **solo lectura** con
   `auditoria-drive-reader@auditoria-ad-piloto.iam.gserviceaccount.com`.
2. Cambiar **únicamente** el valor existente `root_folder_id` de
   `[drive]` al nuevo ID (no crear una sección duplicada).
3. Mantener `[storage]`, `[gcp_service_account]`, `[gemini]`,
   `[auth]` y `[access]` intactos.
4. Abrir AuditorIA y presionar **Actualizar Google Drive**.
5. Verificar inventario y estado antes de cualquier análisis con IA.

Los resultados de documentos reales se guardan en la hoja maestra
existente; si se requiere separación por auditoría o año convendrá usar
una base o archivo específico con permisos y retención definidos.

## Privacidad y costos

El repositorio GitHub público solo guarda código, no secretos ni PDFs.
Google Drive está restringido mediante cuenta de servicio y la aplicación
mediante autenticación Google. La aplicación requiere que el usuario inicie cada solicitud manualmente;
eso **no sustituye una autorización institucional formal**.

Antes de enviar expedientes reales, revisar los términos y nivel de servicio
del proyecto Gemini: el nivel gratuito puede utilizar el contenido
para mejorar productos; consultar las condiciones vigentes en
https://ai.google.dev/gemini-api/docs/pricing .

Las llamadas de IA pueden generar costos. El motor reserva intentos,
reutiliza resultados existentes por contenido y versión y bloquea reintentos
automáticos después de un error no confirmado. Sheets no es un backend
transaccional multiinstancia; antes de la puesta en producción institucional
hay que habilitar permisos por rol, registros robustos, base transaccional
y segregación de expedientes.

## Limitaciones de esta entrega

- Sin ejecución periódica en segundo plano: Drive se consulta al
  abrir la pantalla y con el botón Actualizar.
- Documentos no PDF: se listan, pero no se analizan aún.
- Límite de 50 MB decimales por PDF (50,000,000 bytes), conforme al máximo documentado para Gemini. Los archivos mayores aparecen en el inventario, pero no se envían a la API.
- Carpetas internas: exploración de hasta seis niveles para controlar
  archivos y tiempo de respuesta.
- Las pruebas legales de capital, especialidad, vigencia PUC, responsable
  técnico y fechas dictamen/notificación/contrato aún no están implementadas.
- El resumen y los hechos del modelo son preliminares; se deben verificar
  contra el expediente documental y la normativa aplicable.

**No se ejecutaron solicitudes reales de Gemini al desarrollar este cambio.**
