# Contrato v7 — Modalidad económica y testigos

## Hallazgo que motivó la mejora

Un contrato de **servicios relacionados con obra pública** puede identificarse como
«proyecto ejecutivo» en su encabezado y, al mismo tiempo, pactar **precios
unitarios** en la cláusula de monto y en «BASE DE PAGO». La naturaleza
«servicios relacionados» no responde a la clasificación económica para
precios unitarios/precio alzado. La evidencia debe obtenerse del texto que
realmente regula el precio del contrato.

Del mismo modo, las personas que aparecen debajo del encabezado **TESTIGOS**
en la última página no deben migrarse a `representante_tecnico`; tampoco
un servidor público asignado a supervisión municipal representa
técnicamente a la contratista.

## Cambios en el extractor

- `contrato-prompt-v7` busca la forma de pago en cláusulas de monto y
  BASE DE PAGO, y solicita evidencia literal de la frase **posterior**
  a «IVA incluido» cuando indique precios unitarios.
- El validador v2 recupera la frase literal solo si aparece en la cita
  del **mismo monto contractual**, con página verificable.
- La lista de participantes se cruza con el representante técnico:
  testigos y directores municipales no son representantes de la empresa.
- Los cargos de presidente del consejo de administración pueden
  acreditar representación de una persona moral cuando se documenten
  junto al nombre de la persona.
- La pestaña Resultados diferencia participantes de representación
  técnica acreditada; «testigo» solo aparece como clasificación cuando
  la cita guardada contenga expresamente ese encabezado.
- No se cambia la estructura de 16 campos de contrato-v2.

## Actualizar un análisis ya guardado SIN borrar el anterior

1. Abrir **app original** → **Expedientes de obra**.
2. Seleccionar la **carpeta de obra** y, en «Consultar análisis guardado»,
   elegir **CONTRATO.pdf**.
3. Abrir «Actualizar este contrato con el extractor mejorado».
   Solo aparece cuando el contrato tiene una extracción v2 anterior,
   el PDF sigue activo con la misma huella y no existe un intento
   de extracción sin confirmar.
4. Leer el aviso de consumo de Gemini, marcar la confirmación explícita
   y pulsar «Actualizar análisis de CONTRATO (contrato-prompt-v7)».
5. Después del procesamiento, abrir **Resultados**. La caché de
   resultados se invalida para volver a consultar Sheets; es posible
   pulsar «Actualizar datos» para forzar una recarga.

La nueva solicitud usa el mismo motor y el mismo candado de escritura.
El prompt nuevo genera una clave de caché diferente; se preservan los
registros originales de las hojas `Extracciones` y `DatosContratoV2`.
El vínculo vigente en `Documentos` solo cambia cuando Sheets confirma
una extracción nueva. Nunca se llama a Gemini por navegar o consultar
la información.

**Si la versión guardada ya es v7**, este botón no aparece. Si existe
intento no confirmado se bloquea para evitar duplicar consumo. No
utilizar «Eliminar análisis» para actualizar versiones.

## Qué no puede corregirse sin nueva evidencia

Si una extracción antigua guardó el monto pero omitió la frase de precios
unitarios, la app no inventa esa frase ni completa el tipo por intuición.
Debe obtenerse una extracción nueva del PDF con el prompt actualizado,
o un cotejo manual trazable si posteriormente se habilita tal opción.

El dato original sigue accesible en «Evidencias del PDF». Las decisiones
derivadas de un testigo/representante son preliminares y requieren
verificación profesional.
