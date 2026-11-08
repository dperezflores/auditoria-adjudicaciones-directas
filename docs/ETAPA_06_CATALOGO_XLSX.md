# Etapa 6 — CATALOGO.xlsx sin consumo de Gemini

## Formato reconocido
El archivo debe llamarse CATALOGO.xlsx y tener el tipo MIME XLSX. Puede proceder de un prefiniquito, pero solo se importa el catálogo original.
El lector busca en las primeras 100 filas encabezados equivalentes a Clave, Descripción, Unidad, Inicial y Precio U. No usa Total Aut., Excedente, Acumulado Estimado ni Ejercido como cantidad original.

Los conceptos de capítulos FUERA DE CATÁLOGO, presupuestos adicionales y renglones con Inicial igual a cero no se incorporan al catálogo contractual.

## Datos guardados
Por concepto: identificador de obra y archivo, hoja y fila original, capítulo, clave, descripción, unidad, cantidad inicial, precio unitario e importe original (Inicial × Precio U., sin IVA).

Las claves de concepto se pueden repetir en diferentes capítulos o en varios renglones de un mismo capítulo. El identificador de registro es la hoja y la fila del Excel, junto con el documento; no se fusionan cantidades por clave y el resumen informa cuántas claves se repiten. Esta repetición no es por sí sola una irregularidad.

La nueva pestaña DatosCatalogo se crea automáticamente en Google Sheets cuando se importa por primera vez un XLSX. Un resumen compacto queda en Extracciones bajo el esquema catalogo-xlsx-v1, usando el modelo lógico lector-local-xlsx. No se envía el archivo a Gemini.

La importación utiliza caché versionada; no duplica filas cuando el archivo ya fue procesado. Si Sheets no confirma todas las escrituras, se registra REQUIERE_REVISION y se bloquea el reintento automático. El flujo de eliminación auditada también retira las filas de este documento en DatosCatalogo.

## Prueba operativa
1. Guarda el prefiniquito como CATALOGO.xlsx dentro de la carpeta de obra en Drive y presiona Actualizar Google Drive.
2. En Expedientes > Extracción documental, selecciona obra y archivo.
3. Comprueba que se muestre el extractor catalogo-xlsx-v1 y el botón Importar catálogo sin IA.
4. Pulsa Importar. Si faltan columnas inequívocas, la aplicación no guarda datos parciales.
5. Consulta el resumen y las primeras 300 filas desde Consultar análisis guardado. El detalle completo queda en DatosCatalogo.
6. En Resultados, elige el contrato de esa obra para visualizar el resumen del catálogo.

## Alcance de auditoría
La columna Inicial es una referencia de la cantidad originalmente contratada **según el prefiniquito**. Para considerar la información definitivamente acreditada debe cotejarse con el catálogo/presupuesto firmado y, cuando corresponda, con los convenios. La cifra Inicial × Precio U. es un cálculo preliminar, no equivale automáticamente al monto firmado del contrato.

El archivo original se conserva intacto en Google Drive. No se invoca Gemini ni se determina automáticamente ninguna irregularidad.
