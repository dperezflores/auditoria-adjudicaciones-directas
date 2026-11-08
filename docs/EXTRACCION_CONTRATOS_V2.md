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
En `Expedientes`, elige obra, alcance y archivo(s). En `Plantilla de
extracción` puedes seleccionar:
- **Automático:** identifica por nombre convencional si se trata de
  contrato y aplica la nueva plantilla. Nombres abreviados como
  `CNT_DIR_CNT.pdf` también se identifican como contrato.
- **Contrato completo (16 campos):** fuerza el extractor especializado,
  incluso si un contrato fue analizado anteriormente con plantilla
  general o v1. Esto **puede consumir otra solicitud**, pero preserva el
  resultado antiguo y solo se ejecuta con el botón Analizar.
- **Ficha documental general:** análisis genérico para PUC, dictámenes,
  oficios y otros PDFs, sin suplantar el extractor contractual.

Cuando un documento ya tiene un análisis v2 completo no se reanaliza.
Si hay un v2 incierto, no se reintenta automáticamente.

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
3. Elige **Contrato completo (16 campos)** y revisa la selección antes de
   pulsar Analizar; es una nueva solicitud que puede generar consumo.
4. Una vez terminado, abre Resultados, pulsa Actualizar datos y selecciona
   la fila para ver ficha, personas y legislación.
5. Comprueba en `DatosContratoV2` que los campos textuales y el JSON de
   personas correspondan al nuevo análisis.

No se ha enviado ningún documento real a Gemini durante la implementación
de esta versión.
