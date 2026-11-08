# Paso siguiente — habilitar el inicio de sesión con Google

## Qué se implementó

- `security/app_access.py` comprueba si existen secretos de OIDC.
- Sin sección `[auth]`, la app permanece **solo como demostración ficticia**.
- Con `[auth]` y `[access]` completos, exige inicio de sesión mediante `st.login()` y comprueba la lista de correos permitidos.
- Si existe `[auth]` pero faltan valores, bloquea la aplicación en vez de permitir el acceso.
- No se ha conectado Google Drive, ni se obtienen permisos de Drive por iniciar sesión.

## 1. Configurar la URL de retorno del cliente OAuth

En Google Cloud, proyecto `auditoria-ad-piloto`, entra a **Google Auth Platform > Clientes** y edita el cliente web creado:

```text
https://auditoria-adjudicaciones-directas.streamlit.app/oauth2callback
```

Agrégala entre las **URI de redireccionamiento autorizados** y guarda.

**Aviso:** la URI anterior terminada en `/` por sí sola NO sirve para `st.login()`. El sufijo `/oauth2callback` debe coincidir exactamente con la configuración de Streamlit.

Referencia: https://docs.streamlit.io/develop/tutorials/authentication/google

## 2. Configurar secretos privados en Streamlit Community Cloud

En https://share.streamlit.io/ abre la aplicación y ve a **Settings > Secrets**. Añade el contenido TOML siguiendo este modelo, sustituyendo los valores entre comillas:

```toml
[auth]
redirect_uri = "https://auditoria-adjudicaciones-directas.streamlit.app/oauth2callback"
cookie_secret = "GENERA_UNA_CADENA_ALEATORIA_LARGA_Y_PRIVADA"
client_id = "TU_CLIENT_ID_DE_GOOGLE"
client_secret = "TU_CLIENT_SECRET_DE_GOOGLE"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"

[access]
allowed_emails = ["TU_CORREO_PERSONAL_DE_GOOGLE"]
```

**Importante:** mantén la sección `[auth]` completa, el correo exacto autorizado y **no incluyas este archivo ni valores reales en GitHub, este chat o capturas**.

Para generar un secreto aleatorio localmente puedes ejecutar en tu propio equipo:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Usa la salida solo en `cookie_secret` de Streamlit Secrets. Una contraseña larga, aleatoria y única generada por un gestor de contraseñas también es válida.

Pulsa **Save** y espera al reinicio/despliegue de la aplicación.

## 3. Verificar

1. Abre la aplicación en ventana privada: https://auditoria-adjudicaciones-directas.streamlit.app/
2. Debes ver **Iniciar sesión con Google** y no las pestañas de AuditorIA.
3. Ingresa con el usuario registrado en **Usuarios de prueba** de Google Cloud.
4. Deben aparecer nuevamente las tres pestañas ficticias y la opción **Cerrar sesión**.
5. Cierra sesión y confirma que el contenido vuelve a estar protegido.

Si Streamlit muestra `redirect_uri_mismatch`, revisa la dirección exacta en Google Auth Platform y `[auth].redirect_uri`. Si Streamlit dice que la configuración está incompleta, revisa la indentación, nombres de secciones y cinco propiedades del bloque `[auth]` y la lista `[access].allowed_emails`.

## Riesgos y límites

- Este inicio de sesión **solo identifica al usuario de AuditorIA**. No autoriza por sí solo la lectura de carpetas o PDF de Google Drive.
- El código y la página siguen en un repositorio y un despliegue inicialmente públicos. No incorporar expedientes reales hasta aprobar el tratamiento de datos, controlar accesos y asegurar el backend y el repositorio.
- El usuario de pruebas OAuth y la lista de correos autorizados son dos filtros diferentes; ambos deben contener la cuenta que utilizarás.
- El flujo de lectura de Drive y escritura de Sheets se implementará aparte, con un responsable y credenciales de servicio adecuadas.
