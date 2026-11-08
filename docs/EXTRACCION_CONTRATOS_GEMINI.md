# Extracción de contratos con Gemini — Etapa preparatoria

## Estado a la fecha

✅ Estructura Pydantic en `services/contract_schema.py`.
✅ Prompt versionado en `services/contract_prompt.py`.
✅ Clave de caché SHA-256 en `services/extraction_cache.py`.
✅ Pruebas sin llamadas a Google o Gemini.

**Todavía no se descarga el PDF para IA, no se llama a Gemini, no se almacenan extracciones, no hay botón activo de análisis ni costos generados por este código.**

## Qué se pretende extraer del primer contrato escaneado

- Número de contrato.
- Nombre de la obra.
- Contratista.
- Fecha de firma.
- Fecha de inicio.
- Fecha de término.
- Monto con IVA.
- Porcentaje de anticipo.

Cada campo tendrá `valor`, `pagina` y `evidencia`. La ausencia o ilegibilidad se expresa como `null`; el sistema marca valores sin página/cita como pendientes de revisión. No se inferirán los datos que no estén visibles.

La extracción no es observación de auditoría ni sustituye el cotejo humano. El PDF ficticio es nuestro único material de prueba inicial.

## Evitar analizar dos veces

La clave de reutilización será SHA-256 de:
- contenido real de los bytes del PDF,
- modelo elegido,
- versión del prompt,
- versión del esquema y
- tipo de documento.

Renombrar o mover el archivo **sin alterar sus bytes** no cambia esta clave. Un cambio de PDF o de reglas de extracción crea una clave diferente y permitirá reanalizar. El ID de Google Drive se guardará como vínculo al documento, separado de la clave.

**Pendiente:** implantar un almacenamiento persistente de extracciones (por ejemplo, pestaña `Extracciones` de Google Sheets), operaciones recuperables ante fallos y bloqueo contra ejecuciones concurrentes. Definir esto antes de habilitar la llamada de IA.

## Siguiente acción de configuración: Google AI Studio

1. Ir a https://aistudio.google.com/apikey .
2. Si no aparece el proyecto `auditoria-ad-piloto`, abrir **Projects → Import projects**, seleccionarlo e importarlo.
3. Comprobar que el proyecto se muestra en AI Studio.
4. Crear una clave de acceso API del proyecto **solo cuando la integración esté lista**; no pegarla en GitHub, chat o capturas.
5. Configurar esa clave exclusivamente en Streamlit Secrets durante el paso de integración.

Documentación oficial:
- https://ai.google.dev/gemini-api/docs/api-key
- https://ai.google.dev/gemini-api/docs/document-processing
- https://ai.google.dev/gemini-api/docs/structured-output
- https://ai.google.dev/gemini-api/docs/pricing

## Privacidad, facturación y alcance

La API de Gemini tiene condiciones diferentes en nivel gratis y nivel de pago. La documentación de precios indica que el nivel gratuito puede usar solicitudes para mejorar productos, mientras que el nivel pagado presenta otro tratamiento. **Solo usar PDF enteramente ficticios en este piloto**, incluso si la app exige login. Los expedientes de auditoría reales requerirán aprobación institucional, análisis de confidencialidad, controles de retención/uso de datos, presupuesto y seguridad.

La facturación de API es independiente de cualquier suscripción de chat a Gemini. No activar automáticamente el gasto ni hacer llamadas sin pulsar expresamente **Analizar**.

## Próximo desarrollo técnico

1. Conectar cliente Gemini y obtener el PDF únicamente de la cuenta Drive autorizada.
2. Comprobar tamaño, MIME y contenido; normalizar escaneos y limitar recursos.
3. Buscar en caché **antes** de llamar a Gemini.
4. Solicitar resultado estructurado y validarlo con Pydantic.
5. Guardar resultado, modelo, versión, SHA-256, uso y referencias a páginas.
6. Mostrar datos y evidencia con opción de revisión manual.
7. Probar que una segunda solicitud para el mismo contenido use caché sin costo de IA.
