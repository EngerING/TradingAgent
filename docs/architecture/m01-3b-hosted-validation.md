# M01.3B — Suite B alojada pendiente

**B2 NO EJECUTADA. No hay proyecto de desarrollo confirmado en esta entrega.**
No se seleccionaron proyectos automáticamente ni se creó proyecto, usuario,
factor o sesión real. Ninguna evidencia sintética constituye validación alojada.
El usuario autorizó desarrollar el piloto y condicionó su ejecución a confirmar
un proyecto exclusivamente de desarrollo. B1/CI no necesitan esa configuración.

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
| Password, user, JWKS | TLS/endpoint esperado, firma/issuer/aud/sub/session_id/iat/exp/nbf/role/is_anonymous | Pendiente B2 |
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

Suite A automatizada y Suite B manual/alojada son estados separados: cero pruebas
alojadas ejecutadas; ninguna se marca skip para ocultarlo dentro de CI. Una vez
confirmado el proyecto, el mecanismo local de entrada de credenciales y el plan
de medición deberán concretarse antes de iniciar conexiones alojadas.
