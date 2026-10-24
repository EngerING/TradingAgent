# M03-A.3 — identidad persistente de TWS y renovación DATA_ONLY

Base: `develop` a `3230379de06107b3667eefc24081e9b8ab3ec401`.
Entrega propuesta mediante PR Draft, sin merge, conexión IBKR, órdenes, despliegue
ni autorización de trading. Los tests de CI son offline con cuentas sintéticas.
Los datos auténticos y el comportamiento prolongado requieren pruebas supervisadas
en el host Windows del propietario antes de declarar funcionamiento operativo.

## Objetivo

El operador único registra una vez **cada cuenta** (Paper y Live) y su endpoint.
La identificación guardada **no prueba** cuál sesión de TWS está abierta. En cada
nueva conexión el protocolo restringido solicita `managedAccounts`, verifica
el HMAC del conjunto exacto y solo después puede suscribirse a EUR/USD. Si la
identidad no coincide, se termina la época sin aceptar BID/ASK ni barras.
El puerto es una configuración del host, no una prueba de Paper/Live.

El proceso es independiente del login React y del navegador. Solo se mantiene
activo mientras Windows, el proceso host y TWS estén ejecutándose. No se almacenan
usuario de acceso IBKR, contraseña, OTP ni factor de recuperación.

## Persistencia

`HostVault` almacena perfiles de cuenta en
`%LOCALAPPDATA%\TradingAgent\market-data-host\identities.dpapi`.
El archivo completo se cifra usando DPAPI `CurrentUser`; una cuenta no aparece
en JSON, logs, CI ni artefactos de GitHub. La identidad completa se solicita una
sola vez mediante entrada oculta (no aparecen asteriscos; hay que teclear y Enter).
No se admite una cuenta Paper sin prefijo DU y sufijo 3784 en esta instalación
particular. Live requiere alta independiente; no debe usarse la cuenta Paper.
Reemplazar una cuenta exige el switch explícito `-Replace`. El estado público
solo muestra ambiente, puerto y habilitación.

Al deshabilitar/revocar un perfil se actualiza de forma atómica el vault cifrado.
El colector comprueba su huella y estado al menos cada 1 s durante recepción;
además, crea una nueva firma antes de cada ciclo. Cambiar cuenta, puerto o consentir
solo una de ambas invalida el permiso de la época anterior. Los permisos y claves
efímeros no se almacenan en el repositorio ni en una base operativa.

La protección de DPAPI vincula el archivo al usuario de Windows. Una restauración
en otro perfil u otro equipo no habilita el acceso. Un usuario local malicioso con
la misma identidad de Windows queda fuera del modelo de aislamiento; DPAPI tampoco
constituye control de permisos en el broker.

## TWS y autorizaciones

Se emite `Grant` firmado con HMAC de vigencia 30 minutos y `DataPermit` de
mismo intervalo en memoria, con ámbito adicional
`EURUSD_MARKET_DATA_ONLY_RW_HOST_ATTESTED_V1`. El Core V3.9 original no se
modifica; el permiso v1 ordinario sigue exigiendo `Read-Only API`. Solo el
lector de mercado restringido M03-A acepta la excepción firmada de host cuando
el operador confirmó que TWS tiene `Read-Only API` desactivado.
**No es una garantía de lectura exclusiva a nivel broker**: otros clientes de
TWS podrían enviar órdenes mientras ese checkbox esté desmarcado. El ejecutor
financiero no importa este permiso y nunca obtiene autorización Live.

La lista de comandos de salida existente del lector M03-A sigue intacta,
sin `placeOrder`, `cancelOrder`, `reqGlobalCancel` ni `reqPositions`.
Se mantiene el preflight, perfil de protocolo 157, validación de contrato EUR/USD,
calendario auténtico, calidad/STALE, journal V3.9, cuotas y cierres propios.
Un permiso de lectura Live nunca equivale a `LiveApproved`.

Los ciclos del host duran como máximo 15 minutos con conexión individual
máxima de 120 segundos. Después se obtiene otro permiso de 30 minutos sin
repetir las preguntas, se abre otro archive y se declaran los GAP. Revocación
máxima entre revisiones ~1 s cuando el proceso es receptivo. No se garantiza
continuidad exacta de ticks en los reinicios; M03-B todavía no consume estos
archivos y queda pendiente integrar la proyección multiarchivo.

Se admite `-Environment BOTH` únicamente si **ambas** identidades están
inscritas, con puertos y client IDs separados; cada una usa proceso lógico,
origen y archivos separados. Si falta TWS, el host espera 15 s. Errores de
identidad, protocolo o almacenamiento suspenden la lectura, sin degradar a otra
cuenta ni transformar una excepción en permiso Live. La retención es conservadora:
no hay borrado automático; al alcanzar 10000 archives de un perfil se detiene y
requiere archivado supervisado. No se instala Windows Service o tarea programada.

## Comandos PowerShell en la computadora del propietario

Primero inspeccionar, **sin conectarse a TWS**:

```powershell
.\build\m03a3-host\run-host.ps1 -Action status
```

Para dar de alta una vez la cuenta Paper terminada en 3784 (TWS auténtico
previamente confirmado visualmente):

```powershell
.\build\m03a3-host\run-host.ps1 -Action enroll -Environment PAPER
```

El alta Live requiere una sesión y un identificador real propios, confirmados
localmente, y no se prueba automáticamente por el puerto 7496:

```powershell
.\build\m03a3-host\run-host.ps1 -Action enroll -Environment LIVE
```

Tras auditoría y aprobación supervisada específica para **lectura real**,
operación continua de datos, no de órdenes:

```powershell
.\build\m03a3-host\run-host.ps1 -Action watch -Environment PAPER
# o LIVE/BOTH, con sus perfiles inscritos y TWS abiertos
```

Para suspender persistentemente la lectura de una cuenta, incluso si su sesión
sigue abierta:

```powershell
.\build\m03a3-host\run-host.ps1 -Action revoke -Environment PAPER
```

`Ctrl+C` detiene el watch. El binario Python usa `-B`; no crea secretos en Git.
El script M03-A.2 anterior, de backfill histórico puntual, se conserva intacto:
sus aprobaciones de un solo uso todavía requieren su procedimiento explícito.
M03-A.3 aporta persistencia y renovación **para el colector continuo M03-A**,
no concede automáticamente privilegios al backfill anterior.

## Pruebas y limitaciones

15 pruebas adversariales nuevas: vault cerrado/no existente, inscripción única,
Paper/Live separados, cifrado local, revocación, sustitución, corrupción,
DPAPI auténtico con cuenta sintética en Windows CI, firmas, expiración,
identidad HMAC, scope antiguo bloqueado, manipulación y falta de consentimiento.
Los 572 tests previos siguen ejecutándose en workflows M03-A.2, M03-A y Core.
La CI compila el PowerShell sin ejecutarlo y comprueba blobs preservados por Git.

Pendientes antes de operación continua declarada: prueba TWS auténtica, compatibilidad
perfil 157 real y market-data entitlements, pacing, disponibilidad de calendario y
reconexión real; validar Windows manualmente y observar 24/5; análisis M03-B,
servicio de Windows y política explícita de retención/almacenamiento/backup.
