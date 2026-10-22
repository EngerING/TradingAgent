# M01.4B-B3 — Inicio de sesión alojado, prueba controlada

**Objetivo:** reconocer correctamente la diferencia entre diagnóstico HTTPS local sin login y el piloto de autenticación real con Supabase Auth Dev, manteniendo OFFLINE / NO_TRADE.

## Estado de implementación

- `https://127.0.0.1:<puerto>/` puede servir React en dos modos mutuamente excluyentes. El servidor `--hosted-local-checks` responde `/bff/config` con `HOSTED_LOCAL_CHECKS_ONLY`, deshabilita el formulario en React y deniega auth, MFA, CSRF, sesión y toda solicitud no permitida en servidor.
- El servidor `--hosted-development` responde `HOSTED_DEVELOPMENT_AUTH` y permite **como máximo un intento de contraseña** contra el proyecto de desarrollo alojado `ocwabwmzhpedyxlkjpje`, únicamente tras aprobación interactiva local independiente. No hay llamadas a Supabase al iniciar el host. React solo usa BFF mismo-origen HTTPS, no supabase-js ni tokens en JS.
- El pie de página representa los perfiles alojado, local-only, sintético y demo sin afirmar que hosted usa un fixture.
- Siguen habilitados CSRF, cookies `__Host`, JWT ES256/JWKS estricto, protección ante TOTP `unverified`, sin DELETE/recovery/re-enroll y `app_security` sin permisos de usuario. **No es posible certificar una sesión AAL2 autorizada con las tablas app_users/user_roles/resource_grants vacías.**
- El diagnóstico antiguo `JwtIssuedAtFuture` permanece pendiente. No se alteraron reloj, ClockSkew, verificación criptográfica, roles ni grants.
- El servidor alojado termina a los 20 minutos como máximo; las pruebas de GitHub siguen usando exclusivamente fixture y SQL desechable.

## Ejecución manual en Windows, SOLO desde el repositorio actualizado y una vez aprobada la prueba alojada

```powershell
$pilot = 'f8220d8277684bc894c70add84aa381f'
./build/react-bff/serve-local.ps1 -Mode Stop -RunId $pilot
./build/react-bff/serve-local.ps1 -Mode Status -RunId $pilot
```

Se exige comprobar que el BFF y el PostgreSQL de ese RunId están detenidos. **No** ejecutar `local-pilot.ps1 -Mode Run` mientras `serve-local.ps1` está activo: ambos usan el mismo clúster y origen. Si el certificado expiró, detenerse; la confianza/renovación requiere confirmación separada. Antes de introducir contraseñas, verificar hora UTC de Windows con utilidades nativas y el certificado, pero nunca compensar `JwtIssuedAtFuture` ampliando `ClockSkew`.

Tras confirmar la confianza del certificado **vigente**, la identidad del recurso y una nueva aprobación en el diálogo Windows:

```powershell
./build/react-bff/local-pilot.ps1 -Mode Run -RunId $pilot
```

Este comando restaura DPAPI y credenciales técnicas únicamente en el proceso local, arranca PostgreSQL marcado y el BFF, muestra la URL HTTPS e informa la política de 20 minutos. Teclear URL manualmente sin query ni fragmento. **Solo entonces** introducir el usuario y contraseña de pruebas en Chrome. Un único POST login: no automatizar retries ni capturar tráfico con secretos. El código M01.4B-B2 existente también detiene la admisión si hay TOTP incompleto/ambiguo y deniega el enroll alojado antes del proveedor.

Interpretación de resultados redactados:
- `HOSTED_AUTH_REJECTED:JwtIssuedAtFuture`: JWT rechazado. No atribuir causa sin diagnóstico temporal documentado; no debilitar validación.
- `HTTP 401`: credenciales o JWT rechazados, no inferir más sin código de diagnóstico.
- `HTTP 409`: intento consumido o conflicto MFA; revisar código cerrado, nunca borrar factores.
- `MFA_REQUIRED` con verified: primer factor aceptado pero aún sin sesión; continuar solamente con el autenticador original y challenge/verify autorizados.
- Sesión completa: requiere AAL2 y `app_security`; sin autorización previa la denegación es correcta.

La prueba no permite cambios en Supabase remoto, TOTP, Site URL, usuarios, roles financieros, deploy, trades ni IBKR. No adjuntar logs privados, DPAPI, cookies, JWT, headers, credenciales, PFX o QR a informes. Emitir solo estados y códigos cerrados. Restaurar el modo local-only después, con `serve-local.ps1 -Mode Start` si sigue vigente el certificado.
