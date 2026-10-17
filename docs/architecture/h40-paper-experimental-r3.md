# H40_PAPER_EXPERIMENTAL_R3: preparación supervisada

Estado: **IMPLEMENTED / EXECUTION_BLOCKED**. No autorización concedida, ninguna orden transmitida, EmergencyStop activo y Live bloqueado. Esta variante no acredita rentabilidad ni constituye una promoción de H40.

## Identidad y límites

H40 original permanece intacto: `F_Daily_MEAN_REVERSION_Hold40_R4`, StrategyVersion `2459b8fbe73d4dec3bff7a1baaf3e382b9473fa5908d25e6d6b58ffd151072d8`, candidato `6093d4afc8961b5278cecea356a2b31c705fe6e51cf1ca343a01d030984c48b8`.

Variante independiente: `H40_PAPER_EXPERIMENTAL_R3`, versión `9a5642560bba4fbec3a454468391cc81b3fa59c6ca74aa7a8d312fc2c2cc535e`. Su identidad se deriva del padre, nombre del perfil y riesgo del 3%; los indicadores, señales, stop ATR×2, target R×1 y Hold40 conservan los valores originales. La configuración original del padre sigue declarando riesgo 2%.

| Control | R3 |
|---|---|
| Capital aislado | US$100; nunca BuyingPower/NetLiquidation del broker |
| Riesgo seleccionado | min(3% equity, US$3, US$10, pérdidas acumuladas restantes) |
| Techo externo previsto | US$10; no aumenta el presupuesto R3 ni la cantidad |
| Cantidad | Como máximo una acción completa de F; LONG exclusivamente |
| Efectivo comprometido | Notional más reserva íntegra de ambas comisiones ≤ US$100 y efectivo/equity restante |
| Crédito / fracciones / short | Prohibidos |
| Aperturas | Una única tentativa global transmitida, persistente entre reinicios |
| Consentimiento | DPAPI independiente, máximo 30 minutos, perfil/versión/protocolo/Paper/proceso TWS exactos |
| Política diaria | WIN_TO_CONTINUE / FIRST_LOSS_STOPS_DAY, America/Santo_Domingo |
| Resultado no definitivo | No habilita entrada; neto ≤0 termina nuevas entradas del día |
| Presupuesto acumulado | US$20; las ganancias no restauran pérdidas consumidas |

`H40PaperR3Risk` es una frontera experimental aislada que reutiliza las verificaciones de RiskEngine. No modifica `Risk.cs`, `PaperRiskProfile.cs`, `ExecutionFeasibility.cs`, el techo productivo de 0.5%, el wrapper original R2 ni H40. La ruta normal sigue rechazando el riesgo original del 2%. Un cálculo R3 permitido no concede autorización de ejecución. El ensayo de un solo uso tampoco habilita una segunda apertura después de una ganancia.

Preregistro preparado: `h40-trial-56d27a0a618b4b348ea69534c6075e17`, archivo `artifacts/paper-trials/h40/h40-trial-56d27a0a618b4b348ea69534c6075e17/protocol.json`, SHA256 `60842e234107dab4092b23b1695e55cc01de524f5655fa82ee72b381a384e3d7`. Configuración y fuentes/ejecutables quedan vinculados a su hash. Los protocolos anteriores se conservan; sus attestations de despliegue ya no son reutilizables después de cambiar las fuentes compartidas. No se sobrescribieron sus evidencias.

## Evidencia Paper actualizada

Consultas de cuenta completadas el **2026-10-07 00:16:18 UTC**; cotización recibida a **00:16:33 UTC**. Esto corresponde a la noche del 6 de octubre en America/Santo_Domingo. Evidencia original y hash lateral:

- `artifacts/paper-forward/h40/inspections/20261007T001633935516-3b9a4c2a.json`.
- Diagnóstico de solo lectura: `artifacts/paper-trials/h40/h40-trial-56d27a0a618b4b348ea69534c6075e17/diagnostics/20261007T001633970197-01494904.json`.

| Condición | Estado | Fuente / alcance |
|---|---|---|
| Identidad completa AccountBinding Paper | VERIFIED | Verificación exacta de identidad; identificador de cuenta no divulgado |
| Conectividad y consultas completas | VERIFIED | summary, ledger, updates y multi finalizadas |
| Posiciones / órdenes abiertas | VERIFIED: 0 / 0 | Snapshot Paper; execDetails/commissions vacíos en esta consulta |
| Contrato F STK USD | VERIFIED | conId 9599491, NYSE/SMART |
| BID / ASK | 12.28 / 12.29, DELAYED | marketDataType=3; no utilizables para entrada |
| Siguiente RTH publicado | VERIFIED | 2026-10-07 13:30–20:00 UTC; sesión actual cerrada |
| AvailableFunds | VERIFIED, suficiente | Callback Paper; no utilizado para dimensionar |
| SettledCash USD | UNKNOWN | Las consultas no expusieron un valor inequívoco |
| Permiso efectivo US stocks | UNKNOWN | La existencia del contrato y TradingType no acreditan permiso |
| Tipo cash/margin y restricciones intradía/fondos | UNKNOWN | AccountType=INDIVIDUAL no resuelve esas condiciones |
| Margen específico de F | UNKNOWN | Margen agregado cero sin inventario no demuestra margen de la operación |
| Tamaños declarados | VERIFIED: min/step 0.0001 | Una acción completa representable; permiso fraccionario UNKNOWN y excluido |
| Plan tarifario, routing y aplicación efectiva del cap | UNKNOWN | Tarifas públicas/modelo no prueban la factura Paper |
| STP/LMT/OCA declarados | VERIFIED | Metadatos del contrato; no prueban aceptación efectiva |
| Aceptación de protección / comportamiento parcial | UNKNOWN | No se envió ninguna orden |
| Ajustes corporativos del contexto de señal | UNKNOWN | Revisión de precios/acciones corporativas pendiente |

Los eventos IBKR quedan preservados, incluidos 162, 2188 y 366 asociados al historial/consultas. No se convierten en pruebas de permiso o protección ni se ocultan las condiciones UNKNOWN. Los volúmenes/tamaños recibidos tienen unidad UNKNOWN.

## Riesgo previsto de una acción

La historia recibida permite una referencia ATR14=0.3414285714, stop 11.59 y target 12.96. **Esta referencia no verifica una señal H40**. Se recalculará desde una señal auténtica y cotizaciones LIVE antes de cualquier ensayo autorizado.

| Componente | Modelo R3 con cap publicado | Sensibilidad sin cap confirmado |
|---|---:|---:|
| Cantidad | 1 | 1 |
| BUY límite modelado | US$12.31 | US$12.31 |
| Stop / target de referencia | 11.59 / 12.96 | 11.59 / 12.96 |
| Movimiento hasta stop | 0.72 | 0.72 |
| Comisión BUY estimada | 0.66 | 1.54 |
| Comisión SELL estimada | 0.67 | 1.54 |
| Comisiones totales, incluyendo US$1 de contingencia | 1.33 | 3.08 |
| Spread conservador | 0.01 | 0.01 |
| Slippage ambos lados | 0.012290 | 0.012290 |
| Gap presupuestado | 0.061450 | 0.061450 |
| Contingencia de tick | 0.02 | 0.02 |
| Ajuste por geometría BUY límite/BID del motor | 0.005 | 0.005 |
| Pérdida prevista total | **2.158740** | **3.908740** |
| Presupuesto seleccionado | 3.00 | 3.00 |
| Dentro del presupuesto | Sí, sólo bajo este modelo | **No** |
| Notional más reserva de comisiones | 13.64 | 15.39 |
| Beneficio bruto al target | 0.65 | 0.65 |
| Beneficio potencial neto conservador | **−0.788740** | **−2.538740** |
| Acciones ejecutables ahora | **0** | **0** |

Ambos escenarios son ESTIMATED, no una factura. La sensibilidad conserva mínimos completos Fixed sin aplicar un cap no confirmado, junto con los demás cargos/contingencias del modelo. No afirma que IBKR facture así; muestra que confirmar el plan y la aplicación del cap importa para cumplir US$3. R3 mantiene `EFFECTIVE_FEES_UNKNOWN` bloqueante: consentir una estimación no lo transforma en VERIFIED.

Las [tarifas oficiales US stocks](https://www.interactivebrokers.com/en/pricing/commissions-stocks.php) publican mínimos, máximos porcentuales y cargos adicionales; el modelo auditado aplica estos componentes por orden, sin asumir IBKR Lite. La tarifa concreta de la cuenta, routing, cargos parciales y aplicabilidad deben verificarse. La cantidad no aumenta para compensar comisiones.

El beneficio potencial neto negativo conserva el rechazo `COST_EXCEEDS_POTENTIAL_PROFIT`. El 3% resuelve únicamente la frontera de riesgo del ensayo; no resuelve la economía. No se altera el target original ni se elimina del request para aparentar un diagnóstico.

US$10 es un límite de pérdida **prevista**, no garantía de ejecución del stop. Gaps, halts y fallos pueden exceder la contingencia; una LONG sin crédito puede perder una parte sustancial o todo su notional más cargos. Debe revisarse ese riesgo de cola antes del consentimiento.

## Procedimientos pendientes

1. **Datos LIVE**: operador revisa entitlement/suscripción aplicable a TWS Paper y F. Volver a ejecutar Diagnose durante RTH hasta recibir marketDataType=1 y BID/ASK frescos (≤15 s); captura visual o precio delayed no sustituye callbacks.
2. **Permisos**: comprobar en TWS/Client Portal la identidad Paper y permiso US stocks. Si el portal sólo muestra cuenta real o no expone permiso Paper, solicitar confirmación explícita a IBKR y mantener UNKNOWN. No inferirlo por contractDetails.
3. **Fondos/restricciones**: TWS Paper Account Window → seleccionar la cuenta exacta → revisar SettledCash USD, AvailableFunds, modalidad cash/margin, restricciones de fondos y day trading. Si no expone SettledCash o limitaciones, consultar a IBKR. El recibo debe acreditar compatibilidad del ensayo sin crédito; el saldo grande no amplía US$100.
4. **Tarifas/margen**: revisar plan tarifario de esa cuenta y aplicación de mínimos/caps/addons/routing. Examinar una vista previa de una acción F en TWS Paper **sin Submit/Transmit**. Una estimación de comisión/margen permanece ESTIMATED; no basta para afirmar aceptación o tarifas efectivas. Solicitar evidencia/documentación Paper cuando la vista previa sea insuficiente. Ninguna llamada API `placeOrder`, incluido whatIf, se utilizó para obtener margen.
5. **Historia/señal**: verificar acciones corporativas, ajuste y procedencia de barras completas. Exigir señal H40 original y apertura de la siguiente sesión auténtica dentro de sus primeros 60 s. Esta inspección no acredita señal.
6. **Protección**: metadatos/vista previa no acreditan aceptación. La excepción supervisada existente sólo puede adquirir esa evidencia después de consentimiento específico y de resolver los demás gates. Rechazo previo no admite bootstrap. Operador presente; ACK de cada orden con permId en ≤5 s, después conciliación de fill/cantidad/protectores. [Documentación IBKR de brackets](https://www.interactivebrokers.com/docs/general/order-types/complex-orders/bracket-orders).
7. **Emergencia**: permanece activa. Esta implementación no aporta un mecanismo bursátil compatible de revisión/levantamiento protegido. Mientras ese bloqueo no se resuelva mediante un procedimiento independiente revisado por el operador, Authorize/Run rechazan. No borrar archivos de emergencia ni reutilizar Review Forex como evidencia para Ford.
8. **Economía**: el target de referencia no supera costos; sigue rechazado aunque se resuelvan permisos. Cualquier futura señal se evaluará con sus niveles originales. No forzar operaciones, reducir contingencias sin nueva evidencia/preregistro ni elevar riesgo/cantidad.

Los recibos manuales pueden complementar únicamente UNKNOWN, con `environment=PAPER_TRADING`, `binding_id` exacto y `scope=H40_R3_SUPERVISED_SINGLE_PAPER_TRIAL`. Cada capability requiere `status=VERIFIED`, `compatible=true`, fuente `OPERATOR_PAPER_TWS` o `OPERATOR_PAPER_CLIENT_PORTAL`, referencia comprobable, timestamp UTC no futuro y antigüedad ≤24 h. No crear estos recibos afirmando condiciones no verificadas.

Valores admitidos: stock_permission=true; account_restrictions=`WHOLE_SHARE_CASH_LONG_ALLOWED`; settled_cash/available_funds≥100; contract_margin=rate observado entre 0 y 1 (reserva interna igualmente 100%); effective_fees=`FIXED`/`TIERED` con referencia que documente reglas completas, incluido cap/routing; corporate_actions=`CURRENT_SIGNAL_HISTORY_CHECKED`. La recepción de un nombre de plan no demuestra por sí sola su aplicación a una orden. Posiciones, órdenes, calendario, identidad y cotización siempre provienen de consultas actuales, nunca de recibos manuales.

## Diagnóstico y operación H40 separados

`Diagnose` es **READ_ONLY_PRETRADE_DIAGNOSTIC**: guarda evidencia única con hash, no usa un transporte de órdenes, no crea journal/intención/reserva, no cuenta una operación ni un éxito de estrategia.

Un diagnóstico físico de ejecución de Ford sin señal **no está implementado por este protocolo**. No utilizar ExecutionDiagnostics Forex para F ni Run sin señal. Medir comisiones/fills/protección mediante un diagnóstico bursátil exigiría otra especificación, clasificación y autorización independientes. Una futura operación R3 requiere señal H40; una recuperación anticipada queda etiquetada como recovery y no como salida original ni prueba de rentabilidad.

## Flujo autorizado futuro y recuperación

Todos los gates de entrada se verifican antes de reserva/SEND_PENDING/placeOrder y otra vez en el guard de cada mutación SDK: protocolo, versión, grant, identidad/proceso, emergencia, snapshot reconciliado, sesión/quote, permisos/fondos/costos, señal original y cálculo de riesgo. SEND_PENDING se persiste antes de transmitir y el consumo global se protege contra reinicios. Un timeout/ACK/fill incierto suspende; nunca se reenvía a ciegas.

Bracket: BUY LMT GTD, SELL target y SELL STP GTC ligados al padre, OCA tipo 2. ACK no equivale a fill ni a protección suficiente: se exige conciliar execId/permId/cantidad y protección de la LONG real. Fracción inesperada, rechazo, desconexión u orden desconocida suspende. Los casos ACK sin fill, Filled sin execDetails, parcial, comisión tardía y cancelación pendiente conservan reservas y requieren conciliación.

Salidas originales: stop, target y Hold40 con índice original 39 y siguiente apertura; gaps y doble toque conservadores. No sustituir Hold40 por una salida a los 60 s. Un cierre anticipado exige consentimiento recovery independiente.

RecoveryClose se liga a intención/conId/execId/permId BUY originales y cantidad LONG actual. Reconsulta identidad/órdenes/posición antes de cancelar y vender; cancela sólo órdenes propias y concilia primero. SELL≤LONG confirmado; LONG cero no vende. Cambios inesperados, órdenes ajenas o intento de cierre ambiguo/previo bloquean. Un cierre parcial no permite modificación/reintento automático: intervención supervisada y revisión adicional necesarias. Reserva sólo se libera tras posición cero, ausencia de órdenes pendientes y comisiones definitivas. EmergencyStop no se limpia al recuperar.

## Comandos exactos

Desde la raíz, éstos son seguros para diagnóstico de sólo lectura y no conceden autorización:

```powershell
$trial = 'h40-trial-56d27a0a618b4b348ea69534c6075e17'
$profile = 'H40_PAPER_EXPERIMENTAL_R3'
powershell -ExecutionPolicy Bypass -File .\scripts\h40-paper-trial.ps1 -Action Status -TrialId $trial -Profile $profile
powershell -ExecutionPolicy Bypass -File .\scripts\h40-paper-trial.ps1 -Action Diagnose -TrialId $trial -Profile $profile
```

Cada Diagnose crea un archivo nuevo; no sobrescribe evidencia anterior. No preparar otro trial para eludir un consumo/resultado. Para evaluación con recibos Paper auténticos, una vez recopilados por el operador:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\h40-paper-trial.ps1 -Action Assess -TrialId $trial -Profile $profile -EvidencePath .\.local\h40-r3-paper-evidence.json
```

**No ejecutar ahora**. Sólo después de revisar este protocolo, resolver todos los bloqueos, disponer de señal válida y autorización explícita del operador:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\h40-paper-trial.ps1 -Action Authorize -TrialId $trial -Profile $profile -EvidencePath .\.local\h40-r3-paper-evidence.json
powershell -ExecutionPolicy Bypass -File .\scripts\h40-paper-trial.ps1 -Action Run -TrialId $trial -Profile $profile
```

Authorize exige confirmación local `AUTHORIZE_ONE_H40_PAPER_EXPERIMENTAL_R3_3_PERCENT_NO_LIVE` y verificación específica de TWS Paper/API; refresca readiness después del diálogo. Escribe DPAPI CreateNew, nunca reemplaza un grant. Con la emergencia actual rechaza antes de conceder autorización. No concede PaperAuto.

Comandos existentes de parada/revocación y recuperación, sólo aplicables cuando exista un ensayo autorizado y sus órdenes/inventario propios:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\h40-paper-trial.ps1 -Action Stop -TrialId $trial -Profile $profile
powershell -ExecutionPolicy Bypass -File .\scripts\h40-paper-trial.ps1 -Action Revoke -TrialId $trial -Profile $profile
powershell -ExecutionPolicy Bypass -File .\scripts\h40-paper-trial.ps1 -Action RecoveryInspect -TrialId $trial -Profile $profile
# Sólo padre pendiente sin inventario; no ejecutarlo ahora:
powershell -ExecutionPolicy Bypass -File .\scripts\h40-paper-trial.ps1 -Action CancelPending -TrialId $trial -Profile $profile
# Sólo LONG propio confirmado, nuevo consentimiento recovery local:
powershell -ExecutionPolicy Bypass -File .\scripts\h40-paper-trial.ps1 -Action RecoveryAuthorize -TrialId $trial -Profile $profile
powershell -ExecutionPolicy Bypass -File .\scripts\h40-paper-trial.ps1 -Action RecoveryRun -TrialId $trial -Profile $profile
powershell -ExecutionPolicy Bypass -File .\scripts\h40-paper-trial.ps1 -Action RecoveryInspect -TrialId $trial -Profile $profile
```

Recovery exige scope `H40_R3_TRIAL_OWNED_RECOVERY_CLOSE_ONLY`, distinto de la entrada. Si el cierre solicita conciliación pendiente, usar RecoveryInspect, nunca repetir un SELL a ciegas. No hay inventario del nuevo ensayo ni motivo para autorizar recovery ahora.

## Verificación y archivos

**1,159 pruebas aprobadas: 840 Python + 319 C#, cero omitidas.** Se añadieron 35 Python y 30 C# al estado de 1,094. Las suites completas se ejecutaron secuencialmente; no se suman ejecuciones enfocadas. La primera ejecución C# usó una cadena errónea de la base desechable y falló en 29 pruebas de conexión; ese log se conserva. Repetida con Username=trading_test/Database=postgres, las 319 aprobaron sin cambios de código. Compilación completa: 0 errores y 0 advertencias; compileall y parser PowerShell: PASS.

Cobertura nueva: identidad/parent de variante, límite 3%, una acción, costo+gap+padding dentro de presupuesto, reserva ≤100, min/cap incierto, presupuesto externo sin escalada, rechazos LIVE/DELAYED/UNKNOWN, aislamiento R2/productivo, receipts/grants/recovery de otro scope rechazados, persistencia de consumo/pérdidas/clasificación, diagnóstico único sin órdenes, target no positivo bloqueado. Las regresiones originales de señales/exits/Hold40 y adapter permanecen aprobadas.

El smoke Python→CLI .NET usa un fixture artificial con target 15 exclusivamente para probar serialización y equivalencia del cálculo; no es evidencia de mercado, modificación de H40 ni autorización. El target original 12.96 sigue rechazado en su prueba separada.

Archivos nuevos: `config/h40-paper-r3.json`, `src/TradingAgent.Core/H40PaperR3Risk.cs`, `python/tests/test_h40_paper_r3.py`, `tests/TradingAgent.Tests/H40PaperR3Tests.cs` y este informe. Modificados: `python/trading_agent/h40_paper_trial.py`, `scripts/h40-paper-trial.ps1`, `src/TradingAgent.Api/StockPaperForwardCommand.cs`, `src/TradingAgent.Api/Program.cs`. Evidencia/preregistro/resultados se guardan en carpetas nuevas.

Resultados finales: `artifacts/test-results/h40-r3/verification.json`. Los hashes de 57 archivos protegidos conservan RiskEngine, H40, perfiles originales, AccountBinding, autorizaciones, EmergencyStop y estudio Ford sin cambios. No se abrió la prueba final, no se inició el observador, no se llamó OpenAI, no se concedió autorización ni se transmitieron órdenes Paper/Live. La ejecución efectiva/protección IBKR permanece sin probar.
