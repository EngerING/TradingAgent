# M01.3B — validación alojada B2 parcial

**B2 parcial; no aprobada.**
El usuario confirmó un proyecto exclusivamente de desarrollo y autorizó B2.
No se seleccionaron proyectos automáticamente ni se creó proyecto o usuario.
Ninguna evidencia sintética constituye validación alojada.
Referencia, URL, región y publishable key se conservan en configuración local
ignorada, fuera de Git y artefactos. Se validó el formato y se consultaron por
HTTPS los endpoints públicos Auth settings/JWKS. El transporte/cache reales del
producto también obtuvieron y analizaron la clave: ES256/P-256, un key. Email
habilitado, Google deshabilitado. El registro público ahora está deshabilitado:
se confirmó `disable_signup=true` por HTTPS. El usuario confirmó TOTP y cuenta
ficticia preparados. No se piden claves secret/service_role. CI normal
continúa sin configuración ni conexiones alojadas. [Preflight redactado](m01-3b-hosted-preflight.json).

Los primeros dos intentos interactivos se detuvieron en password: el primero
reportó `AuthFailure.Invalid` sin diagnóstico HTTP y el segundo HTTP400. No se
conservó el cuerpo para inferir su causa. El usuario confirmó haber corregido
la cuenta y autorizó otro intento local. No hay reintentos automáticos ni se
relajan los controles JWT/MFA. El estado vigente consta en el JSON de evidencia.

El tercer intento validó password, firma/claims del JWT AAL1 y GET user con el
código de producto sin cambios. Se creó únicamente una base desechable y sus
fixtures de seguridad; la emisión de sesión para la identidad real AAL1 fue
denegada. Después se detuvo con `AuthFailure.Unavailable` antes de mostrar TOTP.
No hay AAL2 ni revocación real validados. El logout de limpieza recibió204,
se eliminó la base de prueba y se detuvo su cluster. Ese204 no prueba por sí
solo que un JWT previamente emitido sea rechazado inmediatamente.

El observador anterior agrupaba MFA/logout en una clave HTTP: la limpieza
sobrescribió el diagnóstico necesario. No se infiere la causa del fallo ni se
declara incompatibilidad del proveedor. El auxiliar ahora separa enroll,
challenge, verify y logout, y registra intentos, tipo de contenido y booleanos
del tamaño declarado sin conservar cuerpos. Su prueba sin red confirma esas
fronteras. No se cambia el timeout ni el límite64KiB del transporte protegido.
Se solicitó revisar localmente la cuenta ficticia por si quedó un factor no
verificado; no se repite enrollment ni se elimina un factor verificado.

El auxiliar Windows bajo `build/auth-pilot/HostedRunner/` recibe email/password
y TOTP mediante un formulario local, borra los campos y no exporta valores ni
capturas. No instala React ni modifica la UI del producto. Las credenciales
permanecen en memoria administrada durante la medición: no se promete borrado
forense de strings ni aislamiento frente al dueño del host. Los diagnósticos
conservan únicamente estados HTTP y booleanos de compatibilidad. Decodificar
un JWT sin verificar para diagnóstico nunca concede autoridad.

El wrapper exige raíz del repositorio y SDK10.0.402, restaura en locked mode,
compila Release con advertencias estrictas y crea un cluster PostgreSQL17 nuevo,
marcado, con puerto alto aleatorio y credenciales efímeras. Solo después de
validar password/JWT crea su base aleatoria `m012_test_*`, reutiliza el esquema
de seguridad autorizado de M01.2 y prepara roles/grants ficticios. No conecta
el PostgreSQL habitual ni Supabase DB. Su finally elimina el archivo temporal
de password y detiene exclusivamente ese cluster.

La prueba local HTTPS falla cerrada: Windows Schannel rechaza la clave efímera
del listener. No se instalaron certificados, persistieron claves ni eludió TLS.
El usuario eligió continuar Auth/JWT/MFA/SQL directos y dejar HTTPS BFF pendiente
de un certificado compatible aprovisionado externamente. El auxiliar Windows
mantiene esa separación. La prueba fallida de TLS no valida cookies del BFF.

Reproducción manual explícita desde la raíz; requiere configuración pública
local ignorada, binarios PostgreSQL17 y participación humana. Nunca en CI:

```powershell
./build/auth-pilot/run-hosted.ps1
```

Intenta password/JWT AAL1 y GET user, rechazo AAL1 para sesión SQL, factor propio
existente o enrollment si no existe, TOTP local, JWT AAL2/frescura, sesión SQL,
grants exactos y revocación local. Mide scopes Auth local/others/global de la
cuenta ficticia. Un error de dependencia o rate limit queda inconcluso; GET user
aceptado no se presenta como garantía universal de sesión remota activa.
Conserva factores verificados y solo intenta retirar el factor no verificado
creado por esa misma ejecución. Logout remoto de limpieza es best effort y
acotado; una caída o rechazo del contrato tras emitir un token puede requerir
revisión manual de las sesiones de desarrollo. Exit0 del auxiliar significa
mediciones seleccionadas terminadas con casos pendientes, nunca aprobación B2.

Comprobación del redactor sin red ni configuración alojada:

```powershell
./tmp/m011/dotnet/dotnet.exe exec ./build/auth-pilot/HostedRunner/bin/Release/net10.0-windows/HostedRunner.dll --redaction-self-test
```

Pasó con un JWT fixture sin firma válida y marcadores privados: ningún token,
issuer ni marcador llegó a la evidencia y no se concedió autoridad. Es una
comprobación del auxiliar, fuera del conteo xUnit y de los logins reales.

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
| Password, user, JWT | firma/issuer/aud/sub/session_id/iat/exp/nbf/role/is_anonymous | PASS real AAL1 en intento3; AAL2 pendiente |
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

Suite A automatizada y Suite B manual/alojada son estados separados. Los casos
B2 pendientes no son skips silenciosos ni se cuentan entre las190 pruebas de
Suite A. CI no recibe credenciales alojadas ni ejecuta este auxiliar interactivo.
