# Prueba AD-03 — Vigencia histórica del PUC (León)

## Propósito

Prueba independiente de CC-01, en la tercera pestaña de **Pruebas de adjudicación**. Determina preliminarmente si el periodo de inscripción/refrendo acreditado del Padrón Único de Contratistas cubre **la fecha efectiva de asignación** y **la firma del contrato**. Las excepciones legales y la aplicabilidad de normas se revisan por el auditor; no se genera una observación automática.

## Reglas

- Se utiliza el PUC activo y analizado que pertenece a la misma `obra_id`, con `documento_id` y `cache_key` exactos; duplicados o PUC modificados no se aceptan.
- Se usa la fecha efectiva de asignación asentada por el auditor con referencia verificable. La fecha de emisión del dictamen AD se muestra únicamente como referencia preliminar; la fecha de firma no la sustituye.
- Se comparan inicio y fin del registro o refrendo. Sin inicio, **no se usa la fecha de validación como sustituto**.
- La **fecha de impresión** del PUC es un metadato, no condición para ser vigente. La fecha de validación tampoco es el inicio automático.
- Los intervalos fuera de fecha quedan como «Periodo aportado no acredita vigencia»: deben buscarse refrendos históricos, posibles suspensiones y excepciones, sin afirmar automáticamente que el contratista no estaba inscrito.
- Si la cédula informa suspensión o cancelación, se requiere identificar desde cuándo surtió efectos; no proyectar retrospectivamente un estado posterior.
- Una comparación favorable se denomina «Vigencia documental compatible (preliminar)» y no sustituye cotejo de autoridad.

## Revisiones manuales

Desde AD-03 o CC-01 el auditor puede registrar el mismo historial de revisión en la pestaña adicional `RevisionesPUC` de Google Sheets. Los registros son **append-only** y conservan `revision_id`, UTC, correo del auditor, obra, versión exacta de contrato y PUC, fecha efectiva de asignación, periodo histórico, estado, capital históricamente registrado, fecha de su registro, fuente, referencia y conclusión profesional. La revisión más reciente se aplica en memoria a las dos pruebas, siempre que sus identificadores documentales sigan coincidiendo.

El formulario requiere fuente, identificación del soporte y explicación; para capital histórico exige **importe y fecha de actualización oficial** juntos. Los campos de capital pueden quedar vacíos si el cotejo solo valida vigencia. Conclusión del auditor y clasificación automática se muestran por separado.

La pestaña `RevisionesPUC` se crea únicamente con el **primer guardado autorizado**, no por consultar una prueba. No se actualiza ni reemplaza el contenido original de `Extracciones`, `DatosPUC`, `DatosContratoV2` o documentos Drive. Guardar requiere sesión autorizada y el cerrojo de escritura del proceso Streamlit.

## Límites

- No hay consulta histórica automática al padrón oficial; la evidencia documental histórica debe aportarse.
- Cédulas con un único periodo no prueban la ausencia de refrendos distintos.
- Los resultados son preliminares; la revisión jurídica de las excepciones, autenticidad y vigencia normativa sigue a cargo del auditor.
- No se llama a Gemini al consultar o guardar una revisión, ni se altera AD-06.
