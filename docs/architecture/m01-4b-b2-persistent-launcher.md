# M01.4B-B2 — arranque local persistente

2026-10-22 America/La_Paz. OFFLINE / NO_TRADE.
Base develop e4e2cd9e28b4a885c744a27a2f4b4e5dc5a5d33a.
Rama feature/m01-4b-b2-persistent-launcher; PR Draft sin merge.
La PR4 continúa separada: esta rama no importa ni integra sus cambios pendientes.

## Cierre anterior: evidencia

El runner del commit cf515b1 tenía CancellationTokenSource(TimeSpan.FromMinutes(20)).
La ejecución anterior terminó exit_code0. El PostgreSQL de esa ejecución registró
ready a00:55:17 y shutdown ordenado a01:15:18. El cierre del listener correspondió
al deadline del piloto y al finally que apagaba su clúster, no a un fallo demostrado
de Supabase o MFA. Las variables M014B_B2_* eran locales al proceso de PowerShell,
restauradas al salir y nunca persistidas globalmente; su ausencia en una terminal
nueva es esperada. No es pérdida de la configuración DPAPI guardada.

El diagnóstico anterior contiene, por separado, JwtIssuedAtFuture y AUTH401; los
intentos siguientes devolvieron409 por el límite de un login. Ese rechazo JWT no
fue la causa de terminar el host. No se cambia JwtVerifier, reloj o ClockSkew ni se
repite el intento alojado. El factor TOTP no se consulta ni modifica aquí.

## Comando reutilizable

`build/react-bff/serve-local.ps1` tiene Start, Status y Stop. RunId es únicamente
los32hex del recurso previamente preparado, nunca una ruta ni credencial.

```powershell
# Desde la raíz. RUNID identifica el recurso local ya preparado.
./build/react-bff/serve-local.ps1 -Mode Start -RunId RUNID
./build/react-bff/serve-local.ps1 -Mode Status -RunId RUNID
./build/react-bff/serve-local.ps1 -Mode Stop -RunId RUNID
```

Start abre una consola visible dedicada titulada TradingAgent local-only BFF.
No -Wait, tuberías a Codex, proceso de prueba temporal, servicio, tarea programada,
autostart ni temporizador de20min. La consola ejecuta Foreground y permanece mientras
el BFF escucha. Start puede terminar y otra terminal consultar Status/Stop. Un segundo
Start de la misma instancia válida solo consulta su estado, sin duplicarla.
Windows Start-Process inicia procesos locales independientes del llamador:
https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.management/start-process?view=powershell-5.1

Stop crea únicamente el archivo de control en el directorio privado validado; el
runner cierra Kestrel y su PowerShell apaga PostgreSQL con pg_ctl sobre su directorio
exacto. Espera confirmación de ambos. No mata procesos por nombre/PID/puerto. Cerrar
forzosamente la consola/Windows puede impedir finalmente; ante una salida anormal
se conservan recursos y se rechaza attach implícito. No borrar archivos para forzar
un reinicio sin revisar su propiedad. La consola se cierra al completar Stop.

## Validaciones y secretos

Se reutiliza exclusivamente el formato owner.json/prepared.json/secrets.dpapi del
recurso local previo, sin depender del launcher/runner histórico de recuperación.
ACL protegida exclusiva del propietario, SID/ruta/RunId/marcador exactos, sin reparse
points en ancestros ni hijos; PostgreSQL17 y cluster_name propio. No se acepta un
servidor que ya esté corriendo sin su instancia válida; no se toca una base ajena.

En cada arranque la consola valida SDK10.0.402, restore locked, Release/warnaserror,
build React permitido y certificado vigente. Las contraseñas se descifran con DPAPI
solo en memoria y se pasan al proceso BFF por entorno; no argumentos ni archivos
planos, logs, Git o variables de usuario/sistema. Al salir se restaura el entorno.
No hay garantía de borrado físico del heap ni aislamiento de un dueño del host.

El runner exige proyecto Dev exacto, origen127.0.0.1 HTTPS y SAN IP, serverAuth,
clave privada y cadena OS confiable. No bypass TLS, cambio de confianza, renovación
automática, PFX nuevo ni instalación global. Si expira el certificado, se detiene el
arranque; renovarlo/confiarlo necesita una aprobación separada. Se usa DateTimeOffset
para comparar la fecha UTC del manifiesto, evitando interpretar UTC como hora local.

Antes de escuchar, SecurityDatabase abre Runtime y SessionIssuer separadamente:
comprueba marcador de base, ledger original, membresías y privilegios mínimos. Solo
lecturas de preflight. No migración, bootstrap, usuario de aplicación ni grant nuevo.
Los archivos de restore/build quedan locales ignorados; consola solo muestra códigos
cerrados, URL, PID, READY/STOPPED/FAILED y LOGIN_DISABLED. No excepciones completas.

## Frontera local sin autenticación alojada

La nueva entrada --hosted-local-checks exige LOCAL_STARTUP_CHECKS_ONLY; no reutiliza
una aprobación de login. El constructor recibe localChecksOnly desde el servidor,
nunca query, header o perfil controlado por el navegador.

Después de routing y antes de autenticar, LocalStartupBoundary permite solo GET de
endpoints anónimos mapeados y, entre rutas /bff, exclusivamente /bff/config. Deniega
login, CSRF, factores, verify, sesión, probe, logout y endpoints desconocidos; tampoco
registra UseAuthentication en esta composición. Una cookie vieja no dispara GetUser.
El perfil normal/sintético conserva sus contratos y validaciones originales.

/health entrega status=ok; /bff/config conserva exactamente:
HOSTED_DEVELOPMENT_AUTH, OFFLINE, NO_TRADE, executionAuthorized=false. React se sirve
desde el mismo origen HTTPS; los formularios no otorgan autoridad y sus solicitudes
de autenticación están bloqueadas en servidor. No introducir credenciales en este
modo. Una prueba alojada futura necesita nueva aprobación y composición revisada.

Un observador de ConnectStart del proceso registra intentos SQL y cuenta conexiones
fuera del endpoint loopback declarado. El estado privado atómico incluye PID/fecha
de arranque, localChecksOnly, estado y contadores; nunca secretos. El test local
confirmó dos conexiones de preflight y cero destinos inesperados, parada y reinicio
con PID nuevo y respuestas HTTPS normales desde otra terminal. No es firewall ni
sandbox frente a código malicioso/propietario del host.

## Verificación y preservación

Tres regresiones nuevas, reproducidas inicialmente en rojo por frontera ausente:
GET anónimo permitido; rutas de autenticación/sesión denegadas; cookie antigua y POST
de configuración denegados. Se conservan las15 identidades de tests de develop y
se exigen18 por nombre/TRX, cero fallos/omisiones. CI conserva las266 backend,
29 unitarias React,20 E2E y24 HTTPS sintéticas:357 casos distintos esperados.
La PR4 conserva sus cinco tests propios en su rama, sin borrarlos ni integrarlos aquí.

El guard compara el árbol integrado con allowlist exacto y mantiene las barreras
anteriores. Core V3.9, Market Analyst, Vue, PostgreSQL/migraciones operativas,
componentes financieros, validadores JWT, main y develop permanecen intactos.
Los tres documentos/scripts untracked originales permanecen fuera de los commits.
No se hicieron logins, cambios de usuario/factor/servicio Supabase, IBKR ni despliegues.
