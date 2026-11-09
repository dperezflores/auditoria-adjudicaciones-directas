# AuditorIA — Expedientes y análisis documental

## Fase 1 · Paso A: encabezado y navegación (rama de desarrollo)

> Este apartado describe los cambios **solamente en la rama `ui/fase1-explorador`**.
> La aplicación publicada desde `main` permanece sin modificar hasta su aprobación.

La interfaz muestra una barra superior con **Expedientes, Resultados y Pruebas de adjudicación**,
con Expedientes como opción inicial. El encabezado conserva la identidad del
usuario autorizado, **Cerrar sesión**, la carpeta raíz de Drive, la hora de
sincronización presentada en horario de Guanajuato, los tres indicadores de
servicio y **Actualizar Google Drive**. Mientras no se haya abierto Expedientes
ni se haya pulsado Actualizar, la barra indica **Carpeta raíz por cargar** /
**Sin revisar**, sin consultar Drive de forma invisible.

Durante este Paso A, **la pantalla Expedientes conserva su diseño y sus
controles anteriores**. El botón Actualizar también permanece dentro de
Expedientes; ambas ubicaciones llaman al mismo sincronizador con bloqueo de
escritura. Los métodos de análisis, extracción y eliminación no cambian y no
se llaman al navegar por las tres secciones. La barra lateral queda colapsada.

La interfaz usa tipografía IBM Plex Sans/Mono, la paleta aprobada de
AuditorIA y los estilos en `ui/theme.py` y `ui/styles.css`. Si las
fuentes externas no cargan, se utilizan fuentes del sistema.

Para ejecutar la rama **localmente** con credenciales de prueba y autorización
existentes:

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

Para ejecutar las pruebas sin conexión a Drive ni Gemini:

```bash
python -m unittest discover -s tests -v
```

El siguiente trabajo de Fase 1 será la Pantalla 1 (explorador de árbol), la
confirmación y el visor documental. En el Paso A **no están implementados**
los nuevos selectores, barra inferior ni visor de evidencias.

## Fase 1 · Paso B: explorador de dos columnas (rama de desarrollo)

> Se implementa **solo en la rama ui/fase1-explorador**. La aplicación
> original de Streamlit, publicada desde main, no ha sido modificada.
> El estado anterior sigue anclado al commit
> f0329c4118def3459dec8b4da65024709ce91f60.

**Acceso sin Drive ni Sheets:** si sólo se configuraron los secretos de
autenticación Google, en Expedientes se muestra una **vista previa con
datos ficticios** claramente etiquetada. No consulta Drive ni Sheets, no
presenta resultados reales y deshabilita el análisis. Esta vista permite
evaluar y probar la navegación visual sin dar acceso a expedientes.

**Con Drive y Sheets configurados:**
- La columna izquierda muestra obras, búsqueda por obra o archivo,
  filtros Todas / Con pendientes / Completas, progreso por carpeta y
  documentos desplegables. Las casillas de obra y documento seleccionan
  sólo archivos pendientes que pasan las reglas actuales de elegibilidad.
- La columna derecha muestra la obra enfocada, enlace a Drive y cinco
  tarjetas **en una fila**: Contrato, PUC, **Presupuesto** (etiqueta visual
  del CATALOGO.xlsx), Dictamen AD y Notificación AD. La Orden AD se muestra
  como complementaria cuando existe. "Falta" es informativo.
  Los títulos de carpeta se presentan de forma legible sin cambiar sus IDs.
- La tabla muestra Documento, Archivo, Págs., Estado, Último análisis y Acción.
  No se almacenan cantidades de páginas en el inventario actual: la columna
  indica **—** si no hay un dato documental verificable; únicamente en la
  demostración sintética se muestran cantidades inventadas de ejemplo.
  Último análisis corresponde a la marca de tiempo de la extracción vigente,
  no a la fecha de modificación del archivo en Drive.
  Los archivos no compatibles aparecen separados y no son seleccionables.
- **Ver datos/Revisar** abre un panel inferior de consulta que conserva la
  función anterior de extracción literal y la eliminación con confirmación
  ELIMINAR; el visor especializado de evidencias es materia del Paso D.
- La **corrección visual aprobada** permite marcar documentos de varias obras
  en la misma selección, como muestra el PDF. La barra indica el total de
  obras y documentos. Cada llamada de extracción conserva su obra original,
  y el máximo es de **10 documentos por ejecución en total**, no por obra.
  Se sigue reutilizando la función _analyze y sus verificaciones de Drive,
  checksum, esquema, caché, bloqueo y exclusión de Catálogo de Gemini.
  Al enfocar otra obra no se desmarcan los documentos de la anterior.
  La pantalla indica si una selección excede 10, sin repetir análisis
  por sí sola.
- **Aún no hay diálogo previo de confirmación ni nuevo panel de progreso.**
  Esos elementos se implementarán en el Paso C. En el Paso B la pulsación
  de Analizar inicia el proceso como en la versión original.
- Ninguna acción de búsqueda, navegación, selección o consulta invoca
  Gemini. Una falla no provoca reintento automático.

**Fidelidad a la maqueta PDF:** se retiró la fila de métricas generales,
  el encabezado ocupa una sola banda, el árbol y las filas son compactos,
  las tarjetas son horizontales y la barra inferior incluye círculo con
  contador y el total de obras. La ruta de Drive muestra la carpeta real,
  jamás la ruta local ficticia que aparece en la maqueta. Las pestañas
  se presentan como «Expedientes», «Pruebas de auditoría» y «Base de datos»,
  pero conservan internamente las secciones que la app ya tenía.

**Principio de equivalencia:** se reutiliza el backend de ui/expedientes.py
y se añade una función pura services/selection_rules.py para construir
los estados de selección. tests/test_selection_rules.py incluye un oráculo
independiente basado en las reglas originales, con casos de análisis
vigente, solicitud bloqueada, documento desactualizado, formato incompatible
y límite 10. Ninguna función existente de extracción, caché o almacenamiento
ha sido reemplazada.

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
