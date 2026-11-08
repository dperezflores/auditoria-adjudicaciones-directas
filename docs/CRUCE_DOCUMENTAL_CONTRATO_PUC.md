# Resultados: cruce documental de la obra (Contrato ↔ PUC)

## Alcance
La pestaña **Resultados** conserva el listado de contratos (16 columnas) y
la ficha interactiva. Debajo añade **Cruce documental de la obra
seleccionada**, con dos pestañas:
- **Contrato ↔ PUC:** comparación del contratista, número de registro PUC,
  RFC, representante legal, representante técnico y relación temporal entre
  fecha de firma del contrato y fecha de vencimiento extraída del PUC.
- **Otros documentos y análisis:** listado de PDFs complementarios del mismo
  expediente, su estado de extracción y, cuando existe, el resumen y los
  campos literales con páginas y evidencia.

No hay nuevas llamadas a Gemini al abrir Resultados, seleccionar contrato,
comparar PUC o consultar los demás documentos.

## Relación y seguridad
1. Los documentos se relacionan por su `obra_id` en las tablas `Obras` y
   `Documentos`. No se relacionan por nombres parecidos ni por la posición
   en Drive.
2. Solo se consideran obras y documentos activos; únicamente se muestran
   resultados de extracción cuyo `cache_key` coincide con el
   `resultado_id` del documento actual. Extracciones de otros documentos,
   obras o versiones modificadas no se reutilizan.
3. Si hay varios PUC en el mismo expediente, se ofrecen para selección,
   ordenados por coincidencia preliminar de RFC y registro; el usuario debe
   escoger el que corresponda.
4. La igualdad de RFC y registro PUC es un cotejo de textos extraídos;
   una coincidencia no equivale a autenticidad del registro ni validez
   de la constancia. El mismo expediente no garantiza que ambos documentos
   pertenezcan a la misma empresa.
5. La fecha de vencimiento posterior a la firma **no acredita por sí misma**
   que el registro PUC estuviese vigente desde la firma. Faltan comprobación
   del inicio de vigencia, reglas de registro y documento original.
6. El capital y la especialidad del PUC se muestran como datos extraídos
   sin establecer automáticamente que sean suficientes ni compatibles con
   el contrato. Las reglas normativas se incorporarán en Pruebas.

## Primer expediente verificado en la base de datos
La obra de Cerrito de Jerez contiene:
- Un contrato v2 completo.
- Una constancia PUC analizada previamente mediante el esquema
  `documento-schema-v1`, con nombre, RFC y registro coincidentes con los
  extraídos del contrato.
- Un dictamen técnico registrado, pendiente de análisis.

El PUC contiene capital contable `$300,000.00`, especialidad
`OBRA DE INFRAESTRUCTURA VIAL TIPO B` y fecha de vigencia hasta el
`9 de abril de 2026`. Todos son valores *propuestos por la extracción*,
sujetos a cotejo con el PDF.

## Extensibilidad
- Los nuevos tipos documentales se incorporan a la pestaña de documentos
  como fichas con resumen, campos y advertencias, si se registraron con
  `documento-schema-v1`.
- Si el documento fue procesado con `contrato-v2`, se muestran los campos
  efectivamente obtenidos. Esto **no sustituye** una extracción específica
  del PUC, que en el futuro deberá incluir de manera consistente capital,
  especialidad, fechas completas y situación registral.
- Los PDFs no procesados aparecen como `Sin análisis`, sin valores falsos.

## Comprobación en Streamlit
1. Abre Resultados y pulsa **Actualizar datos**.
2. Selecciona la obra de Cerrito de Jerez en la tabla de contratos.
3. Baja a **Cruce documental de la obra seleccionada**.
4. En **Contrato ↔ PUC** revisa los tres identificadores coincidentes y
   los datos de capital, especialidad, representación técnica y vencimiento.
5. En **Otros documentos y análisis** abre la ficha de `PUC .pdf` para
   consultar sus campos y evidencias y observa el dictamen pendiente.
6. Selecciona Parque Uyepac en la tabla: debe cambiar el expediente y
   desaparecer el PUC de Cerrito de Jerez, sin mezclar las obras.
