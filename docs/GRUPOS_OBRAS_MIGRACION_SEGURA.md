# Grupos de obras en Google Drive — migración sin pérdida de resultados

## Objetivo

Separar los expedientes en grupos dentro de la carpeta raíz
`AUDITORIA_PILOTO`, manteniendo una vista **Todas las obras** y un filtro
global para **Expedientes, Resultados, límites AD-06, capital CC-01 y
vigencia PUC AD-03**. Los filtros ya existentes (año de firma,
contratista, búsqueda, estado) siguen funcionando dentro del grupo.

## Estructura recomendada

```text
AUDITORIA_PILOTO/
├── GRUPO_Obras_de_auditoria/
│   ├── 00_045_25_MantEspPubPaq2/
│   └── 00_591_25_ParqueUyepac/
├── GRUPO_Obras_de_pruebas/
│   ├── 001/
│   ├── 002/
│   └── 003/
├── Recursos/                          # sigue en la raíz
└── otras_carpetas_de_obra/           # se muestran bajo «Sin grupo»
```

**Regla conservadora de reconocimiento:** una agrupadora debe comenzar
por `GRUPO_`, `GRUPO-`, `GRUPO:` o `GRUPO `. Si ya existen
agrupadoras con nombres distintos como `01 - Obras de auditoría`,
se pueden declarar sus identificadores en los secretos privados:

```toml
[drive]
root_folder_id = "ID_EXISTENTE_DE_LA_CARPETA_RAIZ"
group_folder_ids = ["ID_EXISTENTE_DE_LA_CARPETA_AGRUPADORA"]
```

No agregar claves a archivos públicos de GitHub; `group_folder_ids`
no es obligatorio si los nombres empiezan por `GRUPO_`.

Se reconocen **obras dentro de un único nivel de agrupadoras**.
Las subcarpetas documentales dentro de una obra (PUC, Contratos,
Anexos) no pasan a ser obras independientes, y los documentos dentro
de una obra siguen encontrándose como antes.

## Pasos de migración segura

1. **Conservar** la carpeta original `AUDITORIA_PILOTO`, el mismo
   archivo maestro de Google Sheets y las credenciales. No crear una
   hoja nueva ni modificar `root_folder_id`.
2. Realizar una **copia de seguridad** de la base documental de Google
   Sheets antes de reorganizar carpetas.
3. Crear las agrupadoras `GRUPO_...` dentro de `AUDITORIA_PILOTO`.
4. Usar la opción **Mover** de Google Drive para trasladar las
   **carpetas de obra originales** al grupo; **no copiarlas y volver
   a subir los PDF**, porque cambiarían sus IDs.
5. Verificar que cada obra sigue conteniendo sus documentos originales.
   Mantener `Recursos` directamente bajo `AUDITORIA_PILOTO`.
6. En AuditorIA pulsar **Actualizar grupos de Drive** y después
   **Actualizar Google Drive** en Expedientes. Comprobar primero
   la vista **Todas las obras** y luego cada grupo.

## Garantías y salvaguardas técnicas

- La identidad de una obra sigue siendo su **ID de carpeta original**,
  y la de cada documento su **ID de archivo original**. Un cambio de
  ubicación/nombre de una agrupadora no provoca una nueva extracción.
- Se conserva la misma hoja de Google Sheets. No se borran las hojas
  `Extracciones`, `DatosContrato`, `DatosPUC`,
  `RevisionesPUC` ni las verificaciones de contrato.
- El **escaneo y sincronización siempre recorren todas las obras**
  antes de aplicar el filtro visual. No se desactivan las obras de
  otros grupos al cambiar la selección.
- **Protección ante pérdidas:** cuando un expediente o documento
  registrado como activo ya no aparece bajo la estructura reconocida,
  el botón de actualización **bloquea cualquier escritura del lote**
  y muestra la incidencia. No marca automáticamente como inactivas
  las obras que podrían haberse movido o quedar sin acceso.
- El filtro global solo modifica qué registros se muestran. La vista
  `Todas las obras` conserva el panorama de contratos y resultados;
  la vista `Sin grupo` incluye carpetas originales en la raíz.

### Importante

Esta protección también bloquea la **archivación automática** de
carpetas/PDF realmente eliminados del Drive durante el flujo ordinario
de `Actualizar Google Drive`. Se trata de una restricción deliberada
para proteger los resultados históricos durante la reorganización;
una futura función de archivación confirmada podrá permitir bajas
intencionales sin eliminar las extracciones de los documentos.

No se ha movido ni renombrado ninguna carpeta del Drive mediante este
cambio de código. La prueba se realiza contra metadatos de Drive y
datos ficticios en CI, sin IA. Antes de reorganizar expedientes reales
debe hacerse el respaldo y cotejar la sincronización.
