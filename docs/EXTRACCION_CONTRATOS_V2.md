# Extracción de contratos v2 — literal, participantes y legislación

## Objetivo
El extractor especializado `Contrato completo (16 campos)` conserva el texto
exacto visible en el PDF sin alterar mayúsculas, minúsculas, comas, puntos,
acentos, importes o fechas. No corrige OCR automáticamente ni normaliza el
texto en el registro. Cada campo mantiene `valor`, `pagina` y `evidencia`.

## Datos que se capturan
1. Número de contrato
2. Obra o servicio
3. Tipo de contrato
4. Contratista (nombre o razón social)
5. Número de registro PUC
6. RFC
7. Representante legal
8. Representante técnico
9. Modalidad de adjudicación
10. Monto del contrato
11. Fecha de inicio contractual
12. Fecha de término contractual
13. Fecha de firma del contrato
14. Anticipo
15. Fuente de financiamiento
16. Legislación citada en el contrato (literal)

Adicionalmente se guarda una **lista independiente** de personas participantes:
nombre, cargo o carácter, a quién representan, página y cita literal de
evidencia. No inventa nombres ausentes o cargos que no estén expresados.

La clasificación **`ambito_normativo_preliminar`** se calcula de forma
conservadora a partir de una ley o reglamento expresamente citado. Los
valores posibles incluyen Federal, Estatal, Municipal, varias normas citadas
o No determinado. **No es un dato transcrito**, sino una etiqueta derivada.
No decide automáticamente qué límites de adjudicación aplicaron: falta
correlacionar ejercicio, naturaleza de los recursos, ente, excepciones y
normas vigentes en la fecha relevante.

## Persistencia, caché y compatibilidad
- `Extracciones`: conserva JSON íntegro con valores, páginas, citas y lista
  de participantes; `version_prompt=contrato-prompt-v4` y
  `version_esquema=contrato-v2`.
- `DatosContratoV2`: nueva pestaña de 23 columnas; 16 campos se guardan
  literalmente, y las personas y observaciones en JSON, además de la
  clasificación preliminar, ID, fecha y huella de caché.
- `DatosContrato` y las extracciones históricas v1 se conservan y no
  se reescriben automáticamente.
- El mismo archivo + versión del modelo/prompt/esquema reutiliza la caché.
  Una nueva versión de extracción requiere solicitud explícita del usuario.
- Las solicitudes incompletas quedan bloqueadas contra reintentos automáticos.

## Cómo analizar nuevos documentos y actualizar anteriores
En `Expedientes`, elige obra, alcance y los PDF. Ya no existe selector
de plantilla: **el botón Analizar siempre emplea los 16 campos del contrato
(v2)** y extrae además la lista de personas participantes.

Si un documento fue analizado con una versión anterior, al pulsar Analizar
se puede obtener la versión ampliada mediante una nueva solicitud a Gemini
y se conserva el resultado histórico. Si ya tiene una extracción v2
completa, se omite para no volver a generar cargos. Los intentos v2
incompletos no se reintentan automáticamente.

Un PDF que no es un contrato también puede examinarse con este esquema,
pero los datos contractuales no encontrados quedan vacíos; una referencia
aislada a una empresa o RFC no basta para integrarlo al dashboard de contratos.

La sección `Consultar análisis guardado` muestra los valores persistentes
y, debajo de ellos, el botón **Ver PDF en Drive** para abrir el documento
original.

## Resultados interactivos
La tabla de contratos usa selección de fila y `on_select='rerun'`. Al
seleccionar una obra se actualiza automáticamente debajo la ficha con:
- **Datos contractuales:** 16 textos literales sin normalización.
- **Personas participantes:** lista tabular con roles y páginas.
- **Legislación y recursos:** cita jurídica literal, fuente de
  financiamiento literal y ámbito preliminar destacado como derivado.
- **Evidencias del PDF:** páginas y fragmentos originalmente devueltos
  por IA para cotejo documental.

Los contratos antiguos continúan visibles con sus campos disponibles;
no se rellenan los campos nuevos mediante conjeturas.

## Prueba sugerida sin costo de IA
1. Abre Resultados y confirma que se conservan los contratos ya extraídos.
2. Entra a Expedientes, selecciona un PDF ficticio o autorizado.
3. Comprueba que se indique **Extracción contractual · 16 campos**.
   Solo pulsa Analizar si deseas generar o ampliar la extracción;
   la llamada a Gemini puede generar consumo.
4. Una vez terminado, abre Resultados, pulsa Actualizar datos y selecciona
   la fila para ver ficha, personas y legislación.
5. Comprueba en `DatosContratoV2` que los campos textuales y el JSON de
   personas correspondan al nuevo análisis.

No se ha enviado ningún documento real a Gemini durante la implementación
de esta versión.
