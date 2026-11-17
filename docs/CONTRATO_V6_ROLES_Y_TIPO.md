# Contrato v6 · Tipo económico y roles contractuales

## Propósito

Ajustes al extractor de **la app original** para reducir falsos «sin identificar» en tipo contractual y no confundir firmantes, representantes técnicos, representantes legales y la persona física que firma por propio derecho. No se modifica la app de pruebas visual.

## Fuente y registro

El extractor continúa obteniendo **16 campos** en `contrato-v2`, cada uno con `valor`, `pagina` y `evidencia` literales. La única excepción explícita a la transcripción es el marcador derivado:

> **No aplica – Contratista persona física**

Ese marcador solo se registra en `representante_legal` cuando el PDF acredita que **la misma persona identificada como contratista** comparece como persona física / por derecho propio. Debe estar acompañada de página y una cita literal verificable. El marcador NO debe presentarse como un texto citado del contrato. El nombre de la persona se conserva como `contratista`. Un verdadero apoderado distinto, expresamente acreditado, debe conservarse como representante legal. No se infiere persona física a partir del RFC o el título «Arq.», «Ing.» o «Lic.».

## Tipo económico

Se buscan menciones a precios unitarios, precio alzado u otra modalidad en todas las cláusulas. Se distingue **plazo de ejecución** de **forma de pago**: «tiempo determinado» no determina el tipo por sí solo.

Cuando el modelo deja `tipo_contrato` nulo o devuelve solo información de plazo, el validador puede recuperar la frase literal «precios unitarios» si la **evidencia del monto contractual** contiene el monto numérico de ese mismo contrato y el mecanismo de pago («con base en los precios unitarios y volúmenes autorizados»), con página. No basta una oferta o una lista de PU de un anexo. Menciones contradictorias a precio alzado se dejan para cotejo; no se elige unilateralmente.

## Roles

- `representante_legal` (persona moral): exige un nombre y evidencia de representación legal de la empresa; un nombre aislado en el cuadro de firmas no basta.
- `representante_tecnico`: exige nombre, función técnica expresa **y vínculo con la contratista**. El representante de la entidad pública, supervisor, testigo, director u otra persona que solo firme no se clasifica aquí.
- `personas_participantes`: conserva por separado los firmantes y participantes reales con sus cargos **literales**; no genera por sí misma una designación de técnico o apoderado.
- Si no está inequívocamente acreditada una función, se conserva `null` y se añade observación de revisión; no se inventa un nombre.

## Visualización y trazabilidad

La tabla «Resultados» usa interpretaciones derivadas **solo cuando existe evidencia suficiente**. Por ejemplo, puede mostrar «Precios Unitarios» si el campo `tipo_contrato` quedó vacío pero la cláusula del monto guardada permite clasificarlo. La ficha individual conserva el valor literal del PDF en la sección de datos y exhibe por separado una nota con las clasificaciones.

Las interpretaciones de datos antiguos no actualizan ninguna celda de `DatosContratoV2` ni sobrescriben `Extracciones`. Si la evidencia vieja es insuficiente, el caso seguirá sin clasificar y necesitará una nueva extracción expresamente solicitada.

## Versionamiento y ejecución

`PROMPT_VERSION = contrato-prompt-v6`; mismo `CONTRACT_SCHEMA_V2 = contrato-v2`. El cambio de prompt modifica la clave de caché, pero **no dispara reanálisis** por sí solo. Se preserva el historial, las reglas de acceso, selección por expediente y los límites de análisis. Las pruebas de regresión son offline y cubren PF, apoderado real, representante técnico real, simple firmante, técnico municipal, precios unitarios e indicaciones ambiguas.

**No constituye determinación jurídica:** «No aplica» solo se marca con declaración suficiente en el PDF; la revisión profesional del contrato y poderes sigue siendo responsabilidad del auditor.
