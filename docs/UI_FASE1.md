# PROMPT — AuditorIA AD · Rediseño de interfaz, Fase 1
## Repositorio `dperezflores/auditoria-adjudicaciones-directas`
### Explorador de expedientes (Propuesta A), Analizar con IA y "Documento con evidencia"

> Para Claude Code en VS Code, dentro del repositorio. Guárdalo como `docs/UI_FASE1.md`.
> Te adjunto capturas del diseño aprobado: son la referencia visual principal.

---

## 0. REGLA PRINCIPAL

**Esto es un rediseño de interfaz, no un cambio de funcionalidad.** El resultado debe verse y comportarse como el diseño, pero con las mismas reglas que ya tiene la app.

**Se conserva sin cambios:**
- Fuente de datos: Google Drive con cuenta de servicio y Google Sheets como registro maestro.
- Acceso con Google (`security/app_access.py`, `st.login` / `st.logout`) y la lista de usuarios autorizados.
- Clasificación documental **por nombre de archivo** (`services/document_classifier.py`), sin asignación manual de tipo.
- Extractores y su despacho por tipo: CONTRATO-v2, PUC-v1, DICTAMEN_AD-v1, NOTIFICACION_AD-v1, ORDEN_AD-v1 y CATALOGO.xlsx sin IA.
- Caché y reutilización; bloqueo de intentos incompletos **sin reintentos automáticos**; `get_writer_lock()`; límite de **10 documentos por ejecución** (`MAX_BATCH`); límites de 50 MB por PDF y 15 MB por XLSX.
- El PDF se envía **completo** a Gemini (no hay selección de páginas).
- Eliminar análisis con confirmación escribiendo `ELIMINAR`.
- Las secciones **Resultados** y **Pruebas de adjudicación** no se tocan en esta fase, salvo para integrarlas a la nueva navegación.

**No hagas, sin mi aprobación explícita:**
- cambiar servicios en `services/`, esquemas, hojas de Sheets o reglas de caché;
- agregar dependencias a `requirements.txt`;
- modificar o borrar pruebas existentes.

Si una parte del diseño exige funcionalidad que hoy no existe, **no la inventes**: adapta el diseño a lo que la app ya hace y anótalo (ver sección 2).

---

## 1. PRIMER PASO: REVISAR EL REPOSITORIO Y ADAPTAR ESTE PROMPT

Antes de escribir código:

1. Lee `README.md`, `app.py`, `ui/expedientes.py`, `ui/resultados.py`, `services/analysis_catalog.py`, `services/drive_service.py`, `services/document_classifier.py`, `services/review_service.py`, `services/analysis_deletion.py`, los `*_schema.py`, `docs/INTERFAZ_OPERATIVA_EXPEDIENTES.md` y las pruebas en `tests/`.
2. Verifica los hallazgos de la sección 2. Corrígelos si algo no es como está descrito.
3. Entrégame un **documento de adaptación** (`docs/UI_FASE1_ADAPTACION.md`) con:
   - qué partes del diseño se implementan tal cual;
   - cuáles se adaptan, cómo y por qué (funcionalidad inexistente o límite de Streamlit);
   - qué archivos crearás y cuáles modificarás;
   - qué pruebas de regresión se verán afectadas y cómo mantendrás las mismas garantías;
   - las decisiones que necesitas que yo tome (sección 9).
4. **Espera mi aprobación** antes de programar.
5. Trabaja en una rama nueva, `ui/fase1-explorador`. Streamlit Community Cloud publica desde `main`, así que **no fusiones a `main`** hasta que yo lo apruebe.

---

## 2. HALLAZGOS PREVIOS DEL REPOSITORIO (VERIFÍCALOS)

| Tema | Cómo está hoy | Consecuencia para el diseño |
|---|---|---|
| Navegación | `st.radio` en la barra lateral: Expedientes, Resultados y Pruebas de adjudicación. La barra lateral muestra sesión, servicios conectados y "Cerrar sesión". | Pasa a una barra superior con esos mismos tres nombres. La sesión y el botón de salir se reubican en el encabezado o en un menú. El estado de Drive, Sheets y Gemini se conserva en un lugar visible. |
| Actualizar | Botón "Actualizar Google Drive" (`_refresh_inventory`) y carga inicial automática. Hora en `ex_synced_at` (UTC). | Se mantiene el texto del botón; se muestra "Revisada hace N min" en hora local. |
| Tipos documentales | CONTRATO, PUC, CATALOGO (xlsx), DICTAMEN_AD, NOTIFICACION_AD, ORDEN_AD (opcional) y POR_IDENTIFICAR, todos por nombre. | Los 5 esperados son Contrato, PUC, Catálogo, Dictamen AD y Notificación AD. La Orden AD solo aparece si existe y nunca cuenta como "Falta". Los no identificados **no tienen "Asignar tipo"**: muestran "Renombra el archivo y actualiza Drive". |
| Estados por archivo | `analysis_catalog.file_states`: Analizado, Pendiente, Parcial, Desactualizado, Revisar error, Sin registrar. | Se mapean a las píldoras del diseño (sección 3.3). |
| Estados por carpeta | `folder_states`: Analizada, Parcial, Pendiente, Revisar error, Sin PDF; progreso `complete/total`. | Se usan en el resumen de cada obra del árbol. |
| Elegibilidad | `render_expedientes` calcula elegibles, reutilizados, bloqueados e ignorados; `batch = to_process[:MAX_BATCH]`. | Esa lógica decide qué se puede marcar y qué dice la ventana de confirmación. Extráela a funciones puras **sin cambiar sus reglas**. |
| Análisis | `_analyze(obra, selection, model)` procesa una obra, en secuencia, con `st.progress`, y devuelve una bitácora. | El panel de progreso del diseño se alimenta de esa misma ejecución. Puedes agregar una función de aviso por documento sin cambiar qué se procesa ni cómo. |
| Reanálisis | No hay "volver a analizar". Un resultado vigente se reutiliza. Para repetir, primero se elimina el análisis. | La ventana de confirmación **no lleva** la casilla "Volver a analizar"; explica que los ya analizados se omiten y que, para repetir, se elimina el análisis desde la vista del documento. |
| Errores | "Revisar error" bloquea nuevos intentos de ese esquema. | El botón del diseño "Reintentar" se cambia por **"Revisar"**, que abre el documento con el detalle y la opción de eliminar el análisis. |
| Páginas | `DocumentRecord` no guarda número de páginas y el PDF se envía completo. | Donde el diseño dice "páginas", muestra **tamaño (MB)** y "se envía completo". Si al renderizar la vista del documento se obtiene el número de páginas, puede mostrarse ahí. |
| Datos extraídos | Cada esquema guarda campos `{valor, pagina, evidencia}` literales, más listas (participantes, especialidades, fundamentos, obligaciones, etc.). Etiquetas en `FIELD_LABELS_V2`, `PUC_LABELS`, `DICTAMEN_LABELS`, `NOTIFICACION_LABELS` y `ORDEN_LABELS`. | La vista muestra el **valor literal** (no hay valor normalizado aparte), su página y su evidencia. Las listas van como tablas debajo de los campos. |
| Correcciones | `review_service` (hoja `RevisionesContrato`) registra Confirmado, Corregido o No localizado, **solo para CONTRATO**, y hoy no se muestra en el flujo operativo. | Decisión 9.2: mostrarlo solo en Contrato o dejar la vista de solo lectura. |
| Abrir PDF | "Ver documento en Drive" con `st.link_button` a `drive.google.com/file/d/{id}/view`. | Ese es el botón "Abrir PDF" del diseño. |
| Imagen de la página | No hay librería para renderizar PDF (`pypdf` no dibuja páginas). | Decisión 9.1. |
| Pruebas | `unittest`. La CI instala solo pydantic, google-genai, openpyxl y pypdf (**sin streamlit**) y ejecuta `python -m unittest discover -s tests`. Varias pruebas **leen el texto** de `ui/expedientes.py` y `ui/resultados.py` (por ejemplo, `key="ex_analyze"`, `disabled=disabled`, `"CONTRATO": CONTRACT_SCHEMA_V2`, `if pending_attempt:`, `st.session_state["ex_last_run"] = _analyze(`). | Esas cadenas protegen garantías (análisis manual, despacho por tipo, sin reintentos automáticos). Mantenlas en `ui/expedientes.py`. Si moverlas es inevitable, propón cómo actualizar las pruebas **conservando la misma garantía** y espera mi aprobación. Los módulos nuevos de lógica no deben importar `streamlit`. |

---

## 3. SISTEMA VISUAL

Centralízalo en `ui/theme.py` (constantes y mapeos) y `ui/styles.css`, inyectado una sola vez. Reemplaza el bloque de CSS de `app.py` por este sistema, conservando lo útil.

### 3.1. Tipografía
- **IBM Plex Sans** (400–700) para texto. **IBM Plex Mono** para nombres de archivo, rutas, números de contrato y RFC.
- Carga las fuentes desde Google Fonts, con `system-ui` y `monospace` como respaldo.
- Tamaños: título 26 px / 600; sección 16 px / 600; texto 14 px; secundario 12–13 px.

### 3.2. Colores

| Token | Valor | Uso |
|---|---|---|
| fondo | `#F4F5F7` | Fondo de la app |
| superficie | `#FFFFFF` | Paneles y tablas |
| borde | `#E1E4E8` | Separadores |
| borde_fuerte | `#D3D8DE` | Botones secundarios y campos |
| texto | `#18212B` | Texto principal |
| texto_2 | `#3A4552` | Texto de apoyo |
| texto_3 | `#5B6573` | Etiquetas |
| acento | `#1F4FD1` | Botón principal, selección y enlaces |
| acento_suave | `#E8EEFC` | Sección activa y obra enfocada |
| seleccion | `#F3F6FE` | Fila seleccionada |
| oscuro | `#18212B` | Barra inferior de selección |

En `.streamlit/config.toml` agrega a `[theme]`: `primaryColor = "#1F4FD1"`, `backgroundColor = "#F4F5F7"`, `secondaryBackgroundColor = "#FFFFFF"`, `textColor = "#18212B"`. Conserva `base = "light"`.

### 3.3. Píldoras de estado (mapeo desde `file_states`)

Todas las píldoras llevan ícono y texto: radio 999 px, 12 px, peso 500, padding `3px 10px 3px 8px` y un SVG de 13 px con `stroke="currentColor"` (viewBox 24).

| Estado actual | Texto en pantalla | Texto | Fondo | Ícono (path SVG) | Acción en la tabla |
|---|---|---|---|---|---|
| Analizado | Analizado | `#17603C` | `#E3F2EA` | `M20 6 9 17l-5-5` | **Ver datos** |
| Pendiente | Por analizar | `#8A4B06` | `#FDF0DC` | `M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18` | **Analizar** |
| Parcial | Parcial | `#7A5200` | `#FFF4D6` | `M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18M12 3v18` | **Ver datos** |
| Desactualizado | Modificado | `#2142A8` | `#E6EDFD` | `M21 12a9 9 0 1 1-3-6.7L21 8M21 3v5h-5` | **Analizar** (si es elegible) |
| Revisar error | Error | `#A4281B` | `#FCE8E6` | `M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z` | **Revisar** |
| Sin registrar | Sin registrar | `#5B6573` | `#F1F3F5` | `M12 8v4M12 16h.01` | (texto: "Actualiza Google Drive") |
| POR_IDENTIFICAR | Sin identificar | `#6A3FA0` | `#F1EAFB` | `M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3M12 17h.01` | (texto: "Renombra el archivo") |
| Tipo esperado ausente | Falta | `#5B6573` | `#F1F3F5` | `M5 12h14` | — |
| Sin extractor, formato no compatible o tamaño excedido | No compatible | `#5B6573` | `#F1F3F5` | `M6 6l12 12M18 6 6 18` | — |

- Los estados de carpeta (Analizada, Parcial, Pendiente, Revisar error, Sin PDF) se muestran como texto en el resumen de cada obra, con el mismo color de su equivalente.
- Si `analysis_catalog` produce un estado que no está en la tabla, muéstralo con estilo gris y su texto original; no lo ocultes.

### 3.4. Componentes base (`ui/components.py`)
- `pildora_estado`, `icono`, `encabezado_app`, `barra_seleccion`.
- Botón principal: fondo acento, texto blanco. Botón secundario: blanco, borde `borde_fuerte`. Alto de 40–44 px y radio 8 px.
- Para estilizar un bloque usa `st.container(key="...")` y apunta en CSS a `.st-key-<key>`. No uses clases internas generadas de Streamlit.

---

## 4. ESTRUCTURA GENERAL

### 4.1. Encabezado superior
- **Izquierda:** cuadro oscuro de 34 px con "A", "AuditorIA" y debajo "Adjudicaciones directas".
- **Navegación:** **Expedientes · Resultados · Pruebas de adjudicación** (los nombres actuales). La activa con fondo acento_suave y texto acento. Usa `st.navigation(..., position="top")` (la versión requerida, ≥1.66, lo permite) o, si choca con la estructura actual, `st.segmented_control`. Conserva el valor por defecto (Expedientes).
- **Derecha:**
  - el nombre de la carpeta raíz (`inventory.root_name`) en mono, con ícono de carpeta;
  - "Revisada hace N min";
  - el botón secundario **Actualizar Google Drive**;
  - el correo del usuario (`st.user.email`) con la opción **Cerrar sesión**.
- **Servicios conectados:** el estado de Drive, Sheets y Gemini (●/○) se mantiene, como indicadores pequeños en el encabezado o en un menú desplegable.
- **Barra lateral:** ya no se usa para navegar. Colápsala por defecto (`initial_sidebar_state="collapsed"`) o elimínala si todo su contenido quedó reubicado.
- El pie de página actual ("Los resultados requieren revisión profesional") se conserva.

### 4.2. Estado de interfaz
- Selección, obra enfocada, obras desplegadas, filtro y documento abierto viven en `st.session_state`, con claves con prefijo `ex_`.
- **No asignes a `session_state` una clave que ya use un widget**: hay una prueba que lo vigila.
- El documento abierto en la Pantalla 3 se indica con `st.query_params` (ej. `?doc=<id>`).

---

## 5. PANTALLA 1 · EXPLORADOR DE EXPEDIENTES (Propuesta A)

Reemplaza la presentación actual de `render_expedientes`: métricas, lista de expanders, "Extracción documental" con radio de alcance y "Consultar análisis guardado". Conserva su lógica.

Usa dos columnas: **izquierda ~320 px** con el árbol y **derecha** con el detalle de la obra enfocada.

### 5.1. Columna izquierda: obras
- **Encabezado:** "Obras en la carpeta" y "N obras · M por analizar".
- **Búsqueda:** campo "Buscar obra o archivo" (misma lógica que `ex_search`: nombre de carpeta o de archivo).
- **Filtros en píldoras** (`st.pills` o `st.segmented_control`, selección única): **Todas · N**, **Con pendientes · N**, **Completas · N**. "Completas" significa carpeta "Analizada". Si conviene, conserva además los filtros actuales de estado.
- **Fila de obra** (52 px mínimo):
  - **casilla de obra**: marca **solo los documentos elegibles** de esa obra según las reglas actuales;
  - flecha para desplegar;
  - ícono de carpeta y nombre;
  - resumen: "3 de 5 documentos analizados · 2 por analizar", "Todo analizado" o "Sin PDF";
  - píldora **Nueva** si la obra no tiene ningún documento analizado ni intento registrado.
  - Si solo algunos documentos están marcados, muestra el estado parcial con un guion (–) junto a la casilla.
  - Al hacer clic en el nombre, la obra queda enfocada (fondo acento_suave) y se despliega.
- **Documentos desplegados** (sangría de 46 px y línea vertical): casilla (solo si es elegible), tipo documental y el ícono de estado a la derecha. Los tipos esperados ausentes aparecen en gris como "Falta". Las subcarpetas internas se indican con su `relative_path`.

### 5.2. Columna derecha: obra enfocada
- **Migas de pan:** "Expedientes / " más el nombre de la carpeta (mono).
- **Título** con el nombre de la obra (26 px) y su resumen.
- **Acciones:**
  - **Abrir en Drive**: `st.link_button` a la carpeta (`work.url`);
  - **✦ Analizar esta obra (N)**, solo si hay elegibles: abre la confirmación con los elegibles de esta obra.
- **Sección "EXPEDIENTE":** una tarjeta por documento esperado (Contrato, PUC, Catálogo, Dictamen AD, Notificación AD) con su píldora. Si existe Orden AD, se agrega una sexta tarjeta marcada "Opcional".
- **Tarjeta "Archivos en la carpeta"** (filas con `st.columns`, no `st.dataframe`).
  - Columnas: casilla · **Documento** (tipo) · **Archivo** (mono, con `relative_path`) · **Tamaño** (MB) · **Estado** (píldora) · **Actualizado** (`modified_time` en `dd/mm/aaaa`) · acción.
  - Las acciones son las de la tabla 3.3. **Ver datos** y **Revisar** abren la Pantalla 3.
  - Debajo van los **otros archivos** (Word, imágenes, Excel que no es catálogo) en gris: "Formato no compatible" o "Sin extractor".
- **Leyenda de estados** al pie, con una explicación corta de cada uno, igual que en el diseño.

### 5.3. Barra inferior de selección (fija)
- Contenedor con `key` y CSS `position: fixed; bottom: 0`, a todo lo ancho. Deja margen inferior en la página para que no tape contenido.
- **Con selección:** fondo oscuro.
  - Contador.
  - "N documentos seleccionados en M obras".
  - En gris claro: "X MB en total · K catálogos se importan sin IA".
  - **Limpiar selección**.
  - **✦ Analizar con IA**, deshabilitado si falta la clave de Gemini y hay PDF en la selección (misma regla que hoy).
- **Sin selección:** fondo blanco y "Marca obras completas o documentos sueltos para analizarlos con IA. Los documentos ya analizados se omiten solos."

---

## 6. PANTALLA 2 · ANALIZAR CON IA

### 6.1. Confirmación (`@st.dialog`)
Calcula todo con las **mismas reglas** que hoy usa `render_expedientes`: elegibles, reutilizados, bloqueados, ignorados, fuera de límite y `MAX_BATCH`.

- **Título:** "Analizar N documentos con IA" (o "Importar N catálogos sin IA" si solo hay Excel). Subtítulo: "Revisa lo que se enviará antes de empezar."
- **Tres cifras:**
  - documentos a procesar en esta ejecución, de M obras;
  - tamaño total enviado a Gemini (MB);
  - omitidos, en verde: "ya analizados".
- **Lista agrupada por obra:**
  - **PDF normal:** tipo, archivo y "4.2 MB · se envía completo".
  - **Catálogo:** "Excel · se importa sin IA".
  - **Omitidos:** con su motivo: ya analizado (reutilizado), intento sin confirmar (bloqueado; mostrar el aviso actual), sin extractor, o supera el límite de tamaño.
- **Límite por ejecución:** si hay más de 10, dilo claramente: "Se analizarán 10 ahora. Los N restantes quedarán listos para la siguiente ejecución." Es el comportamiento actual.
- **Varias obras:** hoy `_analyze` recibe una sola obra. Para la selección de varias obras, la ejecución recorre las obras en orden llamando a la misma función, con un máximo total de 10 documentos. Esto es una decisión que debo aprobar (9.3).
- **Pie:**
  - el texto "Modelo Gemini: X";
  - el texto "Cada documento se guarda en cuanto termina.";
  - **Cancelar**;
  - **✦ Iniciar análisis**, que conserva el control actual: el botón `key="ex_analyze"`, `disabled=disabled` y la llamada `st.session_state["ex_last_run"] = _analyze(...)`, adaptados a su nueva ubicación.
- No agregues casillas de "autorización". Hay una prueba que lo impide a propósito.

### 6.2. Panel de progreso
Muéstralo mientras corre `_analyze`. Agrégale un parámetro opcional de aviso por documento (ej. `on_progress`) que no cambie la lógica.

- **Encabezado:** "Analizando N documentos", "X de N procesados · A listos, B con problema" y el porcentaje grande.
- **Barra en HTML de dos colores:** verde `#2E9E63` para los listos y rojo `#D9483B` para los que tuvieron problema.
- **Una fila por documento** con círculo de estado de 32 px, "Tipo · Obra", archivo y estado:
  - **Listo:** "Analizado y guardado", "Reutilizado (sin IA)" o "Importado desde Excel (sin IA)", con **Ver datos**.
  - **Problema:** fondo `#FFF8F7` y el mensaje de la bitácora actual, sin cambiarlo. El botón es **Revisar**, nunca "Reintentar".
  - **Analizando:** fondo `#F7F9FE`.
  - **En cola:** círculo punteado.
- **Al terminar:** el panel queda como resumen de la última ejecución (reemplaza la tabla `ex_last_run`), con **Volver a Expedientes**. Los estados se recargan con `load_status_tables`, como hoy.
- **Detener:** Streamlit interrumpe la ejecución al tocar cualquier control. Si lo usas, los documentos ya guardados se conservan y el que estaba en curso puede quedar "Revisar error". Explica esto en la interfaz y en la adaptación.

---

## 7. PANTALLA 3 · VER DATOS · DOCUMENTO CON EVIDENCIA

Sustituye "Consultar análisis guardado". Lee **solo de Sheets**, como `_summarize_saved`, sin llamar a Gemini.

### 7.1. Encabezado
- **Migas de pan:** "Expedientes / Obra / Tipo".
- **Título:** el tipo documental. Debajo: "ARCHIVO.pdf · X MB · versión de esquema (ej. contrato-v2) · modelo".
- **Acciones:**
  - **Abrir en Drive** (enlace actual);
  - **Eliminar análisis** (el flujo actual de `_render_delete_analysis`, con `ELIMINAR`, en un `st.dialog` o expander).
- **Pestañas por documento de la obra:** Contrato, PUC, Catálogo, Dictamen AD, Notificación AD y Orden AD si existe, cada una con su ícono de estado. Las no analizadas muestran "Este documento aún no se analiza" y el botón **Analizar** (abre la confirmación con ese documento).

### 7.2. Columna izquierda: la página
- **Con imagen de la página (si apruebas 9.1):**
  - botones con las páginas citadas en la evidencia de los campos (ej. 1 · 2 · 3 · 4 · 23), la activa en acento;
  - la imagen de la página citada por el dato seleccionado.
  - Descarga el PDF con `download_verified_pdf` (que ya valida obra y checksum).
  - Renderiza **solo la página visible** a ~110–130 ppp.
  - Guarda en caché con `st.cache_data`, por (id del documento, md5, página).
  - No guardes PDF en disco de forma permanente.
- **Debajo, siempre, el recuadro de evidencia** del dato seleccionado: fondo `#FFF1C2`, borde 2 px `#E3A23B`, el texto de `evidencia` y "pág. N".
- **Sin página o sin evidencia:** un mensaje centrado: "«Campo» no se localizó en el documento".
- No dibujes recuadros sobre la imagen: la extracción no guarda coordenadas.

### 7.3. Columna derecha: datos extraídos
- **Encabezado:** "Datos extraídos" y "N campos · X localizados · Y no localizados".
- **Filtros en píldoras:** **Todos · N**, **No localizados · N** y, si se aprueba 9.2, **Cotejados · N**.
- **Campos** a partir de las etiquetas existentes de cada esquema, en el orden actual. Puedes agruparlos en secciones (por ejemplo, para el contrato: Identificación, Partes, Objeto, Montos, Plazo y firma), con el agrupamiento definido en `ui/theme.py` y sin tocar los esquemas.
- **Cada campo es una fila con zona clicable:**
  - la etiqueta;
  - el **valor literal** en 14 px / 600 (mono para número de contrato, RFC o registro PUC), o "No localizado" en gris;
  - debajo, la píldora **Localizado** (verde) o **No localizado** (gris) y "pág. N".
  - Al seleccionarla, la página de la izquierda cambia.
  - La fila seleccionada lleva borde de 1.5 px acento y fondo de selección.
- **Listas del esquema**, debajo de los campos, como tablas compactas con su página y evidencia:
  - **Contrato:** personas participantes, legislación citada con su "clasificación preliminar" y fuente de financiamiento.
  - **PUC:** especialidades y advertencias.
  - **Dictamen, Notificación y Orden:** sus listas (fundamentos, motivaciones, obligaciones, plazos, personal designado, documentos citados, advertencias).
  - **Catálogo:** las tres cifras actuales y la tabla de conceptos (primeros 300), con las notas actuales.
  - **Análisis antiguos** (`documento-schema-v1`, contrato v1): se siguen mostrando con el formato actual.
- **Leyendas obligatorias:** se conservan las que ya existen ("Los valores son transcripciones de Gemini, no resultados de las pruebas…", etc.).
- **Cotejo (solo si apruebas 9.2):** solo en Contrato, un botón **Cotejar** por campo que despliega un formulario con decisión (Confirmado, Corregido, No localizado), valor cotejado, página y evidencia. Usa `review_service.save_review` tal como existe. El campo muestra la última decisión ("Corregido por auditor" en azul `#2142A8` sobre `#E6EDFD`, con el ícono de lápiz `M4 20h4L19 9l-4-4L4 16z`). La extracción original nunca se modifica.

### 7.4. Formato
- Fechas de Drive en `dd/mm/aaaa`, en hora local.
- Los valores extraídos se muestran **tal como están** (literales); no los reformatees.

---

## 8. ARCHIVOS SUGERIDOS

```text
ui/
├── theme.py              # tokens, mapeo de estados, agrupación de campos
├── styles.css
├── components.py         # píldoras, íconos, encabezado, barra de selección
├── expedientes.py        # Pantalla 1 (conserva las garantías que vigilan las pruebas)
├── analysis_dialog.py    # confirmación y panel de progreso
└── document_view.py      # Pantalla 3
services/
└── selection_rules.py    # lógica pura de elegibilidad y selección, extraída sin cambios de regla
```

`services/selection_rules.py` **no importa streamlit**. Recibe inventario, tablas y estados, y devuelve: elegibles, reutilizados, bloqueados, ignorados, fuera de límite y el lote de `MAX_BATCH`.

---

## 9. DECISIONES QUE NECESITO TOMAR (inclúyelas en la adaptación)

1. **Imagen de la página del PDF.** Requiere agregar `pypdfium2` a `requirements.txt` (funciona en Streamlit Cloud). Sin ella, la vista muestra solo la evidencia textual y el botón "Abrir en Drive".
2. **Cotejo de campos.** ¿Se muestra el cotejo existente (`RevisionesContrato`) en la vista del contrato? Hoy está oculto en el flujo operativo. Si no, la vista queda de solo lectura.
3. **Analizar varias obras en una ejecución.** ¿Se permite recorrer varias obras con la misma función, con tope total de 10? Si no, la barra de selección se limita a una obra a la vez y lo avisa.
4. **Barra lateral.** ¿Se elimina por completo o se deja colapsada con la información de servicios?

---

## 10. PRUEBAS

- **Todas las pruebas existentes deben pasar:** `python -m unittest discover -s tests -v`, en el mismo entorno mínimo de la CI, sin streamlit instalado.
- **Pruebas nuevas en `unittest`** para `services/selection_rules.py`, que verifiquen que da **exactamente** los mismos resultados que la lógica actual:
  - la casilla de obra marca solo elegibles;
  - los analizados vigentes se cuentan como reutilizados;
  - los intentos `EN_PROCESO` / `REQUIERE_REVISION` quedan bloqueados;
  - los archivos fuera de límite o sin extractor se ignoran;
  - el lote respeta `MAX_BATCH`;
  - un "Falta" nunca es seleccionable.
- **Equivalencia:** antes de borrar el código viejo de selección, compara su resultado con el nuevo sobre los mismos datos simulados.
- **Revisión visual:** si Playwright está disponible (o con mi autorización), toma capturas de las tres pantallas con datos simulados (sin Drive ni Gemini reales) y compáralas con las del diseño. Dime en qué difieren.
- No ejecutes llamadas reales a Gemini ni a Drive durante el desarrollo. Si lo haces con mi autorización, dilo explícitamente.

---

## 11. ORDEN DE TRABAJO

1. Revisión del repositorio y `docs/UI_FASE1_ADAPTACION.md`. Espera mi aprobación.
2. **Paso A:** tema, estilos, componentes, encabezado y navegación superior. Expedientes sigue funcionando igual.
3. **Paso B:** `selection_rules.py` con sus pruebas de equivalencia y la Pantalla 1 completa con la barra de selección.
4. **Paso C:** confirmación y panel de progreso conectados a `_analyze`.
5. **Paso D:** Pantalla 3, con imagen de página y cotejo solo si se aprobaron.
6. En cada paso:
   - corre las pruebas;
   - actualiza `docs/INTERFAZ_OPERATIVA_EXPEDIENTES.md` si cambió cómo se usa la pantalla;
   - dime cómo verlo con `streamlit run app.py`.
7. Commits pequeños en la rama `ui/fase1-explorador`. **No fusiones a `main` sin mi aprobación.**
8. Cuando Streamlit no permita igualar el diseño, usa la alternativa más cercana y regístrala en la adaptación. **Nunca** resuelvas una diferencia cambiando reglas de análisis, caché o seguridad.