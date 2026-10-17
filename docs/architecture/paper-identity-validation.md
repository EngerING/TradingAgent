# Entrega C: preparación de identidad local (estado histórico)

Este informe conserva el estado anterior a la autorización manual. La autorización y la primera lectura real ya se completaron: véase [primera lectura auténtica de IBKR Paper](paper-authentic-data-validation.md).

Fecha: 2026-10-04. Se consultó primero Graphify; su índice identificó PaperOptions, PaperDataBroker y managedAccounts en official_wire. La consulta truncada se completó con lecturas selectivas. La corrección de compatibilidad afecta exclusivamente a los filtros de identidad de Python, API y autorización local, sus pruebas y este informe. No se modificaron transporte, riesgo, capital ni persistencia.

TWS continúa ejecutándose. Se realizaron conexiones de diagnóstico oficiales en 127.0.0.1:7497, handshake y reqManagedAccts; servidor API 226. Se recuperó una sola identidad completa, terminada en **3784**. No se imprimió la identidad completa: se conserva únicamente en memoria y en `.local/ibkr-paper-candidate.dpapi`, cifrada con Windows DPAPI para el usuario actual. Se comprobó que PowerShell puede descifrar el formato y que el registro tiene authorized=false. `.local/` ya está excluido mediante `.gitignore`.

No hay prueba fiable del modo Paper ni del checkbox Read-Only mediante el transporte actual. Por instrucción del propietario, las lecturas operativas quedan detenidas hasta documentar la comprobación manual. No se intentó iniciar sesión, modificar TWS ni probar una orden para deducir Read-Only.

## Intervención del propietario

1. En TWS, comprobar explícitamente que la sesión es **Paper Trading**, y consultar el identificador completo de la cuenta. Debe terminar en 3784; la coincidencia completa se comprueba localmente en el siguiente paso.
2. Abrir **Global Configuration → API → Settings**. Verificar **Enable ActiveX and Socket Clients**, **Socket port 7497** y **Read-Only API marcado**. Mantener Read-Only marcado.
3. En una terminal PowerShell desde la raíz del proyecto, ejecutar:

```powershell
.\scripts\paper-identity.ps1 -Action Authorize
```

Introducir la cuenta completa en el prompt de entrada oculta; no enviarla al chat. Escribir PAPER y READ_ONLY únicamente tras comprobar esos estados en TWS. El script vuelve a consultar reqManagedAccts, compara exactamente y registra la autorización y sus timestamps cifrados en `.local/ibkr-paper-authorized.dpapi`. No acepta una terminación, un prefijo o flags de confirmación automáticos. Cualquier diferencia aborta.

La confirmación vence después de 24 horas; repetirla también si cambia o se reinicia la sesión TWS. `-Action Status` muestra solamente la terminación y el estado; `-Action Load` valida el registro y carga variables de entorno del proceso sin activar el colector. Una carga fallida limpia las variables de autorización previas. No ejecutar todavía la demostración real: primero comunicar al asistente que terminó la comprobación.

Una nueva consulta auténtica de reqManagedAccts confirmó que la única identidad recibida tiene formato **DUR seguido exclusivamente de dígitos** y termina en **3784**; servidor 226. El filtro anterior DU numérico causaba el rechazo. PaperOptions, PaperFeedConfiguration y la autorización local ahora admiten exclusivamente DU o DUR seguido de dígitos ASCII, con mayúsculas y coincidencia de toda la cadena. El descubrimiento sigue registrando candidatos sin autorizarlos. El formato **no demuestra** que sea Paper: se mantienen las atestaciones manuales, el puerto/host verificados, la comparación exacta de la cuenta completa, LIVE_TRADING deshabilitado y los bloqueos de órdenes. Coincidir en los últimos cuatro caracteres nunca autoriza una cuenta. No existe todavía un registro local autorizado: la coincidencia real con una identidad autorizada queda pendiente de la intervención del propietario.

Configuración conforme a la [documentación oficial de IBKR](https://www.interactivebrokers.com/campus/trading-lessons/installing-configuring-tws-for-the-api/). El puerto y la forma del identificador son datos de configuración, no prueba definitiva del entorno.

## Cambios y verificación

- Nuevos `python/trading_agent/paper_identity.py` y `scripts/paper-identity.ps1`: descubrimiento cifrado, comparación manual exacta, registro local cifrado, caducidad y carga al entorno.
- Cuatro pruebas en `python/tests/test_paper_identity.py`: no exposición en salida, descubrimiento DU/DUR/desconocidos sin autorización por prefijo, rechazo de múltiples/malformadas y fallo de cifrado sin escribir texto plano.
- Nuevas pruebas de compatibilidad en `test_broker.py`, `test_tws.py` y `PaperFeedTests.cs`: aceptación DU/DUR con controles completos; rechazo de formatos desconocidos, vacíos, Unicode, minúsculas, espacios y saltos de línea; identidad distinta con el mismo sufijo; bloqueo de lecturas ante una cuenta no autorizada y de órdenes incluso con DUR; ausencia de atestaciones, modo Live, Read-Only desactivado y conexión incorrecta.
- `scripts/verify.ps1` ejecutado tras la corrección: **94 C# y 52 Python aprobadas, cero omitidas**; compilación sin errores ni advertencias, regresiones PostgreSQL y demostración de capital incluidas. Las 119 pruebas originales permanecen aprobadas. La ejecución anterior a la corrección DU/DUR había aprobado 76 C# y 47 Python.
- Comprobación focalizada de Validate-Authorization en PowerShell: **10 casos sintéticos aprobados**, sin ejecutar Authorize ni escribir un registro autorizado. El primer comando de comprobación falló por construir incorrectamente el fixture con salto de línea (la concatenación añadió otro elemento al array); se corrigió el fixture y se repitió con éxito. No fue un fallo del validador.
- Errores corregidos/documentados: inicialmente el descubrimiento rechazó el formato por un filtro DU numérico y se separó de los gates operativos; ahora se corrigió también la incompatibilidad DU/DUR en esos gates, sin sustituir ninguna comprobación de seguridad. TemporaryDirectory de Python produjo PermissionError por sus permisos en el sandbox; los tests usan directorios únicos dentro de `.local`, con limpieza acotada y rutas verificadas. No hubo fallos en las pruebas de esta corrección.
- El PostgreSQL desechable se inició exclusivamente para fixtures sintéticos y se detuvo al terminar. Ningún dato real de cuenta se guardó allí.

**Lecturas auténticas realizadas:** identidad/handshake únicamente. **Patrimonio, efectivo, posiciones, contrato, cotizaciones y velas EUR/USD:** pendientes. **Velas reales recuperadas:** 15m=0, 1h=0, 4h=0. **Órdenes enviadas:** cero. El capital virtual de US$100 y presupuesto acumulado de US$20 permanecen intactos. La entrega C aún no se declara completa.
