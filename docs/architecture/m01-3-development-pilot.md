# M01.3B — preparación del piloto, no ejecutado

**Pendiente de auditoría independiente y aprobación adicional. OFFLINE / NO_TRADE.**
No se creó un proyecto Supabase, usuario, invitación, factor o sesión real.
M01.3A solo compone Auth simulado con PostgreSQL desechable.

Información pública que hará falta después de aprobar M01.3B: URL/referencia de
proyecto exclusivamente de desarrollo, issuer exacto, audiencia, JWKS asimétrico
ES256 y clave publishable pública. También dominios/callbacks HTTPS autorizados,
políticas de invitación/MFA y expiración. No enviar contraseñas, service_role,
JWT, refresh token, claves de firma o secretos TOTP por chat. Los secretos se
aprovisionarán mediante un mecanismo externo del host que debe revisarse antes.

Pasos que NO se han ejecutado:

1. Revisar la composición de host real: el entrypoint histórico y
   CreateSyntheticPilot permanecen cerrados a un proyecto real. No hay un flag de
   entorno que salte esa frontera. El piloto futuro necesita un cambio aprobado.
2. Configurar proyecto de desarrollo por invitación, registro público/Google
   deshabilitados, claves asimétricas y TOTP obligatorio. Confirmar permisos y
   límites sin otorgar roles internos desde claims. No copiar datos financieros.
3. Usar HTTPS real del mismo origen. PostgreSQL continuará desechable salvo otra
   aprobación: M01.2 aún rechaza destinos operativos. Crear identidades internas
   y grants ficticios mediante bootstrap/admin fuera de banda, nunca primer usuario
   ni un token administrativo legacy. No tocar once migraciones financieras.
4. Contrastar OpenAPI y formato JWT/JWKS/AMR con la versión alojada. Probar
   totp/mfa-totp con timestamps, factor unverified/verified, enrolamiento huérfano,
   challenge vinculado y revocación tras MFA. No guardar capturas con secretos.
5. Medir semántica real de GET user tras logout, password change y revocación
   desde otro dispositivo. Si sigue aceptando JWT, conservar bloqueadas acciones
   sensibles y diseñar una prueba de sesión activa autorizada; no inventar
   introspección ni consultar auth.sessions por la base independiente.
6. Ensayar rotación JWKS con standby/espera de propagación y caída. La caché local
   no elimina la del CDN y no prueba revocación inmediata.
7. Diseñar recovery/invitación con PKCE y canje único antes de habilitar esas
   rutas. Rechazar redirect externo y no elevar desde recovery. Logout-all y
   cualquier vault durable/cifrado persistente requieren diseño/aprobación propios.
8. Revisar proxy/TLS, reloj, logging redactado, cuotas distribuidas, protección
   de claves y recuperación operacional antes de despliegue. No hay despliegue
   autorizado, UI React, migración operativa, IBKR, PaperAuto o Live.

El piloto actual no renueva sesiones: lease máximo5min desde contraseña y nunca
supera el JWT disponible. Reiniciar el almacén temporal fuerza nuevo login/MFA.
Rollback consiste en volver a la composición M01.1 cerrada y desechar el estado
temporal; no borrar auditoría SQL. Una copia de seguridad operacional y un vault
durable no están implementados ni se infieren de las pruebas desechables.

| Estado | Alcance |
|---|---|
| Implementado | Adaptador HTTP Auth, validación criptográfica, flujo MFA/BFF, sesión/grants SQL, CSRF y límites. |
| Probado con simulado | Flujo HTTP completo, errores, JWT/JWKS efímeros, concurrencia/revocación y PostgreSQL17 real desechable. |
| Probado con Supabase real | Ninguno. |
| Pendiente de autorización | M01.3B y cualquier despliegue o destino operativo. |
| Pendiente de infraestructura | Proyecto desarrollo, HTTPS, aprovisionamiento externo y garantía de sesión remota. |
| No soportado en M01.3A | Refresh/vault durable, Google/registro público, recovery/invitaciones activas, logout-all, endpoints financieros. |
