# Etapa 1 — Clasificación documental automática por nombre

## Regla aprobada

AuditorIA identifica el tipo documental **exclusivamente por el nombre de archivo
y el formato de Google Drive**. No verifica encabezados ni contenido en esta etapa,
no descarga PDF o Excel para clasificarlos y no llama a Gemini.

| Nombre exacto | Código asignado | Formato |
|---|---|---|
| `CONTRATO.pdf` | `CONTRATO` | PDF |
| `PUC.pdf` | `PUC` | PDF |
| `CATALOGO.xlsx` | `CATALOGO` | Excel |
| `DICTAMEN_AD.pdf` | `DICTAMEN_AD` | PDF |
| `NOTIFICACION_AD.pdf` | `NOTIFICACION_AD` | PDF |
| `ORDEN_AD.pdf` | `ORDEN_AD` | PDF (opcional) |

La comparación de nombres no distingue mayúsculas/minúsculas; la extensión
y el tipo MIME sí deben corresponder. Los nombres diferentes a estas
convenciones (por ejemplo `PADRON.pdf`, `DICTAMEN TECNICO.pdf`,
`CONTRATO (1).pdf`) muestran `POR_IDENTIFICAR` y deben renombrarse en Drive
cuando corresponda; **no se equiparan automáticamente** a otra clase documental.

## Operación

1. Renombra cada documento de la obra usando el código aprobado.
2. En **Expedientes** pulsa **Actualizar Google Drive**.
3. En el explorador revisa la columna **Tipo documental**.
4. Los seis códigos se registran automáticamente en
   `AuditorIA_AD_Master_Piloto`, hoja `Documentos`, columna
   `tipo_documental`. No existe botón de verificación por contenido.
5. Al cambiar el nombre, la próxima sincronización recalcula el código;
   los identificadores e historial del documento se conservan.
6. El extractor de IA sigue pausado hasta construir los esquemas separados
   de PUC, dictamen, notificación, contrato y catálogo.

## Alcance y limitación

Clasificar `PUC.pdf` como `PUC` **no comprueba** que su contenido realmente
sea una hoja PUC: se confía en la correcta nomenclatura del expediente.
La exactitud de la asignación depende del nombre proporcionado por el
usuario o sujeto fiscalizado; conviene controlar los nombres al integrar
las carpetas.

`CATALOGO.xlsx` se registra sin análisis. En la siguiente etapa se
leerán sus conceptos directamente con Python y se excluirán los renglones
fuera de catálogo de la prueba inicial de especialidad, sin borrarlos.

No se ejecutan nuevas pruebas legales ni cruces documentales en esta etapa.
