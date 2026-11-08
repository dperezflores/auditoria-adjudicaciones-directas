# Etapa 5 — Extracción de ORDEN_AD-v1

## Objetivo
Extraer de `ORDEN_AD.pdf` los elementos literales de la orden de
adjudicación directa, sin mezclar sus resultados con el dictamen, la
notificación, el PUC o el contrato. Este documento es **opcional**:
la ausencia de la orden no equivale automáticamente a incumplimiento.

La identificación documental se hace por nombre exacto y MIME en Drive:
`ORDEN_AD.pdf` (sin verificación previa de contenido). Gemini solo se
invoca al pulsar **Analizar**. Cambiar de pestaña o actualizar Drive no
genera consumo de IA.

## 22 campos literales
`numero_orden`, `fecha_emision`, `contratista`,
`representante_legal`, `nombre_obra`, `localidad`,
`tipo_adjudicacion`, `monto_adjudicado`,
`dependencia_emisora`, `area_emisora`,
`fundamento_adjudicacion`, `numero_contrato_referido`,
`fecha_contrato_referido`, `direccion_supervision`,
`supervisor_principal`, `telefono_supervisor`,
`autoridad_firmante`, `cargo_firmante`,
`codigo_formato`, `revision_formato`,
`fecha_revision_formato`, `fuente_financiamiento`.

Todos se conservan literalmente con página y evidencia. Si no existe
el campo, se utiliza `null`: no se infiere un número de contrato
a partir del consecutivo de adjudicación; no se interpreta la fecha de
revisión del formato como emisión de la orden ni como firma del contrato.

## Información complementaria
1. `personal_designado`: persona de supervisión o coordinación,
   su función, dirección, teléfono, página y fragmento literal.
2. `instrucciones`: obligación, plazo literal, evento de inicio,
   condición, consecuencia expresada, destinatario, página y evidencia.
   Ejemplo de rubros a identificar solo cuando aparezcan:
   presentación de calendario, documentación para iniciar,
   coordinación con supervisión y autorización previa de conceptos
   extraordinarios. No se calculan fechas límite.
3. `fundamentos`: ley y artículos citados, nunca complementados
   con fuentes externas.
4. `documentos_referidos`: nombres y finalidad de documentos
   mencionados en la orden. Una referencia no significa que el
   documento exista en el expediente.
5. `firma_aparente`: indicador visual preliminar (visible,
   no visible o indeterminada); no autentica firmas ni acredita
   notificación.
6. `observaciones`: ambigüedades documentales, no hallazgos.

## Persistencia y caché
La pestaña **DatosOrdenAD** del
[archivo maestro de AuditorIA](https://docs.google.com/spreadsheets/d/1xvipXJCI4G6RWpqsPCU6FKVqpWSgaWvPYY7j5MNJdGM/edit)
tiene 32 columnas. Se guarda el literal de los 22 campos y se
serializan las listas como JSON. La hoja **Extracciones** conserva
el JSON integral, evidencias, páginas, versión `orden-ad-v1`,
prompt `orden-ad-prompt-v1`, modelo, tokens y estado.

La caché combina bytes del PDF, tipo, prompt, esquema y modelo.
La extracción completa se reutiliza sin llamar nuevamente a Gemini;
los intentos inciertos quedan bloqueados.

La opción **Eliminar análisis guardado de este archivo** también
abarca este tipo documental: elimina únicamente su ficha y la
caché asociada, registra el evento en Historial, deja el PDF en Drive
y permite reanalizarlo voluntariamente. Reanalizar puede tener costo.

## Prueba de usuario
1. Si existe orden de adjudicación en el expediente, cárgala a la
   subcarpeta correspondiente como `ORDEN_AD.pdf`.
2. En **Expedientes**, pulsa **Actualizar Google Drive**.
3. Selecciona la obra y el documento `ORDEN_AD.pdf`.
4. Verifica que el extractor indicado sea `orden-ad-v1`.
5. Pulsa **Analizar 1 documento(s) con IA** (puede consumir tokens).
6. En **Consultar análisis guardado**, selecciona la orden.
7. Comprueba el consecutivo, la fecha de emisión, obra, contratista
   y monto, junto con la tabla de instrucciones y plazos literales.
8. Verifica que la fecha de revisión del formato permanezca
   diferenciada de la fecha del documento.
9. Comprueba la fila en `DatosOrdenAD` y que no se modificaron
   las extracciones guardadas de otros tipos.

## Próximo paso
Quedan pendientes el extractor de `CONTRATO.pdf` con los 16 campos
aprobados y la lectura estructurada de `CATALOGO.xlsx` sin Gemini.
Después se incorporarán las cinco pruebas cruzadas del procedimiento.
