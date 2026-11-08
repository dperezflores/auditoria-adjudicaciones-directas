# Etapa 4 — Extracción NOTIFICACION_AD-v1

## Alcance
La aplicación reconoce `NOTIFICACION_AD.pdf` por el nombre y formato
en Google Drive. La clasificación no verifica el contenido; por tanto,
debe nombrarse el archivo correcto antes de analizarlo. En **Expedientes**,
Gemini solo se invoca cuando el auditor pulsa el botón de análisis.

**Esta etapa es exclusivamente de extracción.** No se calculan días
hábiles, fechas límite ni se emiten pruebas de cumplimiento.

## Datos principales (21)
`numero_notificacion`, `fecha_emision`, `fecha_recepcion_acuse`,
`destinatario`, `contratista`, `representante_contratista`,
`registro_puc_contratista`, `nombre_obra`, `localidad`,
`modalidad_adjudicacion`, `monto_adjudicado`,
`dependencia_emisora`, `unidad_administrativa`,
`referencia_dictamen`, `fecha_dictamen_referido`,
`autoridad_emisora`, `cargo_autoridad`,
`codigo_formato`, `revision_formato`,
`fecha_revision_formato`, `fuente_financiamiento`.

Cada campo tiene texto literal, página física del PDF y fragmento
de evidencia. No se convierten montos ni fechas. La **fecha de emisión**
nunca se copia al campo **fecha de recepción** salvo que exista evidencia
independiente inequívoca de recepción en esa fecha.

## Grupos complementarios
1. **Supervisores:** función (externa, coordinación interna,
   supervisión interna u otra), nombre, cargo, registro PUC de supervisor,
   página y evidencia. El registro PUC del supervisor externo no se
   equipara al registro del contratista.
2. **Obligaciones y plazos:** instrucción literal, plazo literal,
   evento que inicia su cómputo, condición, destinatario,
   fundamento citado, página y evidencia. El sistema no obtiene
   ni infiere el día final del plazo.
3. **Fundamentos:** normas y artículos expresamente citados en la
   notificación, con evidencia literal y página.
4. **Acuse aparente:** presencia visual (visible, no visible o
   indeterminada), fecha de recepción claramente legible si existe,
   página y nota visual. La presencia de una firma no autentica
   el acuse ni demuestra fecha de recepción válida.
5. **Observaciones:** advertencias documentales o de legibilidad.

## Persistencia y seguridad de caché
Los campos literales se registran en la pestaña
[DatosNotificacionAD](https://docs.google.com/spreadsheets/d/1xvipXJCI4G6RWpqsPCU6FKVqpWSgaWvPYY7j5MNJdGM/edit)
(30 columnas). El JSON íntegro, con evidencias, permanece en
`Extracciones` junto a tokens, modelo y versiones
`notificacion-ad-v1` y `notificacion-ad-prompt-v1`.

La caché depende de bytes del PDF, modelo, esquema, prompt y tipo.
Una extracción completa se reutiliza sin repetir la llamada a Gemini.
Una extracción incierta queda bloqueada; debe inspeccionarse antes
de permitir una nueva llamada.

El botón **Eliminar análisis guardado de este archivo** también
admite notificaciones: borra únicamente los resultados del
documento confirmado y deja constancia en Historial. No borra
el PDF original de Drive. Reanalizar después puede generar cargos.

## Prueba manual
1. Dentro de Google Drive, coloca la **notificación verdadera**
   con nombre exacto `NOTIFICACION_AD.pdf` en la carpeta de su obra.
2. Abre **Expedientes** y pulsa **Actualizar Google Drive**.
3. Selecciona la obra y el archivo `NOTIFICACION_AD.pdf`.
4. Confirma que la tabla muestre `notificacion-ad-v1`.
5. Pulsa **Analizar 1 documento(s) con IA** (solicitud con posible consumo).
6. En **Consultar análisis guardado**, selecciona la notificación.
7. Revisa especialmente que **fecha de emisión** y **recepción/acuse**
   sean campos distintos, y que los registros PUC de
   **contratista** y **supervisor externo** no se confundan.
8. Comprueba las obligaciones, plazos literales, evento de inicio,
   las páginas y las evidencias.
9. Verifica una fila nueva en `DatosNotificacionAD` y que los
   análisis existentes del PUC y dictamen continúan intactos.

## Qué falta
Los extractores `CONTRATO`, `ORDEN_AD` y `CATALOGO`
permanecen pendientes de implementación. Para `CATALOGO.xlsx`
se prevé lectura estructurada con Python, sin envío a Gemini.
Las cinco pruebas de auditoría y los cruces se implementarán después,
como procesos separados de extracción.
