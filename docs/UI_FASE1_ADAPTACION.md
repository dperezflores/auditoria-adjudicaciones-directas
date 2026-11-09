# AuditorIA AD — Documento de adaptación de interfaz · Fase 1

**Estado: ADAPTACIÓN APROBADA PARA COMENZAR EL PASO A. El rediseño sigue aislado en su rama.**

**Aprobación del usuario:** recibida expresamente después de revisar el documento
de adaptación. Para la implementación se adoptan las cuatro opciones
recomendadas: 9.1-B (evidencia textual, sin dependencia PDF nueva),
9.2-A (cotejo en solo lectura), 9.3-A (una obra por ejecución),
9.4-B (barra lateral colapsada). Ninguna modificación se fusionará a main
sin aprobación posterior específica.

**Modificación posterior al Paso B (corrección visual aprobada):**
El usuario aportó el PDF de la **Propuesta A · Árbol y detalle**, señaló
las diferencias con la aplicación y autorizó la corrección visual.
La maqueta incluye explícitamente «documentos seleccionados en 2 obras».
Por tanto, esta autorización **supersede solamente la decisión 9.3-A**:
el panel puede seleccionar documentos de varias obras y el coordinador de
la interfaz invoca el backend existente por obra, respetando el máximo
**global** de 10 documentos por ejecución. No cambia el guardado ni los
servicios de IA. Las demás decisiones y el respaldo permanecen intactos.

La maqueta también solicita «Págs.» y «Último análisis»; el inventario
real no contiene número de páginas, de modo que se muestra «—» sin inventarlo.
La fecha de último análisis procede de Extracciones cuando está vigente.
Solo el modo de demostración muestra páginas ficticias.

**Paso A:** tema `ui/theme.py` / `ui/styles.css`, componentes base,
encabezado y navegación superior en `app.py` y `.streamlit/config.toml`.
Los servicios, los extractores y las pruebas existentes permanecen intactos.
El paso B incluirá servicios de reglas puras únicamente si se confirma
la excepción acotada prevista en la sección 8.

**Fuente de alcance:** docs/UI_FASE1.md, copia íntegra del archivo adjunto PROMPT_UI_Fase1_Repo.md.

**Fecha de línea base:** 8 de noviembre de 2026.
**Repositorio:** dperezflores/auditoria-adjudicaciones-directas.
**Commit de referencia de main:** f0329c4118def3459dec8b4da65024709ce91f60.
**Rama inmutable de referencia:** respaldo/pre-ui-fase1-20261108.
**Rama reservada para trabajo futuro:** ui/fase1-explorador.

## 1. Garantía de reversión y límite de alcance

El cambio es **exclusivamente de experiencia de usuario**. No altera reglas de auditoría ni el resultado de Gemini. La versión de referencia tiene CI exitosa en GitHub Actions (run 42553288901). El respaldo se creó en el commit exacto de main antes de incorporar este documento.

Tras la aprobación se permiten **únicamente los pasos de interfaz acordados**,
con commits pequeños en la rama `ui/fase1-explorador`:
- No modificar servicios de extracción, almacenamiento, clasificación ni caché.
- No cambiar requirements.txt, esquemas, prompts, base de Google Sheets ni datos de Drive.
- No realizar análisis con Gemini ni operaciones sobre expedientes reales.
- No fusionar nada a main. La aplicación publicada debe continuar sin cambios.

Si la Fase 1 no resulta satisfactoria, se descarta o revierte exclusivamente la rama/cambio de UI. La versión base sigue identificable por SHA y rama de respaldo. Antes de cualquier eventual fusión futura se revisará que no haya divergencias nuevas en main. NO usar un reset/force-push destructivo del historial ni revertir cambios ajenos posteriores.

## 2. Revisión del código y verificación de hallazgos del prompt

Se revisaron README.md, app.py, ui/expedientes.py, ui/resultados.py, ui/drive_explorer.py, services/analysis_catalog.py, services/drive_service.py, services/document_classifier.py, services/review_service.py, services/analysis_deletion.py, services/writer_lock.py, los cinco esquemas especializados, docs/INTERFAZ_OPERATIVA_EXPEDIENTES.md y las pruebas de tests/. Se corroboró el funcionamiento descrito en el documento principal, con las precisiones siguientes:

1. **Navegación.** app.py usa st.radio en la barra lateral para Expedientes, Resultados y Pruebas de adjudicación. También muestra el estado de Drive/Sheets/Gemini, sesión autorizada y Cerrar sesión. La autenticación se controla mediante security/app_access.py. Se preservará todo al mover las acciones a un encabezado.
2. **Carga y actualización.** _load_data() de ui/expedientes.py llama _refresh_inventory() al primer acceso y mediante Actualizar Google Drive; _refresh_inventory() sincroniza el inventario con Sheets usando get_writer_lock() y guarda ex_inventory, ex_status_tables y ex_synced_at en UTC. **Precisión:** esas variables no existen necesariamente si el usuario entra primero en Resultados; el encabezado debe mostrar "Carpeta por cargar / Sin revisar" sin disparar una sincronización invisible al navegar a otra pestaña. Las horas se mostrarán, cuando estén disponibles, en America/Mexico_City.
3. **Documentos y clasificación.** services/document_classifier.py identifica por nombre canónico y MIME: CONTRATO, PUC, DICTAMEN_AD, NOTIFICACION_AD, ORDEN_AD (PDF) y CATALOGO (XLSX). Tolera espacios justo antes de la extensión. Los nombres desconocidos se muestran POR_IDENTIFICAR, sin reasignación manual. ORDEN_AD es opcional para el diseño visual, pero mantiene su extractor y posibilidad de análisis.
4. **Estados.** file_states considera PDFs y CATALOGO.xlsx, no cualquier otro archivo; los valores incluyen Analizado, Pendiente, Parcial, Desactualizado, Revisar error y Sin registrar. folder_states utiliza esos mismos documentos compatibles: total, complete, partial y pending, etiquetando vacíos como "Sin PDF", aun si el texto más exacto sería "Sin documentos compatibles". Se propone adaptación **solo visual**, sin editar el motor de estados.
5. **Elección y tamaños.** render_expedientes admite un archivo, varios del mismo expediente o carpeta completa. Filtra según ENABLED_EXTRACTORS, tamaño PDF <= 50,000,000 bytes y XLSX <= 15,000,000 bytes; verifica registro activo, obra, checksum, tipo, intentos IN_PROGRESS/REQUIERE_REVISION y extracción vigente del mismo esquema. Calcula to_process, reused, blocked, needs_sync e ignored. Sólo los primeros 10 pasan al lote. El catálogo se importa sin IA. Se reproducirá exactamente esa elegibilidad, incluidos documentos no registrados y desactualizados.
6. **Análisis.** _analyze(obra, selection, model) procesa secuencialmente una sola obra y descarga el PDF completo o el XLSX completo. Dentro de get_writer_lock() despacha al extractor correspondiente; conserva los resultados en Sheets, devuelve bitácora y recarga el estado al terminar. No hay reintento automático. Se puede incluir callback de progreso opcional **solo tras aprobación** sin alterar despacho ni guardado.
7. **Eliminar análisis.** _render_delete_analysis requiere la palabra literal ELIMINAR, verifica versión/obra/archivo, llama delete_analysis bajo get_writer_lock() y no borra el PDF/Excel de Drive. Debe seguir disponible en la pantalla del documento.
8. **Datos mostrados.** _summarize_saved soporta CONTRATO-v2, PUC-v1, DICTAMEN_AD-v1, NOTIFICACION_AD-v1, ORDEN_AD-v1, CATALOGO-xlsx-v1, además de esquemas previos. Los valores extraídos siguen literales y los hechos suelen guardar pagina y evidencia. Las listas específicas ya existen (especialidades, personal, fundamentos, obligaciones, etc.). El panel nuevo debe consumir esos objetos sin modificar extracciones.
9. **Cotejo manual: discrepancia importante.** services/review_service.py implementa revisiones para campos de CONTRATO **histórico v1**, verificándolas contra DatosContrato y CAMPOS_CONTRATO. No valida automáticamente DatosContratoV2/CONTRATO-v2. Por ello NO es correcto ofrecer "Cotejar" para todos los contratos actuales sólo con un cambio de UI: podría fallar o asociar campos incorrectos. Recomendación: vista de sólo lectura en la Fase 1; la adaptación del servicio para contratos v2 requerirá otro alcance y autorización.
10. **Vista PDF.** El proyecto dispone de pypdf para lectura, pero no de un renderizador gráfico. No puede mostrar miniaturas reales de páginas sin una dependencia/herramienta nueva. Mientras no se apruebe pypdfium2 se muestra evidencia textual, página citada y Abrir en Drive.
11. **Pruebas y CI.** .github/workflows/ci.yml usa Python 3.12, compila módulos e instala pydantic, google-genai, openpyxl y pypdf, **sin instalar Streamlit**. Ejecuta python -m unittest discover -s tests -v. test_expedientes_ui.py y test_resultados_interaction.py verifican cadenas literales del despacho y del botón; test_widget_state.py previene asignaciones a claves de widgets. Estos tests son contratos de regresión que no deben eliminarse ni modificarse sin aprobación.
12. **Manual existente desactualizado.** docs/INTERFAZ_OPERATIVA_EXPEDIENTES.md todavía describe una etapa anterior de sólo PDFs/contratos y enumera límites distintos a los actuales. Se deberá corregir al implementar la UI, sin usarlo para cambiar la funcionalidad real.
13. **Capturas de referencia.** En este intercambio se recibió el prompt Markdown, pero **no las capturas visuales de las tres pantallas aprobadas** a las que el prompt se refiere. Para verificar fidelidad visual pantalla por pantalla harán falta esas capturas. No se inventarán diseños ni se declarará paridad visual sin ellas.

## 3. Implementación fiel al diseño aprobado (después de autorización)

### A. Tema y navegación
- Centralizar tokens, paleta, tipografía IBM Plex Sans/Mono y mapeos de estados en ui/theme.py y ui/styles.css. Mantener respaldo system-ui y monospace; si Google Fonts no carga, conservar legibilidad.
- Sustituir sólo el bloque CSS de app.py por CSS propio usando clases de st.container(key=...), sin depender de clases internas generadas por Streamlit.
- Encabezado con AuditorIA, tres opciones Expedientes / Resultados / Pruebas de adjudicación, estado de servicios, raíz de Drive y revisión reciente, cuenta autorizada y Cerrar sesión.
- Se prefiere st.segmented_control para minimizar cambios del router, o st.navigation(position="top") con las tres páginas equivalentes si la revisión local muestra que conserva la selección. Se mantiene entrada predeterminada Expedientes y el código funcional intacto de Resultados/Pruebas.

### B. Pantalla 1 — Explorador
- Panel izquierdo de obras (~320 px), búsqueda por carpeta o nombre de archivo, filtros Todas / Con pendientes / Completas, selección por obra y árbol expandible de PDFs/XLSX compatibles con rutas internas.
- Panel derecho con migas de pan, obra enfocada, link Drive, tarjetas de 5 documentos esperados (Contrato, PUC, Catálogo, Dictamen AD y Notificación AD), ORDEN AD opcional sólo cuando exista. "Falta" es una tarjeta informativa, jamás un archivo seleccionable.
- Filas de documentos con tamaño real, estado, fecha Drive y acciones: Analizar, Ver datos, Revisar o indicación de renombrar/no compatible. Otros archivos se listan en gris sin enviarlos a Gemini.
- Barra inferior fija con cantidad de documentos seleccionados y acciones. Casillas de obra marcan solamente documentos elegibles, no la totalidad indiscriminada.
- Vista móvil o estrecha: columnas apiladas y barra inferior que no tape el contenido.
- El número de documentos por carpeta se basa en el universo actual de PDFs + CATALOGO.xlsx, no en cantidad fija de tarjetas esperadas.

### C. Pantalla 2 — Confirmación y progreso
- Diálogo nativo @st.dialog con lote de máximo 10, total de MB de PDF enviados completos, catálogos sin IA y documentos excluidos con motivos claros. No agregar casillas de autorización ni "Volver a analizar".
- Reusar la misma función _analyze para conservar los límites, el modelo, el bloqueo y la escritura. Barra de progreso por documento y resumen final; los problemas dicen "Revisar", no reintento automático.
- Si se autoriza selección de varias obras, agrupar los mismos documentos elegibles de cada una y recorrer las obras en orden dentro del límite global de 10; esto necesita aprobación expresa y pruebas de equivalencia.
- La interrupción en Streamlit puede dejar una extracción no confirmada: no simular una función "Detener" que prometa cancelación transaccional segura. Explicar que los documentos ya guardados permanecen y los inciertos requieren revisión.

### D. Pantalla 3 — Documento con evidencia
- Navegación Expedientes / Obra / Tipo y parámetro doc en st.query_params, siempre validando que el doc pertenezca a la obra activa/autorizada.
- Datos literales por campo y su fuente/página; listas estructuradas debajo del formulario. Mantener compatibilidad con versiones antiguas y los resultados del catálogo en Expedientes.
- Columna de evidencia a la izquierda con fragmento destacado y página cuando exista, y campos a la derecha, filtrables por Todos / No localizados. No crear coordenadas ni cuadros encima del PDF.
- Sin autorización para renderizar páginas: sólo texto de evidencia y link Abrir en Drive. Con autorización para pypdfium2: renderizar una página a la vez en memoria, cacheada por id/md5/página, sin guardar PDF en disco.
- Cotejo manual de campos sólo si se aprueba y se resuelve primero la incompatibilidad real entre review_service y contrato-v2; de otro modo, lectura sola y ninguna escritura a RevisionesContrato.

## 4. Adaptaciones inevitables (sin cambios funcionales)

| Elemento visual pedido | Situación y adaptación |
|---|---|
| Imagen de página del PDF | No disponible sin nuevo motor. Esperar decisión 9.1; por defecto, fragmento textual + Abrir en Drive. |
| "Volver a analizar" | No existe. Omitir y explicar eliminación previa de análisis vigente. |
| "Reintentar" al fallar | Sustituir por "Revisar", nunca retry automático. |
| Páginas del archivo | DocumentRecord no tiene cantidad de páginas. Mostrar MB y "PDF completo" hasta abrir el documento. |
| Casilla de obra semimarcada | Checkbox estándar no ofrece indeterminate fiable; añadir guion visible y contador sin alterar selección. |
| Tipo documental desconocido | No añadir selector; renombrar en Drive y pulsar Actualizar Google Drive. |
| Carpeta con cero documentos analizables | folder_states conserva "Sin PDF"; interfaz podrá aclarar "Sin documentos compatibles". |
| Barra fija | CSS mediante key estable, padding inferior para evitar cubrir filas y alternativa fluida en móvil. |
| Carpeta raíz en barra superior antes de abrir Expedientes | Mostrar estado "Por cargar"; no sincronizar Drive silenciosamente desde otras pestañas. |
| Cotejo manual en contrato-v2 | No es viable sólo desde UI con review_service actual. Se propone diferir hasta autorización expresa de servicio/versión. |
| Revisión visual contra capturas | No se adjuntaron las capturas referidas en el prompt. Queda pendiente tenerlas para validar fidelidad. |

## 5. Inventario de archivos propuestos

**Ya creados, en rama aislada:**
- docs/UI_FASE1.md — original íntegro del prompt.
- docs/UI_FASE1_ADAPTACION.md — este documento, antes de programar.

**Por crear tras aprobación:**
- ui/theme.py — constantes visuales, estados y agrupaciones de campos.
- ui/styles.css — estilos de aplicación, árbol y barra fija.
- ui/components.py — encabezado, píldoras, indicadores y barra de selección.
- ui/analysis_dialog.py — confirmación y presentación de progreso.
- ui/document_view.py — pantalla por documento y evidencias.
- services/selection_rules.py — **módulo nuevo de lógica pura** sin Streamlit, si se autoriza expresamente la excepción de crear este módulo bajo services/. NO altera el código de extracción ni Sheets.
- tests/test_selection_rules.py y otros tests nuevos de representación/estado sin importar Streamlit.

**Por modificar, y solamente después de autorización:**
- app.py — encabezado y navegación superior; conserva la seguridad y el pie actual.
- ui/expedientes.py — nueva presentación, mismas reglas, mismas llamadas de analizador y eliminación.
- .streamlit/config.toml — únicamente tokens visuales de theme.
- docs/INTERFAZ_OPERATIVA_EXPEDIENTES.md — actualizar el manual a la realidad.
- requirements.txt — **sólo si** se aprueba añadir pypdfium2 en decisión 9.1.

**No tocar en esta fase:** ui/resultados.py salvo su invocación existente desde app.py; pantalla de Pruebas de adjudicación; services de análisis, extracción, caché, esquemas, sincronización y borrado; archivos de datos o documentos de Drive; pruebas existentes. Si una pantalla exige ampliar servicios, registrar la necesidad y pedir autorización antes de modificarla.

## 6. Estrategia de regresión y equivalencia

1. Registrar línea base y pruebas en CI; baseline main f0329c... pasó tests.
2. Conservar EN ui/expedientes.py las garantías inspeccionadas por tests existentes, entre ellas: código de extractor por tipo, pending_attempt, get_writer_lock, botón key ex_analyze, disabled=disabled, llamada explícita a _analyze, confirmación ELIMINAR y ausencia de selección manual del tipo.
3. Antes de retirar el bloque antiguo de selección, construir tests puros que comparen dos implementaciones sobre los mismos inventarios simulados: eligibles, reused, blocked, ignored, needs_sync, exceso de tamaño, límite 10 y tipo no identificado.
4. No asignar directamente valores a st.session_state de claves ya asociadas a widgets. La UI tendrá claves ex_ estables por obra/documento.
5. Mantener la exclusión de CATALOGO.xlsx de Gemini, envío del PDF completo, reutilización, bloqueos, controles de checksum y scopes por obra.
6. Verificar casos de cero obras, sólo catálogo, orden opcional, PDF renombrado, obra parcial, extracción antigua, error no confirmado y dos obras con documentos homónimos.
7. Mantener todas las pruebas existentes sin editarlas ni borrarlas. Agregar pruebas nuevas; CI sigue ejecutándose sin Streamlit.
8. Revisión visual con capturas simuladas/Playwright sólo si existe soporte y capturas originales, sin consultar Drive ni Gemini reales.
9. Implementar por pasos A → B → C → D. Tras cada paso, ejecutar pruebas y actualizar manual. No fusionar automáticamente al terminar.

## 7. Cuatro decisiones que debe aprobar el usuario

### 9.1. Imagen de página del PDF
**Opciones:** A) mostrar imágenes con pypdfium2 (autoriza dependencia nueva y descarga verificada al abrir el documento); B) evidencia textual + Abrir en Drive, sin dependencias.
**Recomendación para una Fase 1 de riesgo mínimo:** B. Si el visor es indispensable para el diseño aprobado, seleccionar A expresamente.

### 9.2. Cotejar campos en la UI
**Opciones:** A) solo lectura en esta fase; B) solicitar fase separada de compatibilidad contractual v2 antes de habilitar Cotejar (requiere autorización para cambiar servicios y tests).
**Recomendación:** A. El actual review_service valida DatosContrato v1; sería incorrecto presentarlo como cotejo de los 16 campos v2.

### 9.3. Selección y análisis de varias obras
**Opciones:** A) sólo una obra a la vez, mismo comportamiento actual; B) varias obras por ejecución, hasta 10 documentos en total, con nuevo coordinador y pruebas.
**Recomendación:** A por mínima alteración. B puede hacerse en esta fase **sólo si se autoriza explícitamente**.

### 9.4. Barra lateral
**Opciones:** A) eliminar y ubicar servicios/cuenta totalmente en el encabezado; B) dejar colapsada (sin navegación) para indicadores complementarios.
**Recomendación:** B durante la migración, manteniendo los indicadores visibles y acceso a Cerrar sesión.

## 8. Pendientes de aprobación y condición de inicio

Se requiere:
1. Aprobación expresa de docs/UI_FASE1_ADAPTACION.md y permiso para empezar **Paso A**.
2. Respuesta para las cuatro decisiones 9.1–9.4.
3. Aprobación explícita de crear services/selection_rules.py (excepción acotada a la prohibición de cambiar services/), en caso de incluir el Paso B.
4. Capturas de las tres pantallas del diseño aprobado, si se espera fidelidad visual y no solo aproximación a las descripciones del prompt.

**La aprobación para iniciar el Paso A ya fue recibida.** Quedan pendientes la verificación visual de las capturas y una aprobación posterior expresa antes de fusionar a `main`. Durante el Paso A no se añaden dependencias ni se cambia ningún servicio.
