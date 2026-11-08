# Diagnóstico de ClientError en el primer análisis Gemini

**Incidente:** el contrato ficticio fue enviado a Gemini, pero la API respondió `ClientError`. El registro `Extracciones` quedó en `REQUIERE_REVISION`; la pestaña `DatosContrato` permanece sin registros. No se confirmó ninguna extracción ni se puede inferir un cobro a partir del mensaje.

## Primer paso: comprobación sin generación

Desde `Google Drive (piloto)`, después de iniciar sesión y seleccionar `Obra 001 - Prueba ficticia`, pulse **Diagnosticar acceso a Gemini (sin analizar PDF)**.

Este botón usa `client.models.get(model=...)`, solamente solicita metadatos del modelo; **no descarga ni envía el PDF, no llama a `generate_content` y no genera tokens**.

Posibles resultados:

- `MODEL_VISIBLE`: la clave puede consultar ese modelo; la falla anterior probablemente ocurrió en los parámetros, el esquema, las cuotas o la generación propiamente dicha. No demuestra que generación funcione.
- `HTTP_400`: parámetros inválidos.
- `HTTP_401`: clave no aceptada.
- `HTTP_403`: permisos del proyecto o restricciones de clave.
- `HTTP_404`: modelo no disponible para ese proyecto/endpoint.
- `HTTP_429`: límite o cuota.
- `CONNECTION_ERROR`: problema de conexión no clasificado.

Los mensajes completos del proveedor no se muestran ni se almacenan, para evitar exposición de datos privados.

**No marcar «Autorizar reintento explícito» hasta verificar el resultado.**

## Posible corrección de compatibilidad a evaluar

El código de extracción actual incluye `temperature=0`. Google recomienda omitir parámetros como `temperature`, `top_p` y `top_k` con Gemini 3.x. Si el diagnóstico es correcto y el primer rechazo corresponde a HTTP 400, eliminaremos esa opción y versionaremos la configuración antes de una nueva prueba autorizada.

Documentación:
- https://ai.google.dev/gemini-api/docs/whats-new-gemini-3.5
- https://ai.google.dev/gemini-api/docs/generate-content/api-errors
- https://googleapis.github.io/python-genai/

## Registro previo y consumo

Se preserva la fila de fallo como rastro auditable. No borrar, editar a mano ni reenviar el PDF repetidamente. Si corresponde iniciar una nueva solicitud después de corregir el código, se registrará con versión nueva y consentimiento explícito.

Nunca compartir `api_key`, `client_secret`, `cookie_secret` ni valores de `gcp_service_account`.


## Actualización después del diagnóstico de metadatos

La consulta de metadatos del modelo fue satisfactoria, pero no revela cuál
fue el código HTTP del primer `ClientError`. Por ello no se puede atribuir
ese error con certeza a parámetros, cuotas o facturación.

**Cambios publicados:**
- Se eliminó el parámetro personalizado `temperature=0` en `services/gemini_service.py`.
- Las respuestas de error de la API registrarán solo el código HTTP y el
  status estándar, sin el mensaje completo ni secretos.
- Se versionó la extracción como `contrato-prompt-v2`; esto crea otra
  clave de caché para una configuración de extracción distinta. El intento
  antiguo `REQUIERE_REVISION` permanece intacto.

**Próxima prueba:** solo con contrato ficticio, después de una nueva
confirmación del usuario. Mantener desmarcado **Autorizar reintento
explícito**. Una nueva solicitud puede causar consumo/cargos.

Si aparece `HTTP_400_FAILED_PRECONDITION`, revisar requisitos de la
cuenta y facturación en Google AI Studio. Si aparece
`HTTP_400_INVALID_ARGUMENT`, revisar los campos del esquema y request.
Si `HTTP_403`, revisar permisos; si `HTTP_429`, límites de uso.

No repetir solicitudes automáticamente.


## Corrección adicional tras el segundo HTTP 400

La solicitud `contrato-prompt-v2` también fue rechazada con
`HTTP_400_INVALID_ARGUMENT`, pese a que la clave sí podía consultar
los metadatos del modelo. Esto **no demuestra** por sí solo qué parámetro
exacto rechazó Google.

La investigación detectó que se enviaba directamente un esquema Pydantic
anidado (`ExtraccionContrato`) mediante `response_schema`. Google
documenta que los esquemas complejos pueden producir HTTP 400.

**Cambios realizados en v3:**
- Se sustituyó `response_schema=ExtraccionContrato` por un esquema JSON
  compacto en `response_json_schema`, con una sola lista de campos.
- Se mantiene `application/json`, sin temperatura personalizada.
- Los ocho datos mantienen `valor`, `pagina` y `evidencia`.
- La validación Pydantic se aplica **después de recibir** la respuesta.
- Se rechazan campos inesperados, valores duplicados y páginas inválidas.
- La configuración utiliza `contrato-prompt-v3`, que crea una clave de
  caché nueva, sin borrar los registros fallidos de v1/v2.

Se añadieron pruebas sin llamadas a Gemini, incluida la construcción local
de la configuración del SDK `google-genai`. Esto disminuye riesgos pero
**no garantiza** que el endpoint remoto acepte la siguiente solicitud.

**Próxima comprobación:** únicamente contrato simulado; una sola solicitud
bajo confirmación del auditor, con `Reintentar` desmarcado. Si vuelve a
aparecer HTTP 400, detener las pruebas de generación y evaluar un
diagnóstico más fino sin seguir consumiendo llamadas repetidas.

Referencia: https://ai.google.dev/gemini-api/docs/structured-output
