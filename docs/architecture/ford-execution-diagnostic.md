# Diagnóstico independiente de ejecución Ford Paper

Estado: **PREPARED / EXECUTION_BLOCKED**. EmergencyStop permanece activo. Sin autorizaciones, PaperAuto, órdenes al mercado ni activación de Live. No es una estrategia ni una variante de H40.

## What-If: resultado obtenido en la cuenta vinculada

IBKR documenta el credit preview TWS como `EClient.placeOrder` con `whatIf=True`: realiza una comprobación de crédito en lugar de enviar la orden a una bolsa. `transmit=False` por sí solo no es equivalente; puede crear un ticket ordinario no transmitido. Fuentes: [Order.whatIf](https://www.interactivebrokers.com/docs/tws-api/ref/order), [Checking Margin Changes](https://interactivebrokers.github.io/tws-api/margin.html), [OrderState](https://www.interactivebrokers.com/docs/tws-api/ref/order-state).

Se realizó **una única solicitud crediticia What-If BUY de una acción F**, LMT 12.29, exclusivamente en Paper, alrededor de **2026-10-07 00:50 UTC**. No hubo solicitud SELL hipotética con inventario cero, fallback a orden normal ni reintento. La ruta especializada rechaza órdenes normales, protobuf directo, cancelaciones y vinculación al ejecutor.

| Resultado | Evidencia / interpretación |
|---|---|
| Identidad vinculada | VERIFIED; selección exacta Paper antes/después |
| Callback What-If | Recibido: openOrder, request/orderId crediticio 1, PreSubmitted |
| Margen inicial/mantenimiento antes, cambio y después | UNKNOWN: campos vacíos/sentinel, conservados como null |
| Comisión devuelta | Valor bruto `0.0`, con advertencia y moneda ausente |
| Comisión utilizable / efectiva | UNKNOWN; ese cero no demuestra una tarifa gratuita |
| Mínimo / máximo comisión | UNKNOWN; sentinel no convertido en cero |
| Comisión SELL | UNKNOWN; no se simuló un SELL independiente |
| Comisión observada en fill | Ninguna: no ocurrió una ejecución |
| Posiciones, órdenes abiertas y ejecuciones después | 0 / 0 / 0 |

**Funciona la ruta y se recibe un callback; no se obtuvieron estimaciones económicas utilizables.** No se deducen permiso efectivo, margen cero, aceptación de protección ni tarifas reales de PreSubmitted. La primera captura conservó `warning_present=true` pero no el texto de la advertencia: su causa textual exacta sigue UNKNOWN. No se repitió el request para obtenerla. El parser final incorpora advertencias acotadas con identificadores redactados y flags separados de utilidad de margen/comisión para consultas futuras autorizadas.

Evidencia inmutable del request inicial:

- `artifacts/paper-diagnostics/ford/ford-diag-352ab28fcc2a41119bbbb813bf5d3fd4/evidence/20261007T005018993655-38e023bc-whatif-attempt.json` y hash lateral.
- `artifacts/paper-diagnostics/ford/ford-diag-352ab28fcc2a41119bbbb813bf5d3fd4/evidence/20261007T005018993655-38e023bc.json` y hash lateral.
- Evaluación derivada: `artifacts/test-results/ford-execution-diagnostic/whatif-assessment.json`.

La solicitud What-If no creó intención, reserva o consumo del ciclo físico. Su orderId es un identificador de preview, no una autorización/orden diagnóstica transmitida. Los protocolos preliminares se conservan junto con su evidencia; no se reutilizan después de las mejoras de código que cambian sus attestations.

## Matriz operativa actual

Fuente: callbacks TWS Paper de la misma consulta; summary, ledger, updates y multi completos. Los snapshots anterior y posterior al preview permanecen en la evidencia.

| Condición | Estado | Qué falta |
|---|---|---|
| Cuenta exacta Paper, conexión y consultas | VERIFIED | Revalidar al autorizar y en cada conexión |
| Inventario y órdenes existentes | VERIFIED: 0 / 0 | Nueva conciliación antes de cualquier envío |
| F STK USD, conId 9599491 | VERIFIED | NYSE/SMART; contrato no prueba permiso |
| BID/ASK 12.28/12.29 | DELAYED, tipo 3 | Entitlement y callbacks LIVE tipo 1, campos ≤15 s |
| RTH IBKR | Cerrado en la consulta | Calendario auténtico; siguiente publicado 07/10 13:30–20:00 UTC |
| AvailableFunds | VERIFIED, suficiente | Nunca usado como capital de sizing |
| SettledCash USD | UNKNOWN | Valor inequívoco Paper / evidencia del operador |
| Permiso US stocks | UNKNOWN | Evidencia Paper efectiva, sin inferir de contrato/What-If |
| Tipo cash/margin, fondos e intradía | UNKNOWN | AccountType INDIVIDUAL no resuelve restricciones |
| Margen específico de F | UNKNOWN | What-If no devolvió valores utilizables |
| Min/step declarados | VERIFIED: 0.0001 | Una acción completa representable; fracciones excluidas |
| Plan, mínimos/cap/routing y cargos | UNKNOWN | Tarifa efectiva de Paper y aplicabilidad de reglas |
| STP/LMT/OCA declarados | VERIFIED | Metadatos no acreditan aceptación real |
| Protección aceptada / parciales | UNKNOWN | Sólo un ensayo expresamente consentido puede adquirir esa evidencia |

Fuentes públicas de costos: [US stock commissions](https://www.interactivebrokers.com/en/pricing/commissions-stocks.php). No se asume IBKR Lite. Las tarifas públicas y What-If son estimaciones/modelos distintos de comisiones observadas en `commissionAndFeesReport` asociadas a execId Paper.

## Perfil físico preregistrado

Configuración `config/ford-execution-diagnostic.json`, scope `FORD_EXECUTION_DIAGNOSTIC_ONE_SHARE_V1`. Clasificación `EXECUTION_DIAGNOSTICS`, `strategy_version=null`, `strategy_success=false` en protocolo, estado y reportes. No registra candidato, éxito H40, tasa de acierto ni promoción.

| Control | Límite |
|---|---|
| Capital virtual aislado | US$100 |
| Cantidad / lado | Una acción completa F, BUY LONG |
| Aperturas | Una única tentativa global, durable antes del primer SDK send |
| Notional más reserva de ambos lados | ≤US$100 y cash/equity restante |
| Presupuesto previsto | US$3, equivalente al 3% de US$100 |
| Techo externo previsto | US$10; no amplía US$3 ni cantidad |
| Autorización | DPAPI CurrentUser, independiente, una sola vez, ≤30 minutos |
| Entrada pendiente | GTD 30 segundos desde el plan; no se reenvía después de timeout |
| Ventana de admisión | RTH auténtico con al menos 180 segundos restantes |
| Protección | Target LMT y stop STP ligados al BUY; OCA tipo 2 |
| Inicio de cierre controlado | A los 30 s del primer fill; si se detecta después de 60 s, suspender |
| Stop / target diagnósticos | 1% desde BID (mínimo dos ticks) / 2% sobre límite BUY |
| Gap / slippage modelados | 2% precio / 5 bps por lado + contingencia de tick |
| Contingencia de comisiones | US$1 por ciclo |
| Crédito, short, fracciones, repetición | Prohibidos |

Estos niveles son exclusivamente geometría de un experimento de ejecución; no se usan como señales o parámetros H40. H40 original, H40 R3, RiskEngine y sus límites productivos permanecen intactos. El nuevo wrapper C# llama al cálculo experimental existente y conserva validaciones de exposición, costos, capital, datos y permisos. El request de cálculo no exige rentabilidad potencial porque no es una estrategia; exige source/scope/cuenta virtual diagnósticos exactos. La ruta H40 R3 sigue exigiendo su target y filtro económico.

Preregistro **vigente**: `ford-diag-f61d85c8c08a405cb0a8356a0829a72b`, SHA256 `383e4cb665cc3072f18b378f1be1e5bf6c60ce8628eed3cdbdc9eb57ed07fa23`.

## Escenarios adversos de una acción

Usan el BID/ASK DELAYED de referencia; no son cantidades autorizadas ni precios ejecutables actuales.

| Concepto | Sin cap confirmado, escenario predeterminado | Sensibilidad con cap publicado |
|---|---:|---:|
| BUY límite / stop / target | 12.31 / 12.15 / 12.56 | Iguales |
| BUY estimada, con contingencia | 1.54 | 0.66 |
| SELL estimada, con contingencia | 1.54 | 0.66 |
| Costos de comisiones totales | 3.08 | 1.32 |
| Spread conservador | 0.01 | 0.01 |
| Slippage ambos lados | 0.012290 | 0.012290 |
| Contingencia tick | 0.02 | 0.02 |
| Gap presupuestado 2% | 0.2458 | 0.2458 |
| Geometría stop/spread evaluada por motor | 0.175 | 0.175 |
| Pérdida prevista total | **3.533090** | **1.773090** |
| Notional más reserva de comisiones | 15.39 | 13.63 |
| Dentro de US$3 | **No** | Sí, sólo en este modelo |
| Gap adverso 10% | 4.516290 | 2.756290 |
| Fallo de protección, caída 25% | 6.1575 | 4.3975 |
| Pérdida total del inventario más comisiones previstas | 15.39 | 13.63 |

La columna de cap es una **sensibilidad**, no confirmación. No se elige automáticamente porque sea favorable. El perfil sólo permite utilizarla cuando el operador aporta evidencia Paper actual y verificable de las reglas completas de comisión/cap; What-If por sí solo no las verifica. El modelo y la contingencia siguen siendo conservadores después de verificar la tarifa. No se reduce el gap ni se aumenta riesgo/cantidad para hacer pasar un filtro.

Un stop no impone una garantía de pérdida máxima. Incluso la sensibilidad bajo cap excede US$3 ante un fallo de protección. Si el operador requiere una garantía absoluta de US$3/US$10 en cualquier escenario, **este ensayo no satisface esa condición**. Aceptar conscientemente riesgo de cola no aumenta el presupuesto previsto, no convierte UNKNOWN en VERIFIED y no elimina gates. Ahora no hay evidencia para ejecutar.

## Gates, protección y recuperación

Todos los gates se comprueban antes de reserva/SEND_PENDING/placeOrder: grant independiente, protocolo/fuentes/ejecutable, identidad Paper/proceso, emergencia, snapshot completo/plano, capital compartido sin otras reservas, LIVE/RTH, permisos/fondos/margen/tarifas, plan reproducible y cálculo RiskEngine. La IA no participa. Se revalida edad de quote/deadline después del cálculo, y cada mutación SDK exige el grant y campos exactamente permitidos.

La conexión física comparte exclusivamente clientId 93 con los ejecutores Ford existentes; TWS rechaza una segunda conexión con ese identificador (326). Esto evita carreras entre H40/H40 R3 y el diagnóstico sin modificar sus fuentes. Consultas y What-If usan clientId 94; el observador mantiene su cliente separado. Antes de admitir también se vuelven a comprobar las reservas de otros experimentos. Una conexión ya ocupada bloquea el ensayo; no se desconecta otro proceso para apropiarse del slot.

El bracket serializa BUY LMT GTD, dos SELL protectores vinculados y OCA2. Sus ACK deben llegar en ≤5 s. Tipo, precio, conId, cantidad, parentId, OCA y permId se verifican; un ACK genérico no demuestra protección. Tras fill real se exige reconciliar execDetails, LONG restante y protectores. Un Filled sin execDetails no libera reserva ni se convierte en NO_TRADE.

Un parcial fraccionario inesperado se considera incierto: suspender, mantener reserva/protección y solicitar revisión humana; esta versión no adapta automáticamente una orden fraccionaria. Rechazo, desconexión, identidad cambiada, orden ajena, posición/exec mismatch o estado incierto suspenden sin reenvíos ni modificaciones ciegas. Un cierre iniciado tarde también queda registrado y suspendido; la conectividad no garantiza cierre dentro de 60 s.

Al vencimiento sin fill se cancela el padre primero. Hijos sólo se cancelan después de confirmar padre terminal y posición cero. CancelPending puede reducir riesgo de un padre suspendido usando el consentimiento de gestión original, nunca abrir ni vender.

Cierre normal diagnóstico: confirmar protección y fill, registrar inicio, cancelar siblings propios, obtener otro snapshot completo y sólo entonces SELL LMT ≤LONG confirmado al BID LIVE. El adapter reconsulta posiciones/órdenes inmediatamente antes del envío. LONG cero no genera SELL. Cancelación pendiente nunca permite vender en paralelo. El límite de un intento SELL persiste; un cierre parcial/ambiguo necesita revisión adicional, no un reintento automático.

Antes de quitar siblings para cerrar se exige sesión abierta y BID/ASK LIVE frescos; ante delayed/stale o cierre de mercado, se conserva protección y se suspende. La entrada también requiere al menos tres minutos de RTH restante y un final de sesión conocido. Es un margen de planificación, no una garantía frente a desconexión o halt.

RecoveryAuthorize es otro consentimiento DPAPI ligado a intención/conId/execId/permId BUY y LONG restante; no reutiliza el consentimiento H40 ni uno vencido. Admite exclusivamente cancelar/conciliar y reducir inventario propio confirmado. Puede gestionar inventario con emergencia activa; no la limpia ni habilita entradas. Ante cierre previamente intentado, se mantiene bloqueado para impedir un short accidental.

El journal hash-chained registra snapshot previo, cotizaciones, campos de cuenta/margen observado, precio esperado, SEND_PENDING, ACK, execId/permId, cantidades/precios, comisiones por ejecución, fricción estimada/observada, cierre, P&L bruto/neto y decisión diaria. Precio SELL esperado queda explícito. El P&L neto sólo es definitivo cuando todas las comisiones USD están disponibles. La reserva se libera exclusivamente con inventario cero, ausencia de órdenes y resultado conciliado; ganancias no restauran pérdidas acumuladas. Neto ≤0 detiene nuevas entradas del día America/Santo_Domingo, aunque el límite global de este ensayo ya prohíbe cualquier segunda apertura.

## Intervención humana necesaria

1. **TWS Paper exacto**: revisar cuenta/entorno y US stock permissions. ContractDetails o un callback What-If no prueban permiso efectivo. Si Client Portal sólo expone la cuenta real, consultar a IBKR; no sustituirla por evidencia Live.
2. **Account Window Paper**: revisar SettledCash USD, AvailableFunds, cash/margin y restricciones de fondos/intradía/settlement. Documentar que una LONG completa con 100% efectivo es admisible para esta cuenta. Si no expone el dato, mantener UNKNOWN y solicitar confirmación a IBKR.
3. **Mercado LIVE**: comprobar entitlement de US stocks aplicable al Paper y F. Repetir Inspect durante sesión auténtica hasta obtener marketDataType=1 y BID/ASK frescos; delayed no habilita entrada.
4. **Preview/margen/costos**: consultar en TWS Paper `Check Margin Impact` / vista previa de BUY F sin Submit/Transmit. Revisar la advertencia y, si existe, el log del credit preview clientId 94/orderId 1 alrededor de 00:50 UTC. Vista previa produce ESTIMATED; no comisión ejecutada. No reenviar automáticamente What-If para completar campos vacíos.
5. **Tarifa y cap**: verificar plan Paper, routing, mínimos, reglas de máximo porcentual y cargos adicionales. La evidencia debe vincular cuenta Paper y reglas aplicables a este contrato/tamaño. Recibo `effective_fees=FIXED/TIERED` no prueba por sí solo el cap; requiere una referencia específica. Sin esa prueba se conserva el escenario sin cap que ya excede US$3.
6. **Protección supervisada**: revisar riesgos de ACK/rechazo/partiales y el procedimiento de recuperación, permanecer en TWS durante el ensayo. Una vista previa no acredita aceptación. Sólo el consentimiento explícito de bootstrap puede adquirir evidencia inicial; nunca reemplaza un rechazo previo.
7. **EmergencyStop**: revisión protegida compatible con acciones sigue pendiente; esta fase no implementa levantamiento automático ni ofrece un comando para borrar archivos. Mientras esté activa, Authorize/Run rechazan antes de conceder autorización.

Recibos manuales: archivo privado fuera del versionado, `environment=PAPER_TRADING`, binding_id opaco obtenido en Inspect y scope `FORD_EXECUTION_DIAGNOSTIC_ONE_SHARE_V1`. Cada capability VERIFIED/compatible=true, fuente OPERATOR_PAPER_TWS o OPERATOR_PAPER_CLIENT_PORTAL, referencia documental, observed_at UTC no futuro y ≤24 h. Se complementa sólo UNKNOWN; nunca una restricción incompatible observada.

Valores: stock_permission=true; account_restrictions=WHOLE_SHARE_CASH_LONG_ALLOWED; settled_cash/available_funds≥100; contract_margin=rate observado 0–1 (reserva interna sigue al 100%); effective_fees=FIXED/TIERED. Una acción completa ya es representable por el contrato; el permiso fraccionario no se utiliza. Para seleccionar la sensibilidad cap se exige recibo separado `commission_cap`, value `FIXED_1_PERCENT_CAP_WITH_ADDONS_VERIFIED`, con la evidencia específica correspondiente. No rellenarlo para superar un bloqueo sin verificar la regla.

## Comandos exactos

Desde la raíz, protocolo físico vigente. Consultas de lectura, sin autorizaciones:

```powershell
$diag = 'ford-diag-f61d85c8c08a405cb0a8356a0829a72b'
powershell -ExecutionPolicy Bypass -File .\scripts\ford-execution-diagnostic.ps1 -Action Status -TrialId $diag
powershell -ExecutionPolicy Bypass -File .\scripts\ford-execution-diagnostic.ps1 -Action Inspect -TrialId $diag
```

What-If siguiente, **sólo si el operador decide expresamente otra consulta**; una solicitud crediticia BUY como máximo por comando, ninguna orden al mercado ni retry:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\ford-execution-diagnostic.ps1 -Action WhatIf -TrialId $diag
```

No hace falta repetirlo ahora: el resultado inicial ya está preservado y no resolvió la evidencia. `Inspect` no usa placeOrder. Todos los archivos de evidencia tienen nombres únicos y hashes; no sobrescriben los anteriores.

Cuando existan recibos Paper auténticos:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\ford-execution-diagnostic.ps1 -Action Assess -TrialId $diag -EvidencePath .\.local\ford-diagnostic-paper-evidence.json
```

**No ejecutar ahora**. Después de revisar el protocolo, resolver gates y recibir autorización explícita del operador, mecanismos implementados:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\ford-execution-diagnostic.ps1 -Action Authorize -TrialId $diag -EvidencePath .\.local\ford-diagnostic-paper-evidence.json
powershell -ExecutionPolicy Bypass -File .\scripts\ford-execution-diagnostic.ps1 -Action Status -TrialId $diag
powershell -ExecutionPolicy Bypass -File .\scripts\ford-execution-diagnostic.ps1 -Action Run -TrialId $diag
```

Authorize exige frases específicas de consentimiento diagnóstico, revisión de riesgo de cola y comprobación TWS Paper/API, refresca readiness después del diálogo, vincula proceso/protocolo/fuentes/recibos y crea DPAPI mediante CreateNew. Rechaza emergencia, UNKNOWN, presupuesto insuficiente, consumo previo o protocolo revocado. Status muestra existencia de consentimiento; no sustituye gates de Run ni confirma permiso de ejecución.

Parada, revocación y conciliación:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\ford-execution-diagnostic.ps1 -Action Stop -TrialId $diag
powershell -ExecutionPolicy Bypass -File .\scripts\ford-execution-diagnostic.ps1 -Action Revoke -TrialId $diag
powershell -ExecutionPolicy Bypass -File .\scripts\ford-execution-diagnostic.ps1 -Action Reconcile -TrialId $diag
```

Stop/Revoke no liquidan a ciegas y no limpian emergencia. Después de cualquier suspensión, no repetir Run. Reconcile consulta y actualiza el journal sin enviar órdenes.

Sólo cuando el diagnóstico futuro tenga órdenes/inventario propio, rutas protegidas existentes:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\ford-execution-diagnostic.ps1 -Action RecoveryInspect -TrialId $diag
# Sólo padre pendiente sin LONG; cancelación mutante, no ejecutar ahora:
powershell -ExecutionPolicy Bypass -File .\scripts\ford-execution-diagnostic.ps1 -Action CancelPending -TrialId $diag
# Sólo LONG propio confirmado; requiere otro consentimiento local:
powershell -ExecutionPolicy Bypass -File .\scripts\ford-execution-diagnostic.ps1 -Action RecoveryAuthorize -TrialId $diag
powershell -ExecutionPolicy Bypass -File .\scripts\ford-execution-diagnostic.ps1 -Action RecoveryRun -TrialId $diag
powershell -ExecutionPolicy Bypass -File .\scripts\ford-execution-diagnostic.ps1 -Action Reconcile -TrialId $diag
```

RecoveryRun puede devolver cancelación pendiente: conciliar antes de solicitar cierre de nuevo. Si ya intentó un SELL, esta versión impide otro; revisión humana obligatoria. No hay inventario ni journal de este diagnóstico actualmente.

## Verificación y archivos

**1,272 casos únicos aprobados: 922 Python + 350 C#, cero omitidos.** La suite Python completa de la última ejecución aprobó 918 casos; después se añadieron cuatro gates/casos RTH y se ejecutaron nuevamente los 82 casos del módulo afectado, todos aprobados. Los otros 840 casos conservan sus componentes sin cambios. La suite C# completa aprobó 350. No se suman ejecuciones repetidas al total: 82 Python nuevos + 31 C# nuevos sobre las 1,159 anteriores. Compilación de toda la solución: 0 errores y 0 advertencias. Compileall y parser PowerShell: PASS. PostgreSQL desechable detenido al finalizar.

Cobertura: SDK What-If true-only, sin fallback/retry/cancelación, sentinels y estimaciones incompletas, cuenta/scope/proceso/grant, emergencia y consumo entre reinicios, reservas de ambas comisiones, costos/gaps, protección de tipo/precio/vínculo/cantidad, bracket 0-fill, ACK Filled sin execDetails, parcial incierto, comisiones tardías, cierre tras cancelación/reconciliación, sesión/quote antes de quitar protección y exclusión del slot físico Ford. El smoke Python→CLI .NET, exclusivamente offline, confirma riesgo 1.77309/budget3 para un fixture con cap supuesto; no acredita permisos ni tarifa real.

Logs, evaluación de What-If y verificación final: `artifacts/test-results/ford-execution-diagnostic/`. No se repitió la consulta IBKR durante las regresiones. Los fallos intermedios de compilación/fixture se conservan; los resultados finales indicados son los aprobados.

Archivos nuevos: config/ford-execution-diagnostic.json; python/trading_agent/ford_whatif.py; python/trading_agent/ford_execution_diagnostic.py; scripts/ford-execution-diagnostic.ps1; src/TradingAgent.Core/FordDiagnosticRisk.cs; src/TradingAgent.Api/FordDiagnosticCommand.cs; python/tests/test_ford_execution_diagnostic.py; tests/TradingAgent.Tests/FordDiagnosticRiskTests.cs; este informe. Modificado únicamente el dispatch de src/TradingAgent.Api/Program.cs para exponer el cálculo aislado, con el guard Live original intacto.

65 archivos protegidos mantienen su hash: H40/H40 R3, RiskEngine, ExecutionFeasibility, AccountBinding, autorizaciones y EmergencyStop, entre otros. Los binarios reconstruidos cambian las attestations de despliegue de protocolos anteriores; sus evidencias se preservan, pero no se reutilizan grants/protocolos antiguos. No hubo investigación OpenAI, candidatos, backtests ni acceso a holdout sellado. La única comunicación tipo placeOrder fue el credit preview What-If documentado; órdenes al mercado, fills del diagnóstico y autorizaciones concedidas: cero.
