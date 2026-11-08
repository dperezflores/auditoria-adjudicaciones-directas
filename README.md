# AuditorIA — Adjudicaciones Directas

Piloto para la revisión documental y pruebas de auditoría de adjudicación directa de obra pública en Guanajuato.

## Estado actual
**Etapa 1: base de código y demostración de Streamlit.**
La versión inicial usa exclusivamente datos ficticios y no realiza análisis de IA ni conexiones con expedientes reales.

## Objetivo
1. Detectar obras y documentos PDF en una carpeta central de Google Drive.
2. Extraer con Gemini datos del contrato, PUC, dictamen, notificación y catálogo.
3. Conservar las extracciones y evitar repetir procesamiento de PDF sin cambios.
4. Ejecutar cinco pruebas: capital contable, especialidad, vigencia PUC, responsable técnico y secuencia de fechas.
5. Mostrar resultados por obra y dashboard de la muestra.

## Tecnología
Python, Streamlit, Google Drive API, Google Sheets API, Gemini API, Pydantic, Pandas y Plotly.

## Ejecutar una demostración local

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

## Publicar en Streamlit
En [Streamlit Community Cloud](https://share.streamlit.io/) selecciona este repositorio, rama `main`, archivo principal `app.py` y despliega.

## Seguridad
El repositorio está público temporalmente. No subir credenciales, tokens OAuth, contraseñas, archivos confidenciales ni expedientes. Para trabajar con documentación real se necesitará repositorio privado, autenticación y autorización institucional. Los secretos se administrarán fuera de GitHub.

## Próximos hitos
- Conexión OAuth y sincronización incremental de Google Drive.
- Persistencia en Google Sheets.
- Análisis PDF con Gemini y caché persistente.
- Pruebas AD-01 a AD-05.
- Dashboard, trazabilidad y exportación.

El prototipo visual no debe confundirse con un dictamen de auditoría ni con una herramienta de fiscalización en producción.
