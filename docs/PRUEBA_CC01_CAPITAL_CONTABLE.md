# Prueba CC-01 — Capital contable en el PUC (León)

## Alcance y fundamento

En la app original, bajo Pruebas de adjudicación, se incorporó una pestaña
«Verificación de capital contable», independiente de «Verificación de límites
de adjudicación» (AD-06), que continúa funcionando como antes.

Fuente de referencia: Manual de Procesos y Procedimientos de la DGOP León,
PR-DGOP/DACF-011, rev. 02, sección 3, políticas de operación, hoja 2.
El manual indica que en adjudicación directa el contratista debe tener
registrado en su PUC, a fecha de asignación, capital contable de al menos
30 % del monto total de la obra.

Vínculo oficial:
https://www.leon.gob.mx/modulos/img/documentos/obrapublica/procedimientos%20y%20formatos/Manual%20de%20procesos%20y%20procedimientos/14.%20Contrataci%C3%B3n%20de%20obra%20p%C3%BAblica%20y%20servicios%20por%20adjudicaci%C3%B3n%20directa/Procedimiento%20rev02%20Act.%2012-08-2022.pdf

## Cálculo

- Capital mínimo = monto total del contrato × 30 %, a centavos.
- Diferencia = capital contable del PUC − capital mínimo.
- Cobertura (%) = 100 × capital PUC / monto contractual total.

El cálculo utiliza el monto contractual total guardado, o el revisado por
el auditor. No se divide entre 1.16 para esta prueba, ya que el manual
habla del monto total; si el contrato está expresado sin IVA, no se
añade el impuesto sin respaldo. La interpretación final de la base
debe cotejarse con la normativa y el expediente.

## Cruce documental y temporal

Se leen en Google Sheets las versiones activas de `Documentos`, `Extracciones`, `DatosPUC` y `DatosDictamenAD`, vinculando obra/documento/caché. Los PUC duplicados, modificados, incompletos o no analizados no se aplican. La identidad del contratista se comprueba por RFC o número de registro PUC. LS/LP se marcan `No aplica`.

El capital que consta en el PDF disponible **no se presume registrado a la fecha de asignación**, aun si la validación o impresión son anteriores. Una constancia impresa **después** de la asignación tampoco demuestra por sí sola que el capital se registró después.

El resultado distingue:

- **Comparación aritmética provisional:** capital de constancia × importe contractual total. Se conserva el cálculo del 30 % existente.
- **Acreditación histórica:** utiliza `capital_historico` y `fecha_registro_capital` solo cuando el auditor ha registrado evidencia verificable y la fecha oficial del movimiento no es posterior a la fecha efectiva de asignación.
- Sin evidencia de fecha e importe históricos, el estado es `Capital histórico por acreditar`, incluso si la comparación provisional da suficiencia o insuficiencia.
- Si existe un registro histórico documentado anterior o igual a la asignación, se compara **ese** capital contra el 30 %, mostrando `Capital histórico suficiente (preliminar)` o `Capital histórico inferior al 30% (preliminar)`.
- Si el movimiento se registró después de asignar, no se utiliza ese capital retroactivamente: `Capital histórico por acreditar`.

La fecha efectiva de asignación la puede asentar el auditor mediante `RevisionesPUC`; la fecha del dictamen es solo referencia preliminar, y la firma del contrato no la sustituye.

## Estados y presentación

La tabla muestra carpeta, contrato, contratista, monto total, 30 % requerido, capital de constancia, capital utilizado en la comparación, diferencia, cobertura, resultado aritmético y acreditación histórica, con evidencia y vínculos de origen. La conclusión profesional del auditor y el resultado automático se muestran por separado.

Para cotejar fechas, refrendos y la condición de inscripción se dispone de la **prueba independiente AD-03 — Verificación de vigencia del PUC**, sin condicionar el cálculo del capital a la fecha de impresión. Ambas pruebas utilizan una hoja adicional `RevisionesPUC` con historial append-only ligado a las versiones actuales de contrato y PUC.

La pantalla de capital conserva la verificación contractual, descarga CSV y acceso al PUC. Consultar o guardar cotejos no activa Gemini. El formulario histórico solicita fuente, referencia y observaciones; la constancia y las extracciones originales no se modifican.

## Precauciones

El resultado es una prueba de gabinete y no determina por sí solo
incumplimiento legal. Deben revisarse vigencia y aplicabilidad del manual,
fecha efectiva de asignación y registro histórico de capital.
La app de pruebas visual permanece intacta.

Pruebas: python -m unittest discover -s tests -v
