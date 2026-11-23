# Prueba AD-03 — Vigencia del PUC al firmar contrato (León)

## Objetivo y criterio aprobado

Esta prueba determina **exclusivamente si el contratista cuenta con una vigencia de PUC que abarque la fecha de firma de su contrato**. No utiliza la fecha de asignación, notificación ni emisión del dictamen para decidir su resultado. Se conserva el alcance de adjudicación directa (AD) del piloto.

### Cálculo

1. Tomar la **fecha de firma** del contrato analizado (incluida la corrección validada por el auditor, cuando exista).
2. Leer la fecha **vigencia hasta** de la cédula del PUC.
3. Leer **vigencia desde** solo si aparece expresamente en el PUC. **Si no aparece, calcularla restando un año calendario a «vigencia hasta»**, de acuerdo con el criterio operativo aprobado para el piloto.
4. Comparar con extremos inclusivos: `vigencia_desde <= firma <= vigencia_hasta`.
5. Si la firma está dentro, reportar **«Vigente en fecha de firma»**. Si está fuera, reportar **«Fuera del periodo PUC en fecha de firma»**; antes de formular una observación, revisar otros refrendos o excepciones aplicables. Si falta la fecha de firma o vencimiento, reportar pendiente, nunca presumir vigencia.

**Ejemplo:** PUC con vigencia hasta 15/06/2025, sin inicio explícito: desde **15/06/2024** hasta **15/06/2025**. Una firma del 15/06/2024 o del 15/06/2025 queda dentro del periodo; una firma del 16/06/2025 queda fuera.

La resta es por año **calendario**, no por 365 días: en el caso excepcional de una vigencia que termina el 29/02 de un año bisiesto, el inicio calculado corresponde al 28/02 del año previo.

## Registro y evidencia

- Se usa únicamente el PUC activo y analizado, de la misma obra, con identidad de contratista verificable. Se bloquean documentos duplicados, modificados y asociaciones erróneas.
- La aplicación indica cuando el inicio de vigencia es **calculado**, lo separa del valor literal del PDF y nunca sustituye la información extraída por Gemini.
- La fecha de validación y la de impresión no se usan para calcular la vigencia.
- Suspensión o cancelación reportada en la cédula requiere cotejo de la fecha en que surtieron efectos; no se interpreta retrospectivamente sin evidencia.
- El formulario histórico opcional `RevisionesPUC` y las conclusiones manuales previamente incorporadas permanecen disponibles, pero **no son necesarios para la comparación automática**. Si existe un intervalo histórico certificado que corresponde a las mismas versiones documentales, puede utilizarse en lugar del intervalo del PDF.
- Esta simplificación de AD-03 **no cambia la prueba CC-01 de capital contable**, en la cual continúa siendo relevante el capital efectivamente registrado a la fecha de asignación. AD-06 tampoco cambia.

## Resultado en la interfaz

La tabla presenta contrato, contratista, registro PUC, **fecha de firma, vigencia desde, origen de esa fecha (expresa/calculada), vigencia hasta y resultado**. Los registros pendientes o con fechas incompatibles se identifican expresamente.

AD-03 no llama a Gemini, no escribe datos al consultar y mantiene descarga CSV. La evaluación es una prueba de gabinete; un periodo de cédula que no cubre la firma no demuestra automáticamente que no existía otro refrendo.
