# Etapa 1 — Identificación documental (sin inteligencia artificial)

## Qué funciona ahora
AuditorIA reconoce seis códigos documentales:

| Código | Documento | Formato inicial |
|---|---|---|
| CONTRATO | Contrato de obra pública | PDF |
| PUC | Hoja de consulta del Padrón Único de Contratistas | PDF |
| CATALOGO | Catálogo/prefiniquito para análisis de conceptos originales | XLSX |
| DICTAMEN_AD | Dictamen de autorización de adjudicación directa | PDF |
| NOTIFICACION_AD | Notificación de adjudicación directa | PDF |
| ORDEN_AD | Orden formal de adjudicación (si existe) | PDF |

El código se **sugiere por nombre** y solo se **confirma por contenido** cuando
hay encabezados inequívocos. `PADRON.pdf` se sugiere como PUC;
`DICTAMEN TECNICO.pdf` no se supone automáticamente dictamen de adjudicación.
Si el nombre y el contenido apuntan a códigos distintos, el sistema muestra
**Inconsistente** y no guarda el código.

Los PDF textuales se leen con `pypdf` y los Excel con `openpyxl`.
La lectura se realiza **solo cuando el usuario pulsa Verificar tipo por
contenido**, sin llamadas a Gemini. No se envían PDFs ni libros al proveedor
de IA. Los PDF escaneados (solo imagen) pueden no contener texto extraíble;
en esos casos quedan **sin confirmar**, no se asignan códigos por conjetura.
En una etapa posterior se habilitará clasificación visual para esos archivos.

### Persistencia y control
- La sincronización de Drive incorpora PDFs y archivos XLSX a `Documentos`.
- El código **confirmado** se escribe en la columna `tipo_documental`,
  conservando las columnas, pestañas y referencias actuales.
- Se comprueba `documento_id`, `obra_id`, MIME, MD5 y estado activo antes
  de guardar; si cambian los bytes o la obra, la sincronización elimina el
  código confirmado y solicita una nueva verificación.
- Los Excel se incluyen en el registro sin sumarse incorrectamente a las
  métricas existentes de `pdf_*`. Los tipos no compatibles no se procesan.
- `CATALOGO.xlsx` se clasifica aquí, pero aún no se extraen conceptos
  ni se realizan comparaciones de especialidad.

### Protección temporal contra extracciones incorrectas
El botón de análisis con Gemini permanece **deshabilitado en esta etapa**,
porque el extractor antiguo aplicaba 16 campos contractuales a cualquier PDF,
incluido el PUC y los dictámenes. No se realizarán nuevas extracciones hasta
activar y probar los esquemas de datos especializados.

### Prueba manual
1. Abre **Expedientes** y pulsa **Actualizar Google Drive**.
2. Comprueba que `CATALOGO.xlsx` aparece en Otros documentos con código
   sugerido `CATALOGO`; no será enviado a Gemini.
3. Baja a **Identificación documental**, elige la obra y un archivo.
4. Comprueba el código sugerido y pulsa **Verificar tipo por contenido
   (sin IA)**. Si el contenido es legible y coincide, el código se guarda
   en la columna D (`tipo_documental`) de `Documentos`.
5. Verifica sucesivamente `CONTRATO.pdf`, `PUC.pdf`,
   `DICTAMEN_AD.pdf` y `CATALOGO.xlsx`. Si aparece
   `Sin texto legible`, el archivo probablemente requiere clasificación
   visual en la siguiente etapa.
6. Repite **Actualizar Google Drive** y verifica que los códigos confirmados
   persisten sin duplicarse.
7. **No pulses ni intentes habilitar** el análisis antiguo; cada código
   utilizará un extractor propio después de las pruebas.

## Lo que sigue
Crear el esquema específico de extracción del PUC y sus pruebas; después
DICTAMEN_AD, NOTIFICACION_AD, CONTRATO, y lectura tabular de CATALOGO.
No se ejecutarán todavía cruces ni determinaciones legales.
