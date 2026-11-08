# Etapa 3 — Extracción de DICTAMEN_AD-v1

## Objetivo
Extraer datos documentales del dictamen de autorización/procedencia de
adjudicación directa sin valorar todavía cumplimiento legal.

El archivo se reconoce exclusivamente como `DICTAMEN_AD.pdf`.
El nombre identifica su tipo por la convención aprobada. No se hace
una verificación previa de contenido para clasificarlo.
La extracción de Gemini **solo comienza al pulsar Analizar**.

## Campos literales (19)
`numero_dictamen`, `fecha_emision`, `dependencia_emisora`,
`unidad_administrativa`, `contratista`,
`representante_contratista`, `registro_puc`, `nombre_obra`,
`localidad`, `modalidad_adjudicacion`, `monto_asignado`,
`fecha_probable_inicio`, `plazo_ejecucion`, `autoridad_firmante`,
`cargo_autoridad`, `codigo_formato`, `revision_formato`,
`fecha_revision_formato`, `fuente_financiamiento`.

Cada campo conserva texto literal, página y evidencia. Si no aparece
se registra `null`. Se distingue expresamente la **fecha de emisión**
del dictamen de la **fecha de revisión del formato**. No se convierte
el folio del dictamen en número de contrato ni se infiere la fuente
de financiamiento.

## Listas estructuradas
- **Fundamentos:** norma, artículos, texto normativo reproducido
  cuando exista, página y fragmento literal.
- **Motivaciones:** tema (experiencia, especialidad, vigencia PUC,
  mejores condiciones, justificación, selección, capacidad u otro),
  afirmación literal, soporte mencionado, página y evidencia.
- **Documentos soporte:** documento citado por el dictamen, finalidad,
  página y evidencia. La cita no demuestra que el soporte esté en el expediente.
- **Firma aparente:** apreciación visual separada (visible, no visible
  o indeterminada), nunca autenticación ni presunción de validez.
- **Observaciones:** advertencias de lectura, no hallazgos.

## Base y caché
Nueva pestaña `DatosDictamenAD` con 28 columnas en
[AuditorIA_AD_Master_Piloto](https://docs.google.com/spreadsheets/d/1xvipXJCI4G6RWpqsPCU6FKVqpWSgaWvPYY7j5MNJdGM/edit).

`Extracciones` guarda JSON completo, evidencia y páginas, con
`version_esquema=dictamen-ad-v1`,
`version_prompt=dictamen-ad-prompt-v1` y tipo `DICTAMEN_AD`.
Los resultados del `PUC-v1` y contratos previos no se reescriben.
Al volver a consultar un PDF ya procesado con la misma versión y modelo
se reutiliza la caché; un intento incierto queda bloqueado para evitar
un doble consumo de Gemini.

## Prueba manual (solicitud con consumo potencial)
1. En **Expedientes**, pulsa **Actualizar Google Drive**.
2. Selecciona `00_591_25_ParqueUyepac` (si sigue disponible).
3. Elige **Un archivo** y `DICTAMEN_AD.pdf`.
4. Comprueba en la tabla que diga extractor `dictamen-ad-v1`.
5. Pulsa **Analizar 1 documento(s) con IA** solo si autorizas la
   solicitud. Al abrir/consultar la pantalla no se envían documentos.
6. En **Consultar análisis guardado** selecciona el dictamen.
   Deberás encontrar campos literales, fundamentos, motivaciones,
   soportes y nota de firma aparente; al final **Ver PDF en Drive**.
7. Comprueba una fila nueva en `DatosDictamenAD` y en `Extracciones`.
8. Confirma que el PUC analizado previamente sigue disponible.

## Alcance actual
PUC-v1 y DICTAMEN_AD-v1 están disponibles. Aún **no** está activo el
extractor para contrato, notificación, orden o catálogo ni se realizan
las cinco pruebas o cruces normativos en esta etapa.
