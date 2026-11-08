# Dashboard del piloto: datos registrados frente a datos simulados

## Estado

El `Dashboard general` incorpora una sección `Seguimiento del piloto · Google Sheets`
que aparece **solo para usuarios autenticados** que tengan la sección
`[storage]` ya configurada en Streamlit Secrets.

La sección no cambia Google Drive, no escribe en Google Sheets y **no
envía ningún archivo a Gemini**. Lee las pestañas `Obras`, `Documentos`,
`Extracciones` y `DatosContrato` exclusivamente al pulsar
**Actualizar indicadores desde Google Sheets**.

Los gráficos originales de la demostración siguen separados bajo
**Gráficos de demostración** y utilizan solo datos ficticios en memoria.

## Qué muestra

1. Total de obras y documentos activos según IDs de Drive guardados.
2. Número de contratos con campos almacenados asociados a una versión
   vigente de documento.
3. Número de contratos pendientes de cotejo humano (aún no hay módulo
   de validación profesional).
4. Relación por carpeta de obra y tabla con ocho valores de contrato.
5. Advertencia de recuperaciones parciales, sin páginas ni citas
   conservadas.

El estado `REQUIERE_REVISION` de `Extracciones` con datos disponibles
en `DatosContrato` se presenta como
`Recuperado parcialmente · pendiente de cotejo`. Nunca como
`Analizado y aprobado`.

Si `Documentos.estado_procesamiento` indica
`Modificado desde el último análisis`, los valores antiguos no
se presentan como información actual del PDF.

## Prueba actual esperada

Sobre el piloto ficticio ya registrado:
- 2 obras activas.
- 1 PDF activo.
- 1 contrato con valores recuperados.
- 1 contrato pendiente de cotejo.

Estos indicadores pueden cambiar cuando se actualice Google Sheets.
El botón de actualización solo consulta la base: no realiza llamadas
a Gemini ni facturación por tokens.

## Siguiente etapa propuesta

Añadir un flujo de cotejo documental por campo: registrar página, cita,
valor corregido o confirmado, revisor, fecha, estado de evidencia y
trazabilidad de modificaciones, sin cambiar los registros históricos
de respuestas de IA. Solo después se habilitarán estados
`Validado por auditor` y cálculos de cumplimiento sobre evidencia
contrastada.
