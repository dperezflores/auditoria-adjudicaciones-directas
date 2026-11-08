# Etapa 2 — Extracción especializada PUC-v1

## Objetivo y alcance
El archivo `PUC.pdf` se reconoce por su nombre estándar al sincronizar
Google Drive, sin inspeccionar su contenido para clasificarlo. Al pulsar
**Analizar PUC con IA**, Gemini lee exclusivamente ese PDF y extrae sus
valores literales. Se conservan páginas, evidencias y especialidades;
**NO se ejecutan todavía las cinco pruebas de adjudicación**.

Los archivos `CONTRATO.pdf`, `DICTAMEN_AD.pdf`, `NOTIFICACION_AD.pdf`,
`ORDEN_AD.pdf` y `CATALOGO.xlsx` no tienen extractor activado en esta
etapa, aunque sí aparezcan registrados. CATALOGO.xlsx se leerá con Python
posteriormente y no se envía a Gemini.

## Campos del PUC
El esquema `puc-v1` conserva estos 18 valores con página y evidencia:

1. `contratista`
2. `rfc`
3. `numero_registro_puc`
4. `estado_registro`
5. `fecha_validacion`
6. `fecha_impresion`
7. `vigencia_desde`
8. `vigencia_hasta`
9. `representacion_legal`
10. `capital_contable`
11. `ejercicio_financiero`
12. `total_activo`
13. `representante_tecnico`
14. `profesion_representante_tecnico`
15. `cedula_profesional`
16. `resultado_evaluacion`
17. `domicilio_fiscal`
18. `registro_patronal`

Los valores son transcripciones sin cambiar mayúsculas, puntuación,
importes o fechas. Los campos que el PDF no acredita permanecen
`null`. No se presume que la fecha de validación sea el inicio de
vigencia ni que el representante técnico del PUC sea el responsable
designado en el contrato.

## Especialidades
`especialidades` es una lista de registros con:
- `categoria`: categoría de especialidad;
- `actividad`: trabajos o actividad específica;
- `tipo_marcado`: OBRA, PROYECTO, SUPERVISIÓN, ESTUDIO, si figura;
- `aportada_por`: persona o empresa a quien se atribuye;
- `pagina` y `evidencia`: respaldo literal en el archivo.

No se comparan todavía las especialidades con el catálogo ni se
concluye si son suficientes para una obra.

## Persistencia, identificación y caché
Se agregó la pestaña **DatosPUC** en
[AuditorIA_AD_Master_Piloto](https://docs.google.com/spreadsheets/d/1xvipXJCI4G6RWpqsPCU6FKVqpWSgaWvPYY7j5MNJdGM/edit).
Incluye `cache_key`, `obra_id`, `documento_id`, 18 valores
literales, `especialidades_json`, `observaciones_json` y
`extraido_utc`.

La hoja **Extracciones** conserva el JSON completo, páginas y evidencias,
versión de prompt y esquema, conteo de tokens y estado de la solicitud.
La clave de caché depende de bytes del PDF, modelo, versión de prompt
`puc-prompt-v1`, esquema `puc-v1` y tipo `PUC`.

La aplicación registra una reserva **antes** de invocar Gemini.
Los resultados completos se reutilizan sin volver a consultar el
modelo. Si una solicitud falla, queda registrada para revisión y
no se reintenta automáticamente: así evitamos cargos duplicados.

## Prueba en Streamlit
1. Abre **Expedientes** y pulsa **Actualizar Google Drive**.
2. Selecciona una obra con `PUC.pdf`. La columna Tipo documental debe
   mostrar `PUC`.
3. En **Extracción documental**, elige ese PUC (o carpeta completa; se
   filtrarán los archivos de otros tipos). Verifica que la tabla indique
   `PUC-v1 disponible`.
4. Pulsa **Analizar 1 PUC con IA**. Esta acción puede consumir tokens de
   la API; no se llama a Gemini por abrir la pantalla.
5. Después, en **Consultar análisis guardado**, elige el mismo `PUC.pdf`.
   Revisa el listado de 18 campos y la tabla de especialidades, incluidas
   sus páginas y evidencias.
6. Abre la pestaña **DatosPUC** en Sheets para verificar que existe una
   fila del mismo documento y obra.
7. Si el documento ya está analizado, el botón no volverá a procesarlo
   automáticamente. Si falla el guardado, revisa Extracciones/DatosPUC
   antes de autorizar cualquier reanálisis.

## Limitaciones
El sistema no verifica si un archivo llamado `PUC.pdf` realmente es
un PUC: se utiliza la convención de nombres aprobada. Gemini puede
cometer errores de transcripción. El resultado no acredita autenticidad,
capital suficiente, vigencia completa ni especialidad idónea.

## Etapas posteriores
1. Extractor de `DICTAMEN_AD`.
2. Extractor de `NOTIFICACION_AD` y `ORDEN_AD` según disponibilidad.
3. Extractor de `CONTRATO` usando los campos v2 ya definidos.
4. Lectura directa de `CATALOGO.xlsx` y exclusión lógica de conceptos
   fuera del catálogo originalmente contratado.
5. Cruces y pruebas automáticas de auditoría, con fundamentos jurídicos
   y valoración preliminar separados de la evidencia literal.
