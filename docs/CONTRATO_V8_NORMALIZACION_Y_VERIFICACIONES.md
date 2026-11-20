# Contrato v8: literalidad, normalización y verificación persistente

## Entorno y fuente

Esta implementación corresponde **solo a la app original** (`main`).
Se utilizó el archivo suministrado por el auditor:
`prompt_extraccion_contratos_v2.txt` (contenido íntegro en
`services/contract_prompt.py`, `PROMPT_VERSION = contrato-prompt-v8`).

El prompt pide **exactamente 15 campos**. Ya no solicita representante
técnico/superintendente ni convierte nombres de firmantes en esos cargos.
Conserva los participantes y su carácter literal, incluida la calidad de
testigos en el grupo de firmas, si aparece expresamente.

### Compatibilidad con datos anteriores

La estructura persistente `contrato-v2` y la hoja `DatosContratoV2`
conservan sus **16 columnas de datos** para no alterar documentos analizados
con prompts anteriores. En nuevas extracciones v8, el campo histórico
`representante_tecnico` está **vacío** y no se utiliza para determinar
cobertura o presentar la normalización. `Consultar análisis guardado`
muestra los **15 campos literales** (valor/página/evidencia) del prompt v8.
La validación de los textos no reemplaza su transcripción por etiquetas
calculadas. Los registros anteriores mantienen su versión y sus citas.

Las extracciones anteriores **no se reanalizan** automáticamente. La
actualización voluntaria y su aviso de consumo de Gemini siguen presentes.

## Normalización en Resultados

Una función única `services.contract_normalization.normalized_values`
prepara los valores visibles. Se aplica a Resultados y AD-06:

- **Tipo económico:** Precios Unitarios, Precio Alzado, Mixto o sin
  determinar. Coteja cláusulas y citas disponibles; no convierte
  «proyecto ejecutivo» por sí mismo en modalidad económica.
- **Modalidad:** AD, LS, LP, etc., con etiqueta normalizada.
- **Fechas:** DD/MM/AAAA cuando son reconocibles e inequívocas.
- **Monto:** cifra monetaria separada del texto en letras.
- **Anticipo:** solo porcentaje `30%`, `12.5%`, `0%` o `—`
  si no se puede identificar. Una declaración expresa de que no habrá
  anticipo muestra **0%**; si también aparece otro porcentaje, el listado
  agrega **observación de discrepancia**. Los importes citados en pesos
  no se interpretan como porcentajes.
- **Representante legal:** verificación documental de persona física o
  apoderado explícito. No se presume representación por una firma.
- **IVA:** valor `Con IVA (16%)` o `Sin IVA` si el contrato lo
  acredita. Cuando **no hay mención inequívoca**, el criterio
  provisional del piloto **supone «Con IVA (16%)»**, visiblemente
  etiquetado como **SUPUESTO NO ACREDITADO**. Si hay indicaciones
  contradictorias de inclusión, se mantiene **Por confirmar**,
  **sin aplicar el supuesto**. AD-06 no compara divisas extranjeras
  como si fueran MXN.

Los derivados no modifican ninguna celda de `DatosContratoV2` ni el PDF.

## Verificaciones y confirmaciones

El auditor puede seleccionar un contrato en **Resultados** o **AD-06**
y abrir «Verificar, corregir y GUARDAR los datos de este contrato».
Puede seleccionar tipo, modalidad, régimen, año del procedimiento,
condición del IVA, anticipo; además, corregir otros campos normalizados
(textos, fechas e importe) con una nota documental obligatoria.
Selecciona `Pendiente` o `Confirmado` y guarda.

La primera confirmación crea automáticamente la hoja adicional
`VerificacionesContrato` en la base maestra de Google Sheets.
Esta hoja es **append-only**: una nueva verificación agrega fila,
conservando anteriores, y registra:

`revision_id, obra_id, documento_id, cache_key, revision_utc,
auditor, estado_revision, campos_json, observaciones`

Al cargar, se aplica la **última revisión de la misma versión exacta
(`cache_key`) y documento/obra**. Una nueva extracción o PDF modificado
no hereda automáticamente una revisión vieja. Se verifica identidad y
vigencia nuevamente bajo el cerrojo de escrituras del proceso. Esto
es protección local; Google Sheets **no ofrece transacciones
multiinstancia**, por lo que no es apropiado para varios escritores
independientes sin coordinación.

Tras guardar, Resultados y AD-06 invalidan su caché y vuelven a leer
los valores normalizados y el dictamen provisional. El texto original
y la evidencia histórica permanecen visibles por separado.

## Diferencia entre vistas / descargas

- `Consultar análisis guardado`: **valores, citas y páginas literales**.
- `Resultados > Listado de obras y contratos`: normalización
  compartida + columna **Carpeta** + origen IVA + estado de verificación.
- `Pruebas de adjudicación > Evaluación automática`: se alimenta de
  la misma normalización y de las revisiones guardadas, con columna
  **Carpeta**; aplica tabla normativa y calcula importe sin IVA.
- `Exportar listado filtrado (CSV)`: los valores de la tabla Resultados.
- `Exportar resultados AD-06 (CSV)`: columnas de la evaluación automática.
- `Descargar base documental PDF (Excel)`: permanece **documental/literal
  y relacional**, sin sobrescribir las extracciones con revisiones manuales.

El cálculo por límites NO emite por sí solo una observación legal:
la aplicabilidad de las tablas, el ejercicio y el supuesto de IVA deben
ser cotejados por el auditor.
