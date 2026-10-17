# Entrega C: primera lectura auténtica de IBKR Paper

Fecha: 2026-10-04. Validación real completada en modo de solo lectura. **Live Trading bloqueado; cero órdenes transmitidas.** El capital virtual sigue siendo US$100 y el presupuesto acumulado de pérdidas US$20, independientes de los saldos Paper.

Se usaron senior-software-engineer y Graphify antes de revisar el código. El grafo anterior localizó PaperDataBroker, managedAccounts y PostgresStore; la consulta truncada se completó leyendo los componentes actuales. Los cambios quedaron limitados al transporte de lectura, su feed, pruebas, resumen de diagnóstico y documentación; no se modificaron capital, riesgo, esquemas de persistencia ni endpoints de producción.

## Identidad y condiciones de conexión

El propietario registró la comprobación manual de Paper Trading y Read-Only API mediante `scripts/paper-identity.ps1 -Action Authorize`. La autorización DPAPI local se reconoció como vigente; confirmación UTC: **2026-10-04T06:15:53.9199908Z**, vigencia 24 horas. Se comprobó que TWS seguía ejecutándose y que el proceso no se había reiniciado después de esa confirmación. Se realizó un nuevo handshake y reqManagedAccts; la única identidad devuelta coincidió exactamente con la cuenta completa autorizada, terminada en **3784**. El prefijo DUR y el puerto no sustituyen esa comparación ni la comprobación manual.

Conexión exclusivamente a `127.0.0.1:7497`, cliente del colector 73, `ibapi 10.50.2`, servidor API 226. Paper/Read-Only están acreditados mediante el registro manual del propietario; no se afirma que la API permita comprobar esos estados directamente. El cliente bloquea métodos de órdenes antes de cualquier envío y los endpoints de lectura devuelven `executable=false`.

## Datos auténticos y persistencia

Los endpoints consultaron observaciones ya validadas y almacenadas en el clúster Paper separado, loopback:55433, con SCRAM y credenciales protegidas localmente. No se usó el clúster sintético para datos reales. La aplicación dispone de SELECT/INSERT sobre velas, sin UPDATE/DELETE, verificado mediante PostgreSQL.

Snapshot de cuenta recibido **2026-10-04T06:35:02.285992Z**, moneda USD:

| Campo IBKR | Valor recibido |
| --- | ---: |
| NetLiquidation | 1,000,185.90 |
| TotalCashValue / CashBalance | 1,000,000.00 |
| AvailableFunds | 1,000,000.00 |
| BuyingPower | 4,000,000.00 |
| AccruedCash | 185.90 |

Posiciones: **0**, snapshot recibido **2026-10-04T06:35:02.388241Z**. Contrato: EUR/USD, CASH, IDEALPRO, conId **12087792**, minTick **0.00005**, marketRuleIds **3188**, zona US/Eastern. IBKR devolvió minimum_size y size_increment **0.01**; `restrictions_verified=false` se conserva: esos campos por sí solos no certifican mínimos operativos, costos ni viabilidad con US$100.

Cotización recibida **2026-10-04T06:35:12.399122Z**: **UNAVAILABLE**, bid/ask/last nulos, marketDataType **1**, razón `IBKR_READ_TIMEOUT`. Se observaron ticks bid y ask -1, indicadores de ausencia de precio; no se clasificó una cotización inexistente como tiempo real. No se recibió timestamp de origen del precio. REALTIME/DELAYED/FROZEN están cubiertos por pruebas; en esta sesión no se obtuvo una cotización válida de ninguno de esos tipos.

Históricos MIDPOINT, ventana solicitada de siete días, precios y aperturas originales de IBKR:

| Temporalidad | Recibidas y cerradas nominalmente | Excluidas por intervalo corto | Válidas almacenadas / consultadas |
| --- | ---: | ---: | ---: |
| 15 minutos | 475 | 0 | **475** |
| 1 hora | 120 | 5 | **115** |
| 4 horas | 35 | 9 | **26** |

Total recibido: **630**; total conservado en PostgreSQL: **616**. Los recuentos se verificaron de nuevo con SELECT después de terminar la captura, a **2026-10-04T06:37:36.522181Z**; todas las aperturas almacenadas son únicas. Primeras/últimas aperturas UTC: 15m, 2026-09-27 21:15 / 2026-10-02 20:45; 1h, 2026-09-27 22:00 / 2026-10-02 20:00; 4h, 2026-09-28 00:00 / 2026-10-02 20:00. Los eventos HISTORY_* registran los recuentos recibidos, retenidos y excluidos con timestamp de recepción.

IBKR incluye barras de sesión más cortas en series nominales 1h/4h. Por ejemplo, una apertura de 1h a las 21:15 precede a otra a las 22:00. El validador existente exige intervalos nominales sin solapamiento: se excluye la barra anterior cuando su duración nominal invade la apertura siguiente. No se cambian precios, timestamps ni duración declarada; no se resamplea, fabrica volumen o spread ni rellena huecos. Sigue pendiente modelar explícitamente el calendario y las duraciones reales de barras de frontera de sesión; la exclusión no certifica la duración efectiva de cada barra al cierre de sesión.

Evidencias locales, excluidas del repositorio: `artifacts/ibkr/real-paper-validation.json` y `artifacts/ibkr/paper-persistence-validation.json`. Los históricos originales 1h/4h recibidos durante el diagnóstico están en `.local/eurusd-history-{60,240}.received.json`, marcados pendientes de validación de serie; no contienen identificadores de cuenta. La identidad completa autorizada permanece cifrada en `.local/ibkr-paper-authorized.dpapi`.

## Verificación y errores encontrados

- `scripts/smoke-paper-api.ps1 -RealTws` completado: GET de status, cuenta, posiciones, contrato, cotización y las tres series. Token ausente produjo 401; ruta de órdenes ausente produjo 404 sin construir ni transmitir una orden IBKR. El resumen distingue disponibilidad de cotización y recuentos de velas.
- `scripts/verify.ps1` final: **94 C# y 58 Python aprobadas, cero fallos y cero omitidas**, compilación sin errores/advertencias, regresiones PostgreSQL sintéticas, compilación Python y demostración de capital incluidas. Las 119 pruebas originales siguen pasando.
- INVALID_BALANCE: el parser anterior trataba los nombres `$LEDGER-*`, el alias BASE y metadatos textuales como números. Se normalizan únicamente campos permitidos; BASE se resuelve a partir de la moneda recibida en los saldos obligatorios, rechazando ausencia/contradicción. AccountOrGroup se comprueba exactamente y nunca se persiste; otros campos fuera del esquema se descartan. Pruebas cubren estas condiciones.
- INVALID_QUOTE: bid/ask -1 de IBKR se trataban como números inválidos que abortaban los históricos. Ahora se registran como precio no disponible; cero también se excluye para EUR/USD. NaN, infinitos y otros precios negativos siguen rechazados, y una señal de ausencia elimina un precio previo.
- InvalidDataException al persistir 1h/4h: barras de intervalos cortos violaban la regla existente de no solapamiento. Se excluyen con recuento explícito y prueba, sin debilitar el validador C#.
- Las primeras demostraciones vencieron por los errores anteriores; se registraron también eventos IBKR_322 durante esos intentos. La ejecución final completó las tres series; los eventos históricos se conservan para auditoría. Una ejecución de pruebas fue interrumpida por redirección de stderr normal de unittest bajo ErrorActionPreference=Stop; se repitió sin esa redirección y pasó completa.
- Incidencia de privacidad: un diagnóstico ad hoc imprimió por error el campo textual AccountOrGroup con la cuenta completa en la salida de una herramienta. No se repite aquí ni se guardó en archivos del proyecto. Esa salida de herramienta permanece en la conversación. Se corrigió la selección de campos y se comprobó que código, informes, artefactos y logs examinados no contienen la identidad completa; el escaneo excluyó directorios antiguos de fixtures inaccesibles. Un primer escaneo amplio falló por permisos sobre esos directorios, no por encontrar una coincidencia.

Al finalizar se detuvieron el colector/API de validación y los dos clústeres PostgreSQL iniciados para esta tarea; los datos Paper permanecen en disco. TWS y el PostgreSQL existente en 5432 no se detuvieron. Los endpoints se verificaron durante la captura; no se deja un servidor ni un colector continuo activo.

Se verificó el cierre de los puertos 5080, 55432 y 55433. El primer resumen ad hoc de esa comprobación no se pudo serializar por usar claves numéricas en un hashtable PowerShell; se repitió con claves de texto. No afectó a los datos ni al cierre de procesos.

## Limitaciones pendientes

Cotización válida y frescura del precio deberán comprobarse durante una sesión con datos disponibles. Paper/Read-Only requieren renovar la verificación manual al vencer la autorización o cambiar/reiniciar TWS. No están validados para ejecución los calendarios, límites/mínimos de contrato, reglas de mercado, margen, comisiones ni viabilidad económica real. No se habilitó ejecución de órdenes ni Live.

Referencias oficiales: [prefijos por moneda](https://www.interactivebrokers.com/docs/tws-api/doc/tws-settings/per-currency-account-value-prefix), [Account Summary y ledger en moneda base](https://interactivebrokers.github.io/tws-api/account_summary.html), [ticks no disponibles y datos congelados](https://interactivebrokers.github.io/tws-api/md_receive.html).
