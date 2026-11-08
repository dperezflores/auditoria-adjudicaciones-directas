# Activar el registro persistente de Google Drive en Google Sheets

## Estado: código integrado; configuración final pendiente

El explorador ya detecta carpetas y PDF. El motor nuevo también puede registrar
los metadatos en Google Sheets y comparar una consulta con la anterior.

**Hoja existente y verificada:** `AuditorIA_AD_Master_Piloto`.
Está dentro de `Datos_AuditorIA_PILOTO`, con cinco pestañas: Obras, Documentos,
Sincronizaciones, Historial, Configuracion.

La cuenta de servicio `auditoria-drive-reader@auditoria-ad-piloto.iam.gserviceaccount.com`
tiene permiso **Lector** sobre la carpeta piloto y **Editor** exclusivamente
sobre la hoja maestra. No le otorgamos permiso de escritura sobre la carpeta de PDF.

## Única modificación manual: añadir ID de la hoja a Streamlit Secrets

Abre la aplicación en https://share.streamlit.io/ → Settings → Secrets.
**Mantén intactas** las secciones `[auth]`, `[access]`, `[drive]` y
`[gcp_service_account]` que ya funcionan.

Agrega AL FINAL:

```toml
[storage]
spreadsheet_id = "1xvipXJCI4G6RWpqsPCU6FKVqpWSgaWvPYY7j5MNJdGM"
```

Guarda los secretos y deja que Streamlit reinicie la aplicación. El ID de
la hoja no es una contraseña. **No pegues ni publiques las claves privadas**.

## Cómo verificar

1. Inicia sesión y entra a `Google Drive (piloto)`.
2. Presiona **Actualizar Google Drive**.
3. Debe mostrarse `Sincronización guardada en Google Sheets`.
4. Abre la pestaña `Obras` en la hoja maestra: deberían existir **2 obras**.
5. Abre `Documentos`: debería existir **1 PDF**.
6. Presiona Actualizar una segunda vez. Las filas de `Obras` y
   `Documentos` deben mantenerse sin duplicados. Habrá **otro registro**
   en `Sincronizaciones`, porque cada actualización constituye una ejecución
   distinta; `Historial` solo debe crecer si hay cambios.
7. Cierra la pestaña del navegador y vuelve a abrir: las filas seguirán
   guardadas en Sheets.

## Reglas programadas

- Carpeta nueva: alta de obra por ID de Drive.
- PDF nuevo: alta documental por ID, estado `Pendiente`.
- PDF renombrado: actualiza el nombre, conserva su registro y estado anterior.
- Contenido modificado: comparación de MD5; si no existe MD5, se usan fecha
  y tamaño como indicio.
- PDF retirado o carpeta retirada: se marca `activo = NO`; no se destruye
  el histórico y se registra el evento.
- PDF reactivado: conserva ID, fecha original de primera detección e historial.
- Extracciones futuras: la sincronización no sobrescribe `resultado_id`,
  `version_extractor`, `tipo_documental` ni validaciones previas.
- Gemini sigue **desactivado**, por lo que guardar metadatos no consume tokens.

## Limitaciones del piloto

- Solo hay **sincronización manual** mediante el botón; la actualización
  automática cada 60 s se añadirá posteriormente.
- Google Sheets no es transaccional. La app utiliza un cerrojo común a todas
  las sesiones de **un mismo proceso Streamlit**; múltiples réplicas/servidores
  escritores pueden entrar en carrera. Antes de habilitar escalamiento
  multiinstancia se requerirá un escritor único real o PostgreSQL.
- Los rangos no crecen indefinidamente si se exceden límites de la hoja.
- No se marcan jurídicamente incumplimientos sin evidencia: la capa actual
  es únicamente de control documental.

## Solución de problemas

Si se muestran las obras pero aparece el mensaje `No se confirmó el guardado
en Google Sheets`, revisa el ID bajo `[storage]`, la hoja compartida
como Editor con la cuenta de servicio, los cinco nombres de pestañas y los
encabezados. La app no debe mostrar claves ni errores internos de Google.

No elimines filas para reiniciar la prueba sin un respaldo. Si el inventario
se modificó manualmente, el motor puede detenerse al detectar IDs duplicados
o encabezados alterados.
