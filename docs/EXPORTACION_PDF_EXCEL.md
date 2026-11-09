# Exportación documental PDF de AuditorIA

En **Resultados** aparece el botón **Descargar base documental PDF (Excel)**. La descarga se genera **en el momento del clic** desde Google Sheets. No utiliza ni envía archivos a Gemini, no incluye CATALOGO.xlsx y no modifica las hojas de datos originales.

## Relaciones entre hojas

- `OBRAS`: `ID_OBRA` (número de registro) e `ID_OBRA_DRIVE` (ID permanente de la carpeta de Drive).
- `DOCUMENTOS`: una fila por PDF activo (analizado o pendiente) con los mismos identificadores de obra y `ID_DOCUMENTO` (ID de archivo de Drive).
- `CONTRATOS`, `PUC`, `DICTAMEN_AD`, `NOTIFICACION_AD` y `ORDEN_AD`: una fila por PDF con una extracción especializada completa y vigente, enlazada por `ID_OBRA` e `ID_DOCUMENTO`.
- `ESPECIALIDADES`: múltiples filas por PUC; la columna `N` conserva el orden original.
- `EVIDENCIAS`: una fila por campo citado, con su página y evidencia literal.
- `DETALLES`: conserva datos anidados (motivaciones, fundamentos, instrucciones, cargos, firmantes y observaciones) en formato JSON, con su sección y número de elemento.
- `OTROS_PDF`: documentos con esquemas anteriores o no especializados. Sus campos y datos quedan en `EVIDENCIAS` y `DETALLES` cuando existe una extracción general.

Las filas en `OBRAS` llevan un número `ID_OBRA` calculado del **orden histórico de alta en Google Sheets**. Se cuenta también cada obra archivada o sin PDF para no renumerar las obras anteriores conforme aparecen nuevos expedientes. Es importante **no reorganizar ni eliminar manualmente las filas de la tabla Obras** si se necesita conservar dicho número. La identidad estable e independiente de reordenamientos siempre es `ID_OBRA_DRIVE`, por eso el Excel exporta ambas. Para unir las tablas se recomienda utilizar `ID_OBRA_DRIVE` o `ID_OBRA` y, cuando se necesitan registros individuales, `ID_DOCUMENTO`.

## Actualización

1. Cuando se incorporen documentos o carpetas, ve a Expedientes y pulsa **Actualizar Google Drive**.
2. Analiza los PDF nuevos, si procede.
3. Desde Resultados pulsa **Descargar base documental PDF (Excel)**. La app vuelve a consultar los registros de Google Sheets en el propio clic, sin depender de los filtros o del estado anterior del dashboard.
4. El archivo descargado es una nueva fotografía de la base **al momento de la descarga**. No existe sincronización bidireccional entre el archivo que tengas descargado y el sistema. Descarga uno nuevo cuando se agreguen o se actualicen documentos.

El Excel contiene resultados documentales preliminares. El hecho de compartir `ID_OBRA` **no acredita** por sí solo que un PUC corresponda al contratista de la obra; el módulo de cruce conserva la verificación de identidad por número PUC y RFC.

El lector especializado de Resultados reconoce las versiones `puc-v1`, `dictamen-ad-v1`, `notificacion-ad-v1` y `orden-ad-v1`. Las extracciones históricas distintas siguen visibles en `OTROS_PDF` o a través de sus evidencias, sin trasladarlas automáticamente a un esquema incompatible.
