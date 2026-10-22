# M01.4B-B2 — React + BFF alojado: implementación inicial

**Estado:** Código aislado en una rama feature, **no probado contra Supabase alojado**.
**OFFLINE / NO_TRADE.** No se cambió la configuración de Supabase, no se ejecutaron logins ni se tocaron factores TOTP.

## Arquitectura implementada

- El BFF alojado reutiliza `HostedPilotSettings` y `IntegratedHostFactory`, manteniendo exactamente el origen TLS de loopback y la política de CSRF/cookies que ya existían.
- `TradingAgent.Web.Browser.BrowserHost.CreateHosted` entrega el build React bajo el mismo origen HTTPS; los assets se limitan por `BrowserAssets`.
- `GET /bff/config` expone solamente `HOSTED_DEVELOPMENT_AUTH`, `OFFLINE`, `NO_TRADE` y `executionAuthorized=false`; nunca valores de claves, tokens o sesiones.
- React reconoce el perfil alojado **solo en `https://127.0.0.1:<puerto>`**. Mantiene el fixture exclusivamente en `https://localhost`. Una respuesta inválida falla cerrada.
- Se preserva el mismo `BffAuthAdapter` HTTPS/CSRF y su validación de AAL2/SQL, sin SDK Supabase, JWT, refresh tokens ni credenciales de base de datos en el navegador.
- El launcher B2 es una entrada independiente del fixture de pruebas, sin llamar a `HostedDatabase.SeedAsync`, sin `CREATE ROLE`, sin registro de usuarios y sin grants automáticos. Exige roles **ya provisionados en un PostgreSQL explícitamente desechable**, que el propio `SecurityDatabase` valida antes de escuchar en HTTPS.
- Requiere un certificado **previamente confiado por el sistema** que incluya SAN IP `127.0.0.1`, con clave privada y validez temporal. Nunca instala certificados ni ignora errores TLS.

## Límites importantes

1. **Esto no es todavía un login real acreditado.** El problema histórico JWT alojado sigue sin causa verificada.
2. El factor TOTP existente sin verificar sigue bloqueado: ninguna ruta B2 elimina, sustituye o recupera automáticamente ese factor.
3. El acceso requiere identidad registrada/activa y autorización SQL emitida por un administrador humano. El launcher no registra ni concede permisos.
4. Recuperación, invitaciones y cambios de contraseñas reales continúan bloqueados.
5. No se ejecuta la entrada alojada por GitHub Actions: CI utiliza únicamente Auth simulado y Postgres marcado.
6. No reutilizar `build/auth-pilot/run-hosted.ps1` para iniciar React: ese flujo histórico permite bootstrap/recuperación y no es el launcher de B2.
7. No almacenar la clave privada TLS, contraseñas SQL ni credenciales de cuenta en Git/artefactos. La aprobación de autenticación alojada es independiente del merge de código.

## Arranque Windows — solo tras autorización explícita para prueba real

Preparar por medios externos un clúster PostgreSQL desechable con el esquema M01.2 ya migrado y dos roles mínimos separados. Configurar HTTPS con PFX confiado cuyo SAN IP sea `127.0.0.1`. No cambiar Site URL ni plantillas de Supabase para login por password; los callbacks recovery/invite siguen prohibidos.

Compilar React mediante `npm --prefix frontend-react ci --ignore-scripts` y `npm --prefix frontend-react run build`. Restaurar/compilar el proyecto `build/react-bff/BrowserFixture/BrowserFixture.csproj` con SDK 10.0.402 y paquetes bloqueados.

Definir las siguientes variables **solo en la sesión local PowerShell**, sin registrarlas ni imprimir valores:

| Variable | Uso |
|---|---|
| M014B_B2_INTERACTIVE_APPROVAL | Valor exacto `APPROVED_HOSTED_AUTH_DEV_NO_TRADE` |
| M014B_B2_PROJECT_REF | `ocwabwmzhpedyxlkjpje` |
| M014B_B2_PROJECT_URL | `https://ocwabwmzhpedyxlkjpje.supabase.co/` |
| M014B_B2_PUBLISHABLE_KEY | Clave pública **publishable** |
| M014B_B2_ORIGIN | `https://127.0.0.1:<puerto> /` sin espacio antes de `/`; puerto 20000-65535 |
| M014B_B2_SQL_PORT / M014B_B2_SQL_DATABASE | Puerto y nombre marcados del PostgreSQL desechable |
| M014B_B2_RUNTIME_USER / M014B_B2_RUNTIME_PASSWORD | Credenciales de rol `web_security_runtime` solamente |
| M014B_B2_ISSUER_USER / M014B_B2_ISSUER_PASSWORD | Credenciales de rol `identity_session_issuer` solamente |
| M014B_B2_TLS_PFX / M014B_B2_TLS_PASSWORD | Archivo PFX fuera del repositorio y su contraseña |
| M014B_B2_REACT_DIST | Ruta absoluta al `frontend-react/dist` compilado |

Solo si se autorizó la **prueba real alojada**:

```powershell
dotnet build/react-bff/BrowserFixture/bin/Release/net10.0/BrowserFixture.dll --hosted-development
```

El proceso inicia Kestrel y permanece hasta Ctrl+C; no aprovisiona SQL, ni hace login por sí mismo. El usuario solo introduciría credenciales de desarrollo en el navegador si existe autorización adicional. No usar para producción.

**Pendientes de validación:** compilar el nuevo launcher en CI limpia; comprobar SAN/chain con fixture compatible, confirmar comportamiento frente al factor TOTP real sin mutaciones y diagnosticar rechazo JWT con códigos redactados. No existe autorización de iniciar sesión real por el mero hecho de implementar el código.
