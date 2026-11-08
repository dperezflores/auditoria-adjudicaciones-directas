# Cotejo manual de contratos — piloto AuditorIA

## Estado

Implementado en GitHub y habilitado en la sección **Dashboard general**,
bajo la tabla del contrato seleccionado. No se llama a Gemini ni se altera
la extracción original de la IA.

La hoja maestra contiene la nueva pestaña **RevisionesContrato**, que usa
un registro de eventos append-only. Cada corrección añade una fila con:
identificador de revisión, fecha UTC, obra, PDF, clave de versión del análisis,
nombre del campo, decisión, valor IA, valor cotejado, página, evidencia,
justificación y correo del usuario autenticado.

## Regla por campo

- **Confirmado**: el valor cotejado debe coincidir exactamente con el de IA,
  y debe registrarse número de página y fragmento de evidencia visible.
- **Corregido**: el valor cotejado debe ser distinto, indicar página y
  evidencia, y proporcionar justificación de la corrección.
- **No localizado**: dejar valor, página y evidencia vacíos, e incluir
  una justificación. El dato queda documentado como no localizado, no como
  hallazgo de incumplimiento.

Los ocho campos iniciales son: número de contrato, nombre de la obra,
contratista, fecha de firma, fecha de inicio, fecha de término, monto con IVA
y porcentaje de anticipo.

## Seguridad y trazabilidad

- Debe haber inicio de sesión con una cuenta autorizada en Streamlit.
- El servidor toma el correo del usuario autenticado, no un campo editable.
- Antes de guardar se comprueba que obra, documento y clave de caché
  corresponden a una extracción vigente en Sheets y que el documento está
  activo. Si el PDF se modificó, se bloquea el cotejo de la versión anterior.
- Cada revisión se añade como evento nuevo; no se sobrescriben
  `Extracciones`, `DatosContrato`, ni los cotejos anteriores.
- Se comprueba el `revision_id` antes de añadir para evitar duplicados
  ante reenvío; se mantiene un bloqueo local en un proceso Streamlit.
- La página y la cita son registradas por una persona: el sistema
  **no verifica automáticamente** que el texto sea auténtico ni que la
  página corresponda. Esa validación es responsabilidad del auditor.
- Los expedientes reales y el procedimiento formal de aprobación
  necesitan autorización institucional y un backend transaccional para
  múltiples usuarios/instancias.

## Cómo probar un campo

1. Abre https://auditoria-adjudicaciones-directas.streamlit.app/
   e inicia sesión.
2. Selecciona `Dashboard general` y pulsa
   **Actualizar indicadores desde Google Sheets**.
3. Elige `Obra 001 - Prueba ficticia`.
4. Baja a **Cotejo manual por campo**.
5. Usa **Abrir PDF original en Google Drive** y coteja visualmente.
6. Elige **Número de contrato**. Verás el valor IA `SIM-AD-001/2026`.
7. Si coincide, selecciona **Confirmado**, conserva el valor, indica
   la **página real** y transcribe un fragmento que lo respalde.
8. Pulsa **Guardar cotejo del campo** una sola vez.
9. Revisa el avance del contrato: debe pasar de **0/8** a **1/8**.
10. Consulta en Sheets la pestaña `RevisionesContrato`: deberá aparecer
    exactamente una fila nueva, sin cambios en las pestañas de IA.

**No inventar número de página ni evidencia.** Si el contrato no muestra
el valor, elige `No localizado` con justificación.

## Pendientes

- Firma o aprobación final de un supervisor distinto al revisor.
- Comprobación técnica de integridad del PDF contra el momento de cotejo
  (el piloto usa la última sincronización de Drive).
- Control transaccional multiinstancia y política de permisos por rol.
- Exportación formal de papeles de trabajo.
- Cotejos de PUC, dictamen, notificación y las pruebas normativas.
