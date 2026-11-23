# CC-01 · Capital contable: revisión masiva de adjudicación directa (León)

## Criterio de referencia

Manual de Procesos y Procedimientos DGOP León, PR-DGOP/DACF-011,
revisión 02, sección 3, políticas de operación, hoja 2. El criterio
de capital contable del PUC es el 30 % del monto total de la obra.

Documento de consulta:
https://www.leon.gob.mx/modulos/img/documentos/obrapublica/procedimientos%20y%20formatos/Manual%20de%20procesos%20y%20procedimientos/14.%20Contrataci%C3%B3n%20de%20obra%20p%C3%BAblica%20y%20servicios%20por%20adjudicaci%C3%B3n%20directa/Procedimiento%20rev02%20Act.%2012-08-2022.pdf

## Primera pasada: automática y masiva

A petición del auditor, el piloto **equipara operativamente la fecha de firma
del contrato con la fecha de asignación para la primera revisión**. Esto no
significa que ambas fechas sean jurídicamente idénticas. Permite clasificar
masivamente contratos y priorizar posibles riesgos.

1. Se leen exclusivamente **contratos y PUC activos y analizados** de la
   misma obra. El monto de contrato y las correcciones guardadas se usan
   conforme a las reglas actuales de la aplicación. AD-06 no se modifica.
2. Se comprueba que la cédula PUC esté vigente en la fecha de **firma**.
   Se reutiliza el **mismo motor anual de AD-03**: si la cédula solo contiene
   `vigencia_hasta`, el inicio se infiere restando un año calendario.
   El inicio inferido se muestra como dato calculado, sin alterar el PDF.
3. Si hay cédula válida, se toma **el capital contable indicado en esa
   cédula**, como dato de referencia **presuntivo de la primera pasada**.
4. Se calcula: **capital mínimo = 30 % × monto total contractual**;
   **diferencia = capital evaluado − mínimo**;
   **cobertura = capital evaluado ÷ monto contractual × 100**.
5. La clasificación clara es:
   - `Cubre el 30% (revisión inicial)`, con vigencia PUC a la firma.
   - `Capital inferior al 30% (revisión inicial)`.
   - `PUC fuera de vigencia en fecha de firma`, en caso de vencimiento
     frente a la cédula presentada, sin afirmar automáticamente que no
     existía otro refrendo.
   - Estados pendientes o de revisión si no se pudo validar identidad,
     firma, vigencia, monto, evidencia del capital o estado del registro.

Se mantiene el monto total contractual para el cálculo del 30 %, sin dividir
entre 1.16 ni inventar IVA. La diferencia entre el importe del dictamen y del
contrato se advierte para cotejo, pero **no bloquea por sí misma** la
comparación inicial basada en el contrato.

## Segunda pasada: documentación complementaria ante SOP

**No se exige el historial de actualizaciones para emitir el resultado
inicial favorable o desfavorable.** Posteriormente, según el riesgo, se podrá
solicitar a la Secretaría de Obra Pública (SOP) evidencia sobre cambios de
capital del contratista durante la vigencia del registro, sobre todo
modificaciones antes del refrendo o renovación siguiente.

El formulario de revisión histórica `RevisionesPUC` se conserva como
herramienta voluntaria, con fuente, fecha, referencia, capital oficial
y responsable del cotejo, sin volver a procesar documentos con Gemini.

Si se agrega **historial o certificación oficial** que prueba un capital
distinto y que ya estaba registrado en la fecha aplicable, el sistema compara
ese importe y lo identifica como `historial SOP`. Si los documentos prueban
una actualización **posterior** a la fecha aplicable, el sistema muestra
`Requiere revisión de actualización posterior` y no concede una aprobación
automática basada en ese movimiento.

## Precauciones y trazabilidad

La cifra de una cédula vigente **no prueba por sí sola** la inexistencia
de cambios de capital dentro del periodo: precisamente por eso el resultado
se denomina **revisión inicial**. La comprobación de fechas jurídicas,
movimientos históricos y soporte oficial corresponde a la auditoría
complementaria. Un estado favorable es una clasificación preliminar para
trabajo masivo, no una conclusión final de cumplimiento legal.

Los resultados y cédulas se leen de Google Sheets, conservando
`obra_id`, `documento_id` y `cache_key`. La app no modifica documentos
originales ni gasta tokens Gemini al comparar contratos.
La selección por fila y el CSV de CC-01 siguen disponibles.

Pruebas: `python -m unittest discover -s tests -v`.
