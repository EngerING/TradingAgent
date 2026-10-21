# M01.3B — Suite B alojada pendiente

**B2 iniciada parcialmente: solo preflight público de lectura. Login/MFA aún no ejecutados.**
El usuario confirmó un proyecto exclusivamente de desarrollo y autorizó B2.
No se seleccionaron proyectos automáticamente ni se creó proyecto, usuario,
factor o sesión real. Ninguna evidencia sintética constituye validación alojada.
Referencia, URL, región y publishable key se conservan en configuración local
ignorada, fuera de Git y artefactos. Se validó el formato y se consultaron por
HTTPS los endpoints públicos Auth settings/JWKS. El transporte/cache reales del
producto también obtuvieron y analizaron la clave: ES256/P-256, un key. Email
habilitado, Google deshabilitado. No se consultaron usuarios ni sesiones.
El registro público sigue habilitado: se solicitó al usuario desactivarlo desde
el panel, porque no hay panel conectado ni se dispone de autoridad administrativa.
No se piden claves secret/service_role para resolverlo. Login/MFA se mantienen
pendientes de ese ajuste, TOTP/cuenta ficticia y canal local seguro. CI normal
continúa sin configuración ni conexiones alojadas. [Preflight redactado](m01-3b-hosted-preflight.json).

Datos públicos necesarios: referencia exacta20 caracteres, URL HTTPS
`https://<ref>.supabase.co`, issuer derivado `/auth/v1`, audiencia fija
`authenticated`, JWKS derivado `/auth/v1/.well-known/jwks.json`, ES256, y clave
publishable aportada externamente. No se aceptan secret/service_role ni HS256.
La confirmación de entorno de desarrollo procede del usuario/host confiable;
un hostname no demuestra por sí solo si el proyecto se usa en producción.

Aprovisionamiento pendiente, independiente del runtime BFF:

1. Confirmar proyecto/costo antes de crear recursos. Revisar email/password,
   TOTP habilitado, registro público y proveedores sociales deshabilitados para
   el piloto. Usar únicamente identidades ficticias Admin, Alice y Bob.
2. Un administrador del proyecto puede preparar esas identidades por el panel
   de desarrollo con privilegios mínimos. No entregar al BFF su clave secreta.
   No inferir roles internos desde claims o del primer usuario registrado.
3. Preparar certificado HTTPS con SAN127.0.0.1, clave fuera de Git y trust local
   revisado. El host recibe el objeto X509Certificate2; no lee PFX ni instala
   certificados por su cuenta. Configuración del BFF de origen único y puerto
   alto, sin CORS/proxy/forwarded headers. No exponerlo a Internet.
4. Crear un PostgreSQL17 nuevo con marcador desechable como los fixtures; nunca
   usar conexión financiera habitual. Reutilizar esquema app_security y roles
   mínimos de M01.2. Bootstrap/admin se mantienen fuera del runtime.
5. Componer explícitamente HostedPilotSettings.FromExternalValues("Development",
   referencia confirmada, URI proyecto, publishable externa, URI HTTPS loopback)
   y CreateHostedDevelopmentPilot(settings,runtime,issuer,certificado). El host
   histórico y CreateSyntheticPilot permanecen separados. No hay flag ambiental
   que convierta una ejecución sintética en alojada, ni CLI que arranque B2 en CI.
6. Obtener CSRF por el canal HTTPS local. Password y códigos OTP se introducen
   únicamente en el canal local autorizado, nunca en chat, argumentos de shell,
   capturas, logs, evidencias ni artefactos. Si hace falta escanear el secreto
   TOTP, detener el flujo para intervención local; no solicitarlo por chat.

Matriz de medición que debe completarse después de confirmar infraestructura:

| Caso | Evidencia mínima redactada | Estado |
|---|---|---|
| TLS y JWKS | HTTPS200, ES256/P-256, parser/transporte del producto | PASS parcial B2 |
| Password, user, JWT | firma/issuer/aud/sub/session_id/iat/exp/nbf/role/is_anonymous | Pendiente B2 |
| Enroll/challenge/verify | AAL1 denegada, factor propio, amr firmado fresco, AAL2 y cookie opaca | Pendiente B2 |
| Código erróneo/replay/factor ajeno | HTTP genérico y ausencia de sesión SQL concedida | Pendiente B2 |
| Admin/Alice/Bob | issuer+subject, roles/grants exactos, Paper/Live sintéticos y separación usuarios | Pendiente B2 |
| Logout local | capacidad local retirada y SQL revocado, incluso con IdP caído | Pendiente B2 |
| Logout otro dispositivo/global | aceptación/rechazo de JWT y GET user antes/después; sin guardar tokens | Pendiente B2 |
| Password change/revocación | tiempos/estado HTTP, nunca asumir invalidación inmediata | Pendiente B2 |
| Expiración/reinicio | cookie obsoleta recuperable con nuevo password/MFA, sin reutilizar referencia | Pendiente B2 |
| Rotación JWKS/caída | propagación/TTL/bloqueo y rechazo criptográfico; sin debilitar claims | Pendiente B2 |
| PostgreSQL caído/concurrencia |503/conflicto, atomicidad y sentinel financiero intacto | Pendiente B2 |

No se usa acceso directo a auth.sessions, introspección privada, Supabase DB,
Storage ni Realtime. Si falta un claim o garantía suficiente, se detiene ese
flujo y se registra incompatibilidad; no se elimina su validación. Las rutas
sensibles siguen ausentes y providerSessionConfirmedActive=false hasta demostrar
una comprobación soportada. Logout global/password change para esta medición
requieren acciones de prueba explícitas fuera del BFF; no se habilitan endpoints
administrativos de conveniencia. No se promete que GET user detecte cada caso.

Suite A automatizada y Suite B manual/alojada son estados separados: preflight
público ejecutado, cero pruebas alojadas de login/MFA; ninguna se marca skip dentro de CI. Con el
proyecto ya confirmado, el mecanismo local de entrada de credenciales, certificado,
ajustes Auth y el plan de medición deben concretarse antes de B2.
