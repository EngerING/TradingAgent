# M01.3A — ADR: sesión temporal y composición aislada

Base aprobada: f4130ea9671da9b0990ac62bff40a9aa83f60e4d.
OFFLINE / NO_TRADE. Diseño previo a implementación.

Se añaden Identity.Supabase y Web.Auth; WebHostFactory, sus21 pruebas y toda la
persistencia/SQL de M01.2 quedan intactos. La composición integrada es explícita
y solo admite el piloto sintético. Program.cs histórico continúa cerrado.

El access token vive únicamente en memoria del servidor con TTL máximo igual
a exp; no se retiene refresh token ni se implementa refresh. La respuesta del
proveedor necesariamente pasa por un buffer acotado de servidor, pero su refresh
token se descarta al analizarla. No se ofrece persistencia cifrada improvisada.
Los campos SQL reservados siguen NULL. Una caída/reinicio pierde los tokens y
deniega sesiones previas, aunque sus filas SQL sigan existentes hasta expirar.
Las cookies contienen referencias aleatorias opacas, separadas para preauth y
sesión. El almacén limita entradas y las elimina al vencer; las mutaciones de
preauth se serializan y cada challenge se consume antes de enviar verify.

La verificación JWT usa IdentityModel, ES256 y endpoints derivados de configuración
confiable, no de claims. Identidad/issuer/session_id se ligan entre password,
challenge, verify, token conservado y PostgreSQL. La frescura de MFA procede de
amr(method=totp,timestamp) firmado, nunca de la hora local de consulta. Reloj
actual solo comprueba antigüedad y caducidad. El JWT aal1 no emite sesión SQL.

GET /user prueba identidad online, no demuestra la existencia de auth.sessions.
No existe introspección pública inventada ni conexión directa a la base Supabase.
La rotación JWKS tampoco acredita revocación inmediata. Sin esa garantía se
deniegan operaciones sensibles; M01.3A solo expone un probe sintético tras grants
SQL exactos. Las pruebas simulan tanto rechazo remoto como un token que sigue
aceptado por /user después de logout, dejando visible la limitación. Comprobar
logout/password-change/otro dispositivo reales queda bloqueado hasta M01.3B.

Logout revoca localmente en SQL antes de retirar el bearer de memoria y borrar
cookie; una caída remota no restaura acceso. Si SQL está caído se elimina la
capacidad local y se responde503, sin afirmar revocación durable confirmada.
No hay reintentos de mutaciones cuyo commit sea incierto. El lease HTTP es
puntual: no puede retirar una respuesta ya autorizada; no hay streams financieros.

CSRF de ASP.NET con DataProtection efímero exclusivamente para antiforgery,
cookieSecure/HttpOnly/Strict, origen HTTPS y host exactos, FetchMetadata, límites
globales y de preauth, no-store y error fijo. No login público sin CSRF.

Fuentes consultadas: [sesiones](https://supabase.com/docs/guides/auth/sessions),
[claims y amr](https://supabase.com/docs/guides/auth/jwt-fields),
[OpenAPI Auth](https://github.com/supabase/auth/blob/master/openapi.yaml),
[antiforgery ASP.NET10](https://learn.microsoft.com/en-us/aspnet/core/security/anti-request-forgery?view=aspnetcore-10.0).
