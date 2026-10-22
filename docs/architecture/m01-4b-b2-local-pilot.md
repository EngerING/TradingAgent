# M01.4B-B2 — preparación local controlada en Windows

Base integrada develop: e4e2cd9e28b4a885c744a27a2f4b4e5dc5a5d33a.
Rama: feature/m01-4b-b2-local-pilot. OFFLINE / NO_TRADE.
No merge ni despliegue. Solo proyecto Auth Dev ocwabwmzhpedyxlkjpje y SQL desechable.
La implementación no acredita un login alojado exitoso.

## Recursos y separación de autoridad

`build/react-bff/local-pilot.ps1` crea un directorio nuevo por RunId bajo
tmp/m014b-local-pilot/runs. Rechaza rutas fuera del contenedor, reparse points,
RunId/propietario/marcador/versiones incompatibles y cualquier sobrescritura.
ACL exclusiva del usuario antes de escribir secretos; contraseñas aleatorias de256bits,
DPAPI de CurrentUser, PFX protegido y ningún secreto en argumentos de proceso/Git.
El password temporal de initdb se retira al terminar initdb. No se usa .local.
Los strings/variables de entorno del proceso no constituyen aislamiento frente al
propietario del host ni una garantía de borrado físico del heap.

Clúster PostgreSQL17 independiente: puerto dinámico alto, listen127.0.0.1,
SCRAM-SHA256, cluster_name=m012_disposable_<RunId>. Se comprueba el marcador
antes de DDL y se crea una base m012_test_<GUID> con comentario de identidad.
Se reutilizan las migraciones M01.2 originales, sin editar ningún SQL.
Solo hay logins técnicos Migration, Runtime y SessionIssuer, separados; los grupos
Administration/Reader existen como NOLOGIN para las referencias del esquema.
No se crea usuario de aplicación, vínculo de identidad, rol de usuario, recurso o
grant de aplicación. Se comprueba que esas tablas permanezcan vacías. El BFF nunca
recibe la contraseña bootstrap/migration y no se ejecuta bootstrap de app_security.
El login no aprovisiona permisos. Una futura asociación/activación SQL del usuario
necesita revisión y aprobación separadas; AAL2 por sí solo no autoriza sesión local.

Certificado: CA nueva de4h, leaf3h, SAN IP127.0.0.1, serverAuth, private key RSA3072.
La clave de CA se dispone sin exportarla. Se validan SAN/EKU/cadena/fechas con
CustomRootTrust SOLO al preparar/tests. El runner alojado exige confianza OS normal,
serverAuth explícito y no acepta certificados arbitrarios. No callbacks permisivos,
ignoreHTTPSErrors, trust LocalMachine ni exportación de clave privada a artefactos.
PFX únicamente en el directorio privado, cuya contraseña está protegida por DPAPI.
No se cambia confianza automáticamente: Trust muestra un diálogo local Yes/No,
No por defecto, con thumbprint exacto antes de instalar esa CA pública en
CurrentUser Root. La aprobación se registra por un recibo de propiedad específico.
Una CA ya existente no se reclama como propia. Cleanup solo retira esa coincidencia
exacta y vuelve a exigir confirmación local antes de modificar el almacén.

Se observó que el pg_ctl nativo heredaba handles y bloqueaba el pipeline de
Windows PowerShell5 aunque el servidor ya estuviera ready. El launcher nuevo
redirige a archivos y espera solamente al controlador, reteniendo su handle para
leer ExitCode correctamente. No se editan los wrappers históricos para resolverlo.

## Composición y datos del navegador

React compilado y BFF se sirven en https://127.0.0.1:<puerto-dinámico>/.
No Vite para contraseñas reales, SDK Supabase cliente, proxy financiero ni HTTP.
Se conserva HOSTED_DEVELOPMENT_AUTH, el diseño aprobado, Origin exacto, CSRF,
cookies __Host Secure/HttpOnly/Strict y CSP same-origin. El BFF mantiene JWT solo
en memoria; no conserva refresh_token. Browser solo maneja cookies opacas.
El perfil alojado browser ahora deniega enrollment en el servidor antes de acceder
al proveedor, incluso si se observa inventario vacío. No existe DELETE browser.
Un factor unverified previo o inventario ambiguo sigue bloqueando el flujo B1.
No se recupera, reemplaza o crea factor por efectos de este launcher.

`Run` exige una SEGUNDA confirmación local, separada de Trust, antes de arrancar
el perfil alojado. Informa proyecto, origen, límite20min, factor pendiente y SQL
sin autorización de aplicación. La configuración pública local se lee de
tmp/m013b/hosted-development.public.json sin imprimirla; se comprueba referencia,
URL exacta y publishable key. No se aceptan service_role/secret keys. No se cambian
Site URL/Redirect URLs/plantillas/usuarios/passwords/factores ni sesiones ajenas.
Cada proceso admite un solo POST de login; otro intento devuelve409 sin proveedor.
Arrancar el host no hace login automáticamente. Credenciales solo en React HTTPS
después del consentimiento; nunca chat, CLI, archivos, HAR, screenshots o traces.

## Diagnóstico JWT y sesión

JwtVerifier/JwksCache/AuthTransport/SupabaseAuthClient permanecen intactos respecto
a la base integrada. Se mantienen ES256/P-256, kid/JWKS, issuer/audience, claims,
exp/nbf/iat, session_id, AAL, AMR, duración y cero ClockSkew. El rechazo histórico
PASSWORD200/JWKS200/Unspecified no tiene causa demostrada: un flag iat futuro
decodificado sin verificar no basta. No se repite ni se corrige por conjetura.

El BFF conserva errores públicos genéricos. Un logger específico del launcher
acepta exclusivamente eventos internos1301/1302/1303: operación cerrada+status,
AuthDiagnostic tipado, o JWT_USER_ACCEPTED con conteos verified/unverified.
Nunca ejecuta el formatter ni escribe excepciones, identificadores, claims,
cuerpos, headers, cookies o secretos; máximo1024 líneas por proceso. Archivo
diagnostic.jsonl dentro del directorio protegido, excluido de CI/Git.
JWT_USER_ACCEPTED se emite después de PasswordAsync/JwtVerifier y CheckUserAsync:
prueba la llegada a ese punto, no AAL2 ni autorización SQL ni vigencia remota.
Un fallo de preflight imprime únicamente código fijo, sin stack trace sensible.

La sesión continúa exigiendo MFA reciente, identidad/session_id concordantes,
factor verificado, app_security.create_session y posterior GET/bff/session con
self_user/Active. SQL desconocido/inactivo/caído deniega. Sin grants automáticos,
refresh ni promesa de revocación remota inmediata. providerSessionConfirmedActive
sigue false; logout durable local no prueba logout remoto. No acceso financiero.

## Reproducción y cierre

Desde raíz, SDK10.0.402, Node24.20.0/npm12.2.0, PostgreSQL17. Los binarios Node/npm
pueden ser portables en tmp, con hash oficial comprobado, sin cambiar PATH global,
NVM ni instalaciones. Primero restore/build bloqueados y frontend verify/e2e.
El preparador requiere BrowserFixture.dll Release previamente compilado.

```powershell
./tmp/m011/dotnet/dotnet.exe restore build/react-bff/BrowserFixture/BrowserFixture.csproj --locked-mode
./tmp/m011/dotnet/dotnet.exe build build/react-bff/BrowserFixture/BrowserFixture.csproj --no-restore -c Release --warnaserror
./build/react-bff/local-pilot.ps1 -Mode Prepare
# Sustituir RUNID por los32hex impresos al preparar; nunca una ruta.
./build/react-bff/local-pilot.ps1 -Mode Verify -RunId RUNID
./build/react-bff/local-pilot.ps1 -Mode Trust -RunId RUNID
# Solo si se aprueba explícitamente el segundo diálogo local:
./build/react-bff/local-pilot.ps1 -Mode Run -RunId RUNID
# Desde otra consola; el runner responde a este archivo y apaga su clúster:
./build/react-bff/local-pilot.ps1 -Mode Stop -RunId RUNID
# Esperar salida del runner y clúster; después confirmar retiro de CA propia:
./build/react-bff/local-pilot.ps1 -Mode Cleanup -RunId RUNID
```

Prepare/Verify apagan su clúster al terminar. Run usa Ctrl+C, archivo stop o
deadline20min y un finally para apagar su PostgreSQL; ante caída del proceso
propietario conservar directorio y revisar su estado, sin matar procesos ajenos.
Cleanup rechaza clúster activo y cualquier propiedad dudosa. No borra directorios
antiguos, bases operativas, certificados ajenos ni documentos del usuario.

Verify ejecuta266 backend históricos,20 backend de integración (15 originales B2
+5 nuevos) y smoke TLS sintético en base de tests separada. Los fixtures de pruebas
sí crean identidades sintéticas en sus propias bases efímeras; no aprovisionan la
base reservada al piloto alojado. React tiene29 unitarias+20E2E; Chromium HTTPS
integrado24 se acredita por CI. Total esperado distinto359, sin doble contar
ejecuciones de unidades React. Mantener todos los casos previos y cero omitidas.
Cinco casos nuevos: certificado correcto; TLS inválido; logins técnicos limitados;
redacción sin formatter/excepción; enrollment alojado denegado sin proveedor/SQL.

Se añade guard estricto desde e4e2cd9 con allowlist de estas rutas; siguen pasando
las barreras históricas y protección de main, Core, Market Analyst, Vue, SQL
operativo, diseño y build histórico. Resultados finales/commit/tree/CI y estado
de intervención alojada se entregan aparte con evidencia local redactada.
