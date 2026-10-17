# Ensayo supervisado H40 en IBKR Paper

Estado de preparación, 6 de octubre de 2026: **BLOCKED / NO_TRADE**. No se ha concedido autorización, transmitido órdenes, consumido una apertura ni creado un journal de ejecución del ensayo. EmergencyStop permanece activo; PaperAuto y Live permanecen bloqueados. Este protocolo no promueve H40 ni afirma rentabilidad.

## Perfil y separación del riesgo

`config/h40-paper-trial.json` define `PAPER_EXPERIMENTAL_H40_SUPERVISED_V1`. La StrategyVersion sigue siendo `2459b8fbe73d4dec3bff7a1baaf3e382b9473fa5908d25e6d6b58ffd151072d8`; el candidato original sigue siendo `F_Daily_MEAN_REVERSION_Hold40_R4`, risk_percent=2, stop_atr=2, target_r=1 y max_hold_bars=40. No se modificaron sus indicadores, señales, configuración o salidas.

| Control | Límite del ensayo |
|---|---|
| Capital virtual inicial | US$100, independiente del saldo IBKR |
| Notional máximo | US$100, sin apalancamiento |
| Notional + reservas de ambos lados | ≤ US$100 y ≤ efectivo/equity de la asignación |
| Riesgo previsto | min(2% equity, US$10, presupuesto de pérdidas restante) |
| Presupuesto acumulado | US$20; las ganancias no restauran pérdidas consumidas |
| Primera prueba supervisada | Una acción completa de F como máximo |
| Aperturas | Una sola tentativa transmitida, persistente entre reinicios |
| Autorización de entrada | Independiente, DPAPI, de 30 minutos como máximo |
| Posiciones | Una LONG; prohibido short, fracciones y otra entrada |
| Costos | FIXED_FEE_STRESS auditado + US$1 de contingencia por ciclo |
| Protección | Bracket LMT/STP, OCA tipo 2; aceptación efectiva UNKNOWN inicialmente |

El US$10 es un techo externo; no convierte el 2% original en 10%. `H40PaperTrialRisk` utiliza las comprobaciones experimentales ya existentes de RiskEngine dentro de una frontera nueva limitada a F/Paper/BUY/una acción/capital 100. El cálculo no concede permisos de broker. La autorización protegida específica se comprueba en Python antes de reservar y en cada mutación SDK. La ruta productiva conserva su techo de **0.5%**, y `StockPaperForwardRisk` continúa rechazando H40 al 2%. `Risk.cs`, `PaperRiskProfile.cs` y `ExecutionFeasibility.cs` permanecen intactos.

El filtro económico del motor también sigue vigente: un target cuyo beneficio potencial no cubra costos permanece rechazado. No se elimina para producir actividad. El riesgo presupuestado incluye movimiento hasta el stop, ambas comisiones, spread, deslizamiento, redondeo/tick y gap conservador de 0.5%. Un stop no garantiza una pérdida máxima de US$10 ante gaps, halts o fallos. En una LONG sin crédito, la pérdida extrema puede aproximarse al notional comprometido más cargos; estos riesgos de cola requieren revisión explícita del operador.

## Evidencia Paper obtenida sin órdenes

Inspección: `artifacts/paper-forward/h40/inspections/20261006T230123606278-7694abf4.json`, con hash lateral preservado. Consultas concluidas alrededor de **23:01 UTC**; cotización recibida a **23:01:23 UTC**.

| Dato | Estado y alcance |
|---|---|
| AccountBinding completo | VERIFIED; única identidad Paper exacta, sin mostrar el identificador |
| Conectividad y consultas | VERIFIED; summary, ledger, updates y multi terminadas |
| Posiciones / órdenes abiertas | VERIFIED: 0 / 0 |
| Contrato | VERIFIED: F, STK, USD, conId 9599491, NYSE/SMART |
| BID / ASK | 12.27 / 12.28, **DELAYED** (marketDataType=3), no utilizables para ejecutar |
| Sesión regular | Cerrada; siguiente publicada por IBKR: 2026-10-07 13:30–20:00 UTC |
| AvailableFunds | VERIFIED, suficiente para US$100; nunca usado como capital de dimensionamiento |
| SettledCash | UNKNOWN; no apareció un valor USD inequívoco |
| Permisos efectivos / restricciones intradía | UNKNOWN; contrato y AccountType no los acreditan |
| Tamaños declarados | Min/step 0.0001; una acción completa representable; permiso de fracciones UNKNOWN y fuera de alcance |
| Margen específico de F | UNKNOWN; el motor reserva 100% del notional, sin crédito |
| Tarifas efectivas / routing / nuevos mínimos parciales | UNKNOWN; modelo conservador ESTIMATED |
| Protección declarada | VERIFIED: LMT/STP/OCA disponibles en metadatos |
| Protección aceptada / comportamiento parcial | UNKNOWN; no se transmitió ninguna orden |
| Ajustes corporativos del contexto de señal | UNKNOWN; revisión pendiente |

La referencia histórica de 15 sesiones da ATR14=0.3414285714, stop 11.59 y target 12.96. **Es una referencia, no una señal H40 autorizable.**

| Referencia de una acción | Sin contingencia adicional | Perfil del ensayo |
|---|---:|---:|
| Límite BUY modelado | US$12.30 | US$12.30 |
| Stop / target | 11.59 / 12.96 | Sin cambios |
| Apertura / cierre estimados | 0.16 / 0.17 | 0.66 / 0.67, incluyendo contingencia repartida |
| Reserva de efectivo | 12.63 | 13.63 |
| Movimiento al stop | 0.71 | 0.71 |
| Spread | 0.01 | 0.01 |
| Slippage ambos lados | 0.01228 | 0.01228 |
| Gap presupuestado | 0.06140 | 0.06140 |
| Contingencia de tick | 0.02 | 0.02 |
| Pérdida prevista total | 1.14368 | **2.14368** |
| Target bruto | 0.66 | 0.66 |
| Target neto conservador | 0.22632 | **−0.77368** |
| Cantidad admitida | Referencia sin permisos | **0: supera US$2 y no cubre costos** |

No se escoge el escenario barato para levantar un bloqueo. Los precios son evidencia fechada y DELAYED, no una cotización ejecutable actual ni garantía de tarifa. Los límites porcentuales/minimum/cap de la tarifa se aplican por orden conforme al modelo V2, más cargos y contingencias; las comisiones efectivas se registrarán desde callbacks, no se sustituirán por estas estimaciones. Fuentes: [tarifas oficiales](https://www.interactivebrokers.com/en/pricing/commissions-stocks.php), [brackets IBKR](https://www.interactivebrokers.com/docs/general/order-types/complex-orders/bracket-orders).

## Protocolo de la primera prueba

1. Preregistro inmutable con versión, configuración, hashes del ejecutable y fuentes. Consentimiento local DPAPI independiente de las autorizaciones Forex/PaperAuto; ligado a la identidad completa, proceso TWS y protocolo. No se sobrescribe una autorización existente.
2. Verificación Paper de solo lectura de posiciones, órdenes, fills, comisiones, cuenta, contrato, calendario y cotización. Todos los callbacks de cuenta deben terminar. No se envía `whatIf/placeOrder` para obtener margen. Datos LIVE de BID y ASK de antigüedad ≤15 s; sesión RTH auténtica de IBKR.
3. Permisos/restricciones/margen/fondos y calidad de la historia deben estar verificados para la cuenta Paper concreta. Evidencia manual protegida puede complementar UNKNOWN, nunca contradecir una restricción observada. Tarifas pueden permanecer UNKNOWN únicamente con consentimiento específico al escenario ESTIMATED y contingencia; no se etiquetan como VERIFIED por aprobar una estimación.
4. Emergencia y paradas de entrada deben haber recibido una revisión protegida del operador. Este cambio **no limpia la emergencia** ni implementa una limpieza bursátil automática. No se reutiliza una revisión Forex como prueba de readiness de F. Mientras no exista una revisión compatible, Authorize/Run permanecen bloqueados; borrar un archivo de emergencia manualmente no es el procedimiento recomendado.
5. Señal original reproducida de velas completas, entrada en la apertura de la siguiente sesión auténtica y dentro de sus primeros 60 s. Stop y target originales; no se mueve su geometría para superar gates. Sin señal, datos insuficientes, costos excesivos o tamaño cero: NO_TRADE, sin orden ni cuota.
6. Signal → cálculo experimental RiskEngine → ExecutionFeasibility → TrialGuard → reserva íntegra → SEND_PENDING durable → bracket. conId, fecha GTD, versión, intención e identidad de señal se vuelven a comprobar antes de la primera mutación. La autorización protege exactamente este perfil; no cambia el productivo.
7. Operador presente en TWS. Únicamente este consentimiento permite adquirir evidencia de aceptación inicial: BUY LMT GTD, SELL target y SELL STP GTC vinculados al BUY; OCA tipo 2. Se esperan ACK individuales con permId en ≤5 s. Un ACK del bracket no implica todavía protección de la posición: después se exige reconciliar el fill y los dos protectores con la cantidad LONG restante.
8. Si falta ACK, hay rechazo, fill fraccionario inesperado, identidad distinta, conexión perdida, orden desconocida o estado incierto: suspensión durable; no se reenvía, modifica ni abre otra posición. Primero reconciliar. Una apertura 0-fill pendiente se cancela por el padre; se conservan hijos hasta confirmar ausencia de inventario y padre terminal. Un fill parcial requiere cancelación/reconciliación; no se acepta sobreprotección que pueda abrir short.
9. Salidas normales: stop, target o la apertura original de Hold40 (índice 39 de barras auténticas). Este ensayo **no sustituye Hold40 por un cierre a los 60 s**. Un cierre anticipado requiere RecoveryClose propio, explícito y separado; se identifica como recuperación y no como resultado de la salida original H40.
10. RecoveryClose requiere nueva autorización DPAPI ligada a intención, conId, execId/permId BUY y LONG restante. Cancela/reconcilia órdenes propias antes de SELL; reconsulta posiciones y órdenes en el límite de envío. SELL nunca excede el LONG confirmado; posición cero nunca genera SELL. Un intento SELL ambiguo o parcial no admite modificación/reintento ciego. Un segundo cierre parcial exige revisar evidencia y una nueva decisión del operador; esta versión lo mantiene bloqueado y puede requerir intervención directa supervisada en TWS.
11. Reserva retenida hasta posición cero, cero órdenes abiertas y comisiones definitivas de todos los fills. Un ACK Filled sin execDetails no se trata como NO_TRADE ni libera reservas. Gross/net, comisiones, fricción estimada/observada, equity, pérdidas acumuladas y decisión diaria se conservan en el journal hash-chained. Neto positivo puede habilitar búsquedas futuras dentro de la política general; **este ensayo de un solo uso no habilita una segunda apertura**. Neto negativo o cero detiene el día America/Santo_Domingo. Reiniciar no borra pérdidas ni consumo global del ensayo.

## Intervención humana pendiente

- TWS **Paper**: revisar cabecera de entorno/cuenta exacta, permisos de US stocks y estado de restricciones. Si Client Portal sólo muestra la cuenta real, no utilizar esa captura como evidencia Paper; consultar a IBKR o mantener UNKNOWN.
- TWS Paper Account Window: recuperar SettledCash USD, AvailableFunds, tipo cash/margin y restricciones de fondos/intradía. Los saldos no amplían la asignación virtual.
- Para margen/tarifas: revisar información de cuenta y una vista previa de F en TWS Paper **sin pulsar Submit/Transmit**; registrar fecha, fuente y limitaciones. Si la vista previa no prueba la condición, permanece UNKNOWN. Sin llamadas API `placeOrder/whatIf`.
- Suscripción/entitlement de mercado: corregir disponibilidad y volver a consultar hasta recibir marketDataType=1; una captura o precio delayed no reemplaza el gate LIVE.
- Revisar acciones corporativas, ajustes y procedencia del contexto diario de H40.
- Revisar el riesgo de cola, escenario de costos y protocolo de protección inicial. El consentimiento no garantiza que las órdenes sean aceptadas. Si el costo conocido permite reducir una contingencia, será una nueva revisión y preregistro, no una edición silenciosa del perfil firmado.
- Revisión protegida compatible de EmergencyStop pendiente antes de cualquier entrada; nunca concede PaperAuto o Live.

## Comandos implementados

Desde la raíz, protocolo vigente:

```powershell
$trial = 'h40-trial-4f100143d5a442089dddffaf9bd1aa38'
powershell -ExecutionPolicy Bypass -File .\scripts\h40-paper-trial.ps1 -Action Status -TrialId $trial
powershell -ExecutionPolicy Bypass -File .\scripts\h40-paper-trial.ps1 -Action Inspect -TrialId $trial
```

Las consultas se automatizan; condiciones no expuestas deben aportar recibos Paper revisados por el operador. El archivo `-EvidencePath` contiene `environment=PAPER_TRADING`, el `binding_id` opaco devuelto por Inspect y `scope=H40_SUPERVISED_SINGLE_PAPER_TRIAL`. `capabilities` contiene sólo los recibos necesarios: status VERIFIED, compatible true, source `OPERATOR_PAPER_TWS` o `OPERATOR_PAPER_CLIENT_PORTAL`, reference de la evidencia, observed_at UTC ≤24 h y value. Valores: stock_permission=true; account_restrictions=`WHOLE_SHARE_CASH_LONG_ALLOWED`; settled_cash/available_funds ≥100; whole_share_minimum/quantity_increment=1 si se confirman manualmente para órdenes completas; contract_margin=rate observado 0–1 (el modelo igualmente reserva 100%); effective_fees=`FIXED`/`TIERED` sólo si se verifica; corporate_actions=`CURRENT_SIGNAL_HISTORY_CHECKED` tras revisar la historia. No sustituir UNKNOWN por estas afirmaciones sin evidencia.

Para reconocer explícitamente incertidumbre de tarifas, el documento puede añadir:

```json
"cost_scenario": {
  "status": "ESTIMATED", "model": "FIXED_FEE_STRESS",
  "effective_fees": "UNKNOWN", "contingency_usd": 1,
  "operator_accepts_uncertainty": true,
  "source": "https://www.interactivebrokers.com/en/pricing/commissions-stocks.php"
}
```

Solamente después de revisar el protocolo y resolver los gates; **Authorize sigue rechazando la emergencia actual sin escribir un grant**:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\h40-paper-trial.ps1 -Action Assess -TrialId $trial -EvidencePath .\.local\h40-paper-evidence.json
powershell -ExecutionPolicy Bypass -File .\scripts\h40-paper-trial.ps1 -Action Authorize -TrialId $trial -EvidencePath .\.local\h40-paper-evidence.json
powershell -ExecutionPolicy Bypass -File .\scripts\h40-paper-trial.ps1 -Action Run -TrialId $trial
```

Parada/revocación, conservando gestión propia y emergencia:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\h40-paper-trial.ps1 -Action Stop -TrialId $trial
powershell -ExecutionPolicy Bypass -File .\scripts\h40-paper-trial.ps1 -Action Revoke -TrialId $trial
```

Recuperación futura, únicamente si este ensayo creó inventario u órdenes propios:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\h40-paper-trial.ps1 -Action RecoveryInspect -TrialId $trial
# Sólo para bracket pendiente sin inventario: padre primero, luego reconciliar.
powershell -ExecutionPolicy Bypass -File .\scripts\h40-paper-trial.ps1 -Action CancelPending -TrialId $trial
powershell -ExecutionPolicy Bypass -File .\scripts\h40-paper-trial.ps1 -Action RecoveryInspect -TrialId $trial
# Sólo para LONG propio confirmado; exige consentimiento local nuevo.
powershell -ExecutionPolicy Bypass -File .\scripts\h40-paper-trial.ps1 -Action RecoveryAuthorize -TrialId $trial
powershell -ExecutionPolicy Bypass -File .\scripts\h40-paper-trial.ps1 -Action RecoveryRun -TrialId $trial
powershell -ExecutionPolicy Bypass -File .\scripts\h40-paper-trial.ps1 -Action RecoveryInspect -TrialId $trial
```

No ejecutar ahora Run/Authorize/RecoveryRun/CancelPending. No existe inventario del ensayo. Si RecoveryRun solicita cancelación pendiente, el siguiente paso es RecoveryInspect; no repetir a ciegas ni volver a ExecutionDiagnostics. Si la posición es cero, RecoveryAuthorize no concede una orden SELL. Las autorizaciones expiradas o archivos existentes no se reemplazan automáticamente.

## Verificación

Resultados y logs: `artifacts/test-results/h40-controlled-paper/`. Nueva cobertura: autorización experimental independiente, ceiling productivo intacto, perfil 2%/US$10, reserva de costos/capital, un solo uso entre reinicios, permisos UNKNOWN, delayed/stale, bootstrap protegido y rechazo previo, ACK sin fill, Filled sin execDetails, inventario sin protección, cancelación padre/hijos conservadora, neto negativo/cero/positivo y comisión pendiente, vinculación GTD/conId/intención y recovery sin short. Las pruebas del adapter existente siguen cubriendo parcial, comisión tardía, cancelación, serialización y cierre propio.

**1,094 pruebas aprobadas: 805 Python + 289 C#; cero fallos y cero omitidas.** Se añadieron 58 pruebas Python y 27 C# al estado de 1,009. Compilación de toda la solución: cero errores y advertencias. Compileall Python y parser PowerShell: PASS. Las suites completas se ejecutaron secuencialmente contra PostgreSQL desechable, posteriormente detenido; no se suman las ejecuciones enfocadas ni las regresiones intermedias al total final.

La comprobación de hashes de 54 archivos protegidos no detectó modificaciones de RiskEngine, H40, AccountBinding, autorizaciones anteriores, EmergencyStop o el observador Ford. El estudio preregistrado del observador continúa separado. Sin llamadas OpenAI, promoción de estrategias, acceso a la prueba final sellada ni órdenes Paper/Live. La ejecución efectiva y protección en IBKR siguen **sin probar**.
