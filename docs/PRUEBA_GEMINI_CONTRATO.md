# Extracción de contrato simulado con Gemini — primera prueba

## Estado

La integración utiliza la clave ya configurada en `[gemini].api_key` de **Streamlit Secrets**. No se almacena ni imprime la clave en GitHub.

La aplicación no invoca Gemini al abrirse o al pulsar **Actualizar Google Drive**. Solo lo hará si el auditor confirma y presiona **Analizar contrato con IA (o reutilizar caché)**.

**Restricción temporal:** la primera prueba solamente admite el PDF ficticio de "Obra 001 - Prueba ficticia", ID de Drive `1zGZjRXxLtaNmmMW-0kGOU9W6m7Wr1YA2`, cuyo nombre debe comenzar por `Contrato_SIMULADO_`. No se habilitarán documentos reales en esta fase.

## Configuración

Streamlit Secrets debe contener las secciones que ya funcionan:
- `[auth]` y `[access]`: acceso a la interfaz.
- `[drive]` y `[gcp_service_account]`: lectura del PDF desde Google Drive.
- `[storage]`: escritura en la hoja maestra.
- `[gemini]`: clave API.

Opcionalmente define el modelo:

```toml
[gemini]
api_key = "VALOR_PRIVADO_EXISTENTE"
model = "gemini-3.5-flash-lite"
```

**Si [gemini] ya existe, NO agregues otra sección: agrega solo la línea `model = "gemini-3.5-flash-lite"` si quieres fijarlo explícitamente.** El valor anterior es solo ejemplo. El código utiliza ese modelo por defecto.

Google lo describe como un modelo compatible con PDF y extracción estructurada de costo relativo bajo. El acceso a modelos y las tarifas dependen del proyecto y del nivel de servicio. Comprueba las condiciones aplicables antes de procesar información real.

Fuentes:
- https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite
- https://ai.google.dev/gemini-api/docs/document-processing
- https://ai.google.dev/gemini-api/docs/structured-output
- https://ai.google.dev/gemini-api/docs/pricing

## Qué hace el análisis

1. Solo se habilita si la cuenta inicia sesión y está autorizada.
2. El auditor selecciona la obra y el PDF **ficticio**.
3. Acepta que la solicitud a Gemini podría generar consumo/cargos.
4. Al pulsar el botón, vuelve a leer el archivo desde la cuenta de servicio.
5. Comprueba MIME PDF, pertenencia a carpeta autorizada, límite de 8 MB, tamaño y huella MD5.
6. Calcula SHA-256 de los bytes reales del documento.
7. Construye la clave de caché con SHA-256 + modelo + versión de prompt + versión de esquema + tipo de documento.
8. Consulta la pestaña `Extracciones` **antes de realizar una llamada a Gemini**.
9. Si hay resultado `COMPLETADO`, lo muestra sin volver a solicitar análisis.
10. Si no existe, guarda un registro `EN_PROCESO` y realiza **una sola solicitud**.
11. Valida la respuesta con Pydantic; guarda JSON estructurado y estadísticas de tokens, y crea fila en `DatosContrato`.
12. Actualiza `Documentos` con el estado y referencia al análisis.
13. Si ocurre un error después de reservar, se marca `REQUIERE_REVISION` y no se reintenta automáticamente.

## Datos del contrato

`numero_contrato`, `nombre_obra`, `contratista`, `fecha_firma`,
`fecha_inicio`, `fecha_termino`, `monto_con_iva` y
`porcentaje_anticipo`.

Cada dato tiene: `valor`, `pagina` y `evidencia`. Los faltantes se guardan como `null`, no como valores inventados. Los datos sin evidencia requieren revisión humana.

## Verificación inicial

1. Inicia sesión en https://auditoria-adjudicaciones-directas.streamlit.app/
2. Entra en **Google Drive (piloto)** y pulsa **Actualizar Google Drive**.
3. Selecciona `Obra 001 - Prueba ficticia`.
4. Baja a **Extracción de datos del contrato con Gemini**.
5. Selecciona el PDF `Contrato_SIMULADO_...`.
6. Marca la casilla que confirma el uso de documento ficticio y autoriza una posible solicitud con costo.
7. Pulsa **Analizar contrato con IA (o reutilizar caché)**.
8. Si el proveedor y la clave funcionan, debe aparecer una tabla con los ocho campos y evidencia. Confirma en Sheets las pestañas `Extracciones` y `DatosContrato`.
9. Pulsa el mismo botón por segunda vez: debe mostrar **Resultado recuperado de Google Sheets** sin otra llamada al modelo.

## Seguridad y limitaciones

- El repositorio GitHub puede seguir público, pero no contiene claves; la app exige login. No se deben añadir expedientes reales ni habilitar el análisis a archivos ajenos al ensayo ficticio.
- Las citas son propuestas de la IA, no evidencias verificadas automáticamente. El auditor debe contrastarlas con el PDF y validar antes de emitir conclusiones.
- Google Sheets carece de garantías transaccionales y bloqueos distribuidos. Se usa un cerrojo local dentro de un solo proceso Streamlit. Se necesita un backend transaccional o un escritor único real antes de habilitar concurrencia entre réplicas.
- Si Gemini respondió pero el guardado falla, podría existir consumo sin resultado confirmado. Por ello los registros inciertos bloquean el reintento automático; el usuario debe comprobar la base antes de forzar otra solicitud.
- `DatosContrato` conserva campos de extracción pero no sustituye un dictamen ni una revisión legal.
- Aún no se ha ejecutado una prueba real desde Streamlit con la clave del usuario. La disponibilidad del modelo y la exactitud de los datos se verificarán cuando el usuario ejecute la prueba.
