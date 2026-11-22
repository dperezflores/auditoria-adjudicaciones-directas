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

Se leen en Google Sheets los registros actuales de Documentos, Extracciones,
DatosPUC y DatosDictamenAD, vinculando obra_id, documento_id y cache_key.
El capital se obtiene del campo capital_contable del PUC, con evidencia y
página. La identidad del contratista se comprueba por RFC y registro PUC.
Los PUC duplicados, modificados, incompletos o no analizados no se toman
automáticamente. Los contratos de LS/LP se marcan No aplica.

Cuando existe dictamen AD completo, su fecha_emision es una referencia
temporal preliminar; no sustituye confirmar la fecha efectiva de asignación.
Sin dictamen, la fecha del contrato es solo referencia y la parte
histórica queda pendiente. Si el PUC fue impreso o validado después
de la referencia, estaba vencido, o no tiene fechas suficientes, la
prueba conserva el cálculo pero no acredita retrospectivamente el capital.

## Estados y presentación

La tabla muestra carpeta, contrato, contratista, monto total, capital PUC,
30 % requerido, diferencia, porcentaje de cobertura y dos diagnósticos
independientes: comparación aritmética y verificación histórica.

Los principales estados son: Cubre el 30 % (preliminar), Capital inferior
al 30 % (preliminar), Pendiente de PUC, Pendiente de revisión histórica,
Requiere revisión de identidad/importes/evidencia, y No aplica.

Si aún no se analizó el PUC, se indica «Pendiente de PUC»; jamás se
clasifica como capital insuficiente. La interfaz ofrece una ficha con
evidencia y página PUC, vínculo al PDF original en Drive y descarga CSV.
Para completar documentos faltantes se puede usar Expedientes > Varias
carpetas > PUC.pdf. Consultar esta prueba no activa Gemini.

El formulario de verificación existente permite confirmar o corregir
valores del contrato (sin alterar extracción histórica). La prueba no
reescribe los datos de PUC ni el archivo original.

## Precauciones

El resultado es una prueba de gabinete y no determina por sí solo
incumplimiento legal. Deben revisarse vigencia y aplicabilidad del manual,
fecha efectiva de asignación y registro histórico de capital.
La app de pruebas visual permanece intacta.

Pruebas: python -m unittest discover -s tests -v
