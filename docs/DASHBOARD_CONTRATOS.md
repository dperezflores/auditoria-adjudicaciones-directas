# Resultados · Dashboard ejecutivo de contratos extraídos

## Propósito
La sección **Resultados** ya no replica el explorador de Drive: se alimenta
de Google Sheets para construir una relación de **obras con contratos
analizados**. Una obra aparece por primera vez al extraer al menos un
contrato asociado; no se presentan obras que solo tienen carpetas o PDF sin
análisis.

## Fuente y trazabilidad
Sólo lee (batchGet) estas pestañas del registro:
- `DatosContrato`: ocho campos por contrato.
- `Extracciones`: estado, versión, resultado JSON y evidencia por campo.
- `Documentos`: comprobar que el registro corresponde al PDF vigente,
  activo y a la clave de extracción actual.
- `Obras`: vínculo con una obra activa y nombre de su carpeta para
  búsqueda auxiliar; **el nombre de obra visible procede del contrato
  extraído**, no de la carpeta.

No se descarga ningún PDF ni se llama a Gemini al entrar o filtrar.
No se modifican filas de Sheets.

## Indicadores
Los cuatro indicadores se recalculan con los filtros activos:
- **Obras con contrato:** número de IDs de obra diferentes.
- **Contratos extraídos:** número de versiones contractuales vigentes,
  sin duplicar historiales o reprocesamientos.
- **Monto identificado:** suma de montos numéricos extraídos cuando
  pertenecen a un mismo grupo de moneda; no suma divisas mixtas ni
  inventa monedas no indicadas en el texto.
- **Campos sin dato:** total de valores ausentes entre los ocho campos
  definidos por contrato, sin interpretarlo automáticamente como riesgo.

## Filtros, listado y detalle
Filtros por texto (obra, número o contratista), año de firma, contratista y
estado. El listado contiene número de contrato, nombre de obra, contratista,
monto con IVA, porcentaje de anticipo, año de firma y cobertura de campos.
Seleccionar una fila muestra la ficha completa, incluidas fechas literales
de firma, inicio y término.

El detalle incluye un apartado desplegable con páginas y fragmentos de
evidencia conservados en el JSON de extracción. La ficha permite abrir el
contrato original para cotejar los resultados.

Se puede exportar el listado filtrado a CSV. Los comparativos por contratista
o año se presentan solo con varias observaciones comparables, evitando
gráficos sin significado estadístico con un único registro.

## Exclusiones y controles
- No incluye obras ni documentos desactivados.
- No usa análisis de versiones anteriores, documentos modificados ni
  resultados de otros esquemas documentales (PUC, dictámenes, etc.).
- El historial del contrato ficticio archivado no se incorpora a los
  indicadores operativos.
- Una extracción con estado `REQUIERE_REVISION` puede aparecer como
  recuperación parcial, claramente identificada.
- Los valores son **extracciones de IA**, no hallazgos verificados.
  Las pruebas normativas y los riesgos se desarrollarán en
  `Pruebas de adjudicación` después de definir las reglas.

## Ejemplo disponible a la fecha del desarrollo
Existe un contrato real activo con extracción completa para la obra de
rehabilitación de caminos de Cerrito de Jerez, con importe identificado
de $2,350,150.88 y anticipo del 30 %. El dashboard mostrará ese
contrato y se actualizará conforme se analicen otros.

## Prueba funcional
1. Entra a `Resultados`. La pantalla consulta Google Sheets
   sin volver a usar Drive ni Gemini.
2. Debe aparecer una obra con contrato y su importe.
3. Busca por número de contrato, nombre o contratista.
4. Selecciona la fila y abre `Ver trazabilidad y evidencias extraídas`.
5. Cambia filtros, observa la actualización de indicadores y exporta CSV.
6. Después de analizar otro contrato en `Expedientes`, pulsa
   `Actualizar datos` en `Resultados` para refrescar el dashboard.
