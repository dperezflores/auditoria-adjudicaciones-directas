# Prueba AD-06 — Límites de adjudicación (2021–2026)

## Ámbito

Prueba de gabinete por importe. Se incorpora únicamente en la pestaña **Pruebas de adjudicación** de la app original (`main`). **No sustituye** las cinco pruebas AD inicialmente previstas y **no modifica** la app de pruebas visual (`ui/fase1-explorador`).

**Alcance temporal del piloto:** todas las evaluaciones municipales se realizan con el municipio **León, Guanajuato**, fijado en el motor de la prueba. No se requiere que el objeto del contrato mencione León y el usuario no selecciona un municipio. La conclusión queda condicionada a que el expediente realmente pertenezca al universo de obras de León. Este alcance debe revisarse antes de utilizar AD-06 para otros municipios.

## Fuente única de los montos

La app consulta mediante la cuenta de servicio de Google Drive, **solo lectura**, la ruta:

`[drive.root_folder_id]/Recursos/ADJUDICACION_LIM_2021_2026.xlsx`

Solo abre las hojas **Base municipal** (276 filas: 46 municipios x seis años) y **Base estatal** (seis ejercicios, 2021–2026). La app comprueba estructura, existencia, huella MD5, límite 2 MB, continuidad a centavos, integridad por ejercicio y duplicados. Cada resultado muestra la tabla, decreto, municipio/grupo (cuando aplica), artículo estatal, clave y URL de fuente. No se copia la tabla a GitHub ni a Sheets.

## Campos usados (contrato v2)

| Campo extraído | Uso |
| --- | --- |
| `legislacion_citada` | Identificación preliminar de la LOPYSRM local o norma federal |
| `fuente_financiamiento` | Distinguir municipal o estatal solo si es explícito; fondos mixtos/federales requieren revisión |
| `obra_servicio` | Se conserva como dato contractual, pero **no determina el municipio del piloto**: se aplica León. |
| `fecha_firma_contrato` | Ejercicio inicial (año de firma); validar si el procedimiento inició en otro año |
| `modalidad_adjudicacion` | Clasificación AD / licitación simplificada / licitación pública |
| `monto_contrato` | Importe original; conversión a monto sin IVA solo si se conoce tratamiento |

Los contratos en versiones antiguas sin esos campos quedan como **Requiere revisión**. Los registros de extracción vigentes se leen del portafolio actual sin consultar nuevamente a Gemini.

## Determinación de la tabla

- LOPYSRM de Guanajuato **y** recursos municipales explícitos -> **Base municipal**, índice año + **León fijo**; el grupo histórico A/B/C se lee desde el catálogo para ese mismo año.
- LOPYSRM de Guanajuato **y** recursos estatales explícitos -> **Base estatal**, índice año.
- Ley federal, fondos federales/mixtos, legislación o fuente indeterminada -> **Requiere revisión**. Las excepciones normativas y el régimen efectivo no se presumen.
- La interfaz permite confirmar temporalmente **año, base normativa y tratamiento del importe**. El municipio se muestra como **León (fijo)**, sin selector. Estas confirmaciones **no modifican** la extracción, el contrato, la tabla de Drive ni la evaluación automática general; el detalle marca las confirmaciones manuales.

## Resultados

1. **Dentro del límite:** AD con importe sin IVA <= máximo AD, o LS dentro de intervalo.
2. **Excede el límite:** AD o LS sobrepasan su máximo ordinario.
3. **Procedimiento más competitivo:** se eligió LS/LP para un importe inferior al comienzo de su rango ordinario. **No es automáticamente irregularidad**.
4. **Dentro del rango de LP:** el monto alcanza LP mínimo; la tabla no establece máximo de licitación pública.
5. **Requiere revisión:** falta cualquier dato esencial (año, régimen, modalidad, monto comparable sin IVA) o falta la fila de **León** para el ejercicio en el histórico.

Los límites e importes son **sin IVA**. Cuando el contrato dice IVA incluido se divide el importe entre 1.16 y redondea a centavos; cuando indica sin IVA no se transforma. Si el tratamiento no consta no se asume y la prueba queda pendiente de confirmación.

### Detección del IVA en la cláusula contractual (contrato-prompt-v5)

El extractor sigue guardando los **16 campos literales de contrato-v2** sin alterar la estructura de `DatosContratoV2`. Para el campo `monto_contrato`, el nuevo prompt exige una cita de `evidencia` que **contenga el importe total y la aclaración fiscal**, siempre que aparezcan en la misma cláusula. La cita conserva página y texto literal, incluso si «IVA INCLUIDO» aparece después de la cantidad en letras o de «55/100 M.N.».

AD-06 clasifica el IVA primero desde `monto_contrato.valor` y después, cuando sea necesario, desde `monto_contrato.evidencia`. Solo admite la segunda ruta cuando esa cita **incluya el mismo importe numérico exacto** que el campo; una mención fiscal de un anticipo u otro monto no basta. Si la cita contradice el valor, o si solo aparece «IVA 16 %» sin aclarar inclusión, se mantiene **Por confirmar**. La decisión derivada puede consultarse en la ficha de extracción, la columna «IVA del importe» de AD-06 y el detalle por contrato (con fuente y página).

**Ejemplo de control:** importe contractual $1,542,830.55, con «IVA INCLUIDO» en la misma cita: $1,542,830.55 ÷ 1.16 = **$1,330,026.34** sin IVA. Se trata de un cálculo de comparación de importes, no de una validación fiscal integral.

**Compatibilidad de caché:** `contrato-prompt-v5` tiene una nueva versión de prompt y, si el auditor solicita una nueva extracción, se genera una clave de caché distinta. No se reanalizan los PDFs guardados de forma automática ni se reemplazan las respuestas antiguas. Los contratos anteriores con citas útiles pueden aprovechar la nueva detección **sin consumir Gemini**; los que no conservaron evidencia suficiente seguirán necesitando cotejo o una nueva extracción explícitamente solicitada.


## Importante para la auditoría

**Este cálculo NO determina cumplimiento legal integral ni es una observación automática.** El año de firma puede diferir del año del procedimiento o asignación. Hay que comprobar el régimen normativo efectivo, la fuente y origen presupuestario, excepciones de contratación, convenios, participación competitiva y fraccionamiento. Las bases son una fuente de referencia; los enlaces a decretos incluidos en el archivo requieren cotejo contra su texto publicado vigente.

La aplicación genera un CSV del listado automático y muestra un comparativo de la obra seleccionada con límites y fuente. No se crean escrituras en Google Sheets ni resultados definitivos de auditoría.

## Pruebas automáticas

`python -m unittest discover -s tests -v`

Incluye las pruebas de bordes por centavo, vigencia 2021–2026, cambios de grupo por ejercicio, lectura del XLSX, detección de régimen, recurso mixto/federal, importe ambiguo, IVA, **León fijo** aun sin municipio en el objeto contractual y vigencia de contrato-v2.
