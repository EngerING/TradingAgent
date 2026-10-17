# Entregas A y B: capital virtual y viabilidad económica

Fecha: 2026-10-03. Implementado y verificado en simulación local. **Live deshabilitado; no hay envío de órdenes, ni siquiera Paper.** No se ha comprobado una conexión IBKR. Este informe actualiza el estado histórico de fase 2.

## Entrega A

`VirtualCapital` separa la asignación inicial, P&L realizado bruto/neto, P&L flotante bruto/neto, costos realizados/abiertos y gastos de transferencias. La API crea exclusivamente cuentas `SIM-*` con la asignación de la política: US$100 y presupuesto de pérdidas de US$20. El saldo y el poder de compra de IBKR no alimentan esta asignación. `CashFlow` rechaza aportes a una asignación virtual; los gastos de transferencia solo afectan el resultado económico del proyecto.

La interpretación conservadora de **pérdidas acumuladas** es la suma de los resultados netos negativos de operaciones cerradas. Las operaciones ganadoras aumentan el patrimonio y el tamaño admisible, pero no reponen el presupuesto de US$20. Se añade la pérdida flotante neta actual, sin sumar otra vez las comisiones ya incluidas. Esto puede suspender una cuenta con patrimonio superior a US$100 después de devolver ganancias.

```text
Equity = capital inicial + P&L realizado bruto - costos realizados
         + P&L flotante bruto - costos abiertos
ConsumedLoss = suma de pérdidas netas cerradas + max(0, -P&L flotante neto)
LossRoom = max(0, min(20 - ConsumedLoss, Equity - 80))
EntryBudget = max(0, min(Equity * fracción efectiva,
                        min(margen de los límites diario/semanal/drawdown, LossRoom)
                        - riesgo residual/reservado - buffer))
```

Posiciones abiertas y órdenes pendientes contribuyen a riesgo, margen, exposición y ocupación del slot único. El riesgo residual se cuenta desde la valoración actual; no vuelve a cargar las pérdidas flotantes. El presupuesto se recalcula sobre equity actualizado y el sizing redondea hacia abajo. No se amplían posiciones perdedoras.

| Patrimonio | Nivel | Factor adicional de riesgo y exposición |
| --- | --- | --- |
| Mayor que US$95 | `NORMAL` | 1 |
| US$95 o menos | `REVIEW` | 1; reevaluación determinista de límites |
| US$90 o menos | `REDUCED` | 0,5 |
| US$85 o menos | `RESTRICTED` | 0,25 |
| US$80 o menos, o presupuesto consumido | `SUSPENDED` | 0; nuevas entradas suspendidas |

Los umbrales/factores son configurables y versionados en `research-capital-v3`. Se mantienen los controles anteriores: 0,25 % ordinario, máximo duro de 0,50 % por operación, 1 % diario, 2 % semanal, 5 % de drawdown, prevención por tres pérdidas o 2 % de drawdown, exposición máxima de una vez el patrimonio. **Estos límites pueden suspender antes de US$95/90/85/80**. No se han elevado para alcanzar los niveles nuevos. Los perfiles moderado/agresivo quedan pendientes para investigación aislada en D.

La persistencia usa los payloads JSONB existentes y sus transacciones por cuenta; no modifica migraciones históricas. Liquidaciones y valoraciones son idempotentes. Reiniciar, repetir la inicialización, cambiar de estrategia o empezar otro día no borra pérdidas, reservas ni paradas. Un intento de cambiar la política de una asignación existente requiere revisión administrativa; no hay ruta para que la IA la active.

US$80 es un umbral de control, **no un saldo garantizado**. Se conservan pérdidas mayores a US$20; una prueba registra una caída a US$79 sin ocultar el exceso.

## Entrega B

`ExecutionFeasibilityAnalyzer` recibe los límites calculados por `RiskEngine` y realiza el sizing económico. Comprueba mínimo/incremento de cantidad para la modalidad declarada, permisos, comisiones de apertura/cierre, costos por unidad, spread, slippage, escenario de gap, exposición, margen, capital virtual, pérdida al stop y beneficio potencial si está disponible. En la API el objetivo se deriva de la versión registrada de estrategia, no de un objetivo arbitrario del cliente.

El margen utilizable es el menor entre el disponible declarado y el patrimonio virtual menos margen existente. Se reserva también el costo de ejecución. Nunca utiliza US$1.000.000 de Paper para respaldar una asignación de US$100, ni aumenta el apalancamiento para compensar comisiones.

`RiskRequest.execution` es un nuevo contrato de evidencia. Omitirlo, desconocer la comisión de cierre o declarar costos/margen/contrato no fiables produce rechazo. La marca de cotización debe ser `SIMULATED` para estos endpoints; una valoración `FROZEN`, `DELAYED`, desconocida, futura u obsoleta no admite una nueva entrada. La fuente y fecha quedan almacenadas con la propuesta idempotente. Estas marcas se proporcionan por el operador de simulación: **no son una certificación independiente del bróker**. Antes de E deberá existir evidencia adquirida y validada por un adaptador confiable.

Los rechazos conservan un código y una categoría separada: costo excesivo, capital insuficiente, margen insuficiente, mínimo, riesgo excesivo, datos incompletos o restricciones del bróker. Una cantidad válida para Paper también debe respetar las restricciones conocidas de la cuenta real equivalente; las restricciones desconocidas no se inventan.

Si faltan restricciones reales, el resultado se marca `UNVALIDATED_FOR_PRODUCTION`. Si están completos los campos modelados, se indica únicamente `KNOWN_REAL_RESTRICTIONS_CHECKED_LIVE_DISABLED`: no aprueba producción, no cubre requisitos reales no modelados y no autoriza Live. El contrato de restricciones puede ampliarse cuando se conozcan tipo/jurisdicción de cuenta y condiciones concretas.

La observación proporcionada de EUR/USD/100 EUR/odd lot/comisión de entrada US$2 no se convierte en una regla global de IBKR. La prueba con comisión de cierre desconocida rechaza por datos incompletos. Incluso con cierre sintético gratuito, US$2 de entrada excede US$0,50 de riesgo máximo con US$100. No se declara viable el instrumento para esa configuración.

Al liquidar se compara el costo observado completo con el estimado. Un exceso conserva P&L neto y costos sin doble descuento, registra un evento y suspende nuevas entradas con `EXECUTION_COST_OVERRUN`. No existe reanudación automática.

## Archivos afectados

| Archivo | Cambio |
| --- | --- |
| `src/TradingAgent.Core/VirtualCapital.cs` | Nuevo registro de capital/P&L/costos y nivel de protección |
| `src/TradingAgent.Core/Risk.cs` | Política v3, protección, presupuesto acumulado, valoración y admisión |
| `src/TradingAgent.Core/ExecutionFeasibility.cs` | Evidencia, restricciones equivalentes, sizing y rechazos |
| `src/TradingAgent.Infrastructure/PostgresStore.cs` | Inicialización segura, persistencia, valoración, costos y política |
| `src/TradingAgent.Api/Program.cs` | Asignación limitada, valoración de posición sintética y demo |
| `config/research-policy.json` | Capital, presupuesto y umbrales versionados |
| `tests/TradingAgent.Tests/CapitalTests.cs` | Nuevos escenarios de capital y recuperación PostgreSQL |
| `tests/TradingAgent.Tests/ExecutionFeasibilityTests.cs` | Nuevos escenarios de costos, margen, datos y restricciones |
| `tests/TradingAgent.Tests/RiskTests.cs` | Fixtures con evidencia y composición de una misma asignación |
| `scripts/smoke-api.ps1` | Evidencia, rechazo incompleto, valoración, contabilidad y reinicio |
| `README.md`, `docs/architecture/capital-preservation.md`, `docs/architecture/phase2-implementation.md` | Enlaces al estado actual |
| `docs/architecture/virtual-capital-and-feasibility.md` | Este informe |
| `graphify-out/` | Índice local consultado y actualizado; reporte y visualización |

## Pruebas ejecutadas

| Ejecución | Resultado |
| --- | --- |
| Base previa: `dotnet test TradingAgent.sln -m:1` | 24 aprobadas, 10 PostgreSQL omitidas inicialmente |
| Entrega A, con PostgreSQL desechable | 48 aprobadas, 0 fallidas, 0 omitidas; `artifacts/test-results/delivery-a.trx` |
| B, antes de añadir valoración de posición | 66 aprobadas, 0 fallidas, 0 omitidas; `artifacts/test-results/delivery-b.trx` |
| Validación final `scripts/verify.ps1`, con PostgreSQL | Build con 0 errores/advertencias; 67 C# aprobadas, 0 fallidas/omitidas; `artifacts/test-results/phase2.trx` |
| Misma validación: Python y compilación de módulos | 27 aprobadas; `compileall` aprobado; demo C# ejecutada |
| `scripts/smoke-api.ps1` con la política v3 | Aprobado: auth, ausencia de órdenes/Live/IA, evidencia incompleta, admisión, replay, valoración flotante, liquidación y estado después de reinicio real de API |
| Intento de iniciar API con `Trading__LiveEnabled=true` | Rechazado en arranque con `LIVE_DISABLED` y código de salida 1 |
| Confirmación final C# tras limpieza del fixture | 67 aprobadas, 0 fallidas/omitidas; `artifacts/test-results/capital-feasibility-final.trx` |

Durante B fallaron inicialmente dos expectativas de categoría: con mínimo 20.000 y spread/slippage sintéticos, el rechazo correcto era costo excesivo. Se aislaron los tests de mínimo eliminando esos costos sintéticos; permanecen pruebas separadas de spread elevado y costo excesivo. La ejecución final no tiene fallos. No se debilitó un control para superar estas expectativas.

Los experimentos de cinco ganancias, cinco pérdidas, US$150, US$90 y US$80 usan secuencias sintéticas. Los tests que aíslan el presupuesto acumulado usan límites diarios/semanales/drawdown deliberadamente amplios **solo en su fixture**. No constituyen operaciones IBKR ni evidencia de rentabilidad. Los controles existentes de desconexión, cuenta Live, cambio de versión, oportunidades rechazadas y parada se volvieron a probar con simuladores/PostgreSQL; ejecución parcial y reconciliación de fills de bróker quedan para E.

## Configuración y compatibilidad

Usar `TRADING_POLICY_PATH=config/research-policy.json`, `TRADING_DB`/`TRADING_TEST_DB` apuntando a una base desechable y un `TRADING_ADMIN_TOKEN` aleatorio de al menos 32 caracteres. El README conserva los comandos PowerShell completos. La API sigue limitada a loopback y a simulación.

Los payloads antiguos pueden leerse, pero las cuentas sin registro de asignación no admiten nuevas entradas. No se infieren pérdidas históricas ni se rellenan con cero: hace falta revisión/migración explícita con evidencia antes de reutilizarlas. Para pruebas nuevas, crear otro identificador `SIM-*`. No usar cuentas nuevas para eludir el presupuesto de una asignación operativa: el binding de una única asignación a una cuenta Paper autorizada es trabajo previo a E.

Una decisión ahora necesita, además de los campos anteriores, evidencia como esta **exclusivamente sintética**:

```json
{
  "source": "synthetic-test-fixture",
  "environment": "SIMULATION",
  "mode": "SIMULATED",
  "at": "<fecha UTC actual>",
  "openingCommission": 0,
  "closingCommission": 0,
  "costsReliable": true,
  "marginReliable": true,
  "contractReliable": true,
  "brokerPermitsEntry": true,
  "quoteStatus": "SIMULATED"
}
```

Esto permite pruebas sin bróker; no son tarifas de IBKR. Los importes fijos apertura+cierre deben coincidir con `commissionFixedRoundTrip`. Costos por unidad siguen siendo round trip. Se admite `equivalentRealAccount` parcial para aplicar las restricciones conocidas; omitirlo conserva la marca de producción no validada.

`POST /simulation/valuation` exige `accountId`, `eventId`, `decisionId`, `unrealizedNetPnl`, `openCosts`, `remainingRisk`. El neto incluye costos abiertos; estos no se restan otra vez. La reserva permanece hasta `/simulation/settle`, cuyo `netPnl` es el resultado total de la operación, incluidos los costos observados. No es un callback de fills ni un mecanismo de conciliación IBKR.

## Entrega C y pendientes

Comprobación local de solo lectura: puerto configurado efectivo 7497; conexiones TCP a 7497 y 4002 no disponibles; `ibapi` no instalado; no están configurados `IBKR_VERIFIED_TWS_PORT` ni `IBKR_PAPER_ACCOUNT`. No se identificó una cuenta Paper, no se consultó patrimonio real ni se obtuvieron cotizaciones/velas/What-If. No se utilizaron credenciales y no se envió ninguna orden.

Siguiente paso: disponer de TWS o IB Gateway en modo Paper, instalar el SDK oficial compatible y configurar identidad/puerto verificados para continuar C en lectura. No asumir equivalencia con IBKR Desktop. La consulta de órdenes/restricciones, permisos, What-If, conciliación y pruebas contra IBKR siguen pendientes; el cliente existente no las ofrece todas. D–G, perfiles experimentales amplios, walk-forward/Monte Carlo, ejecución Paper autorizada, fills parciales, OpenAI/Sol, Telegram y observación de siete días no se implementaron en esta entrega.

Graphify se consultó antes de editar: índice inicial de 328 nodos; índice actualizado de 424 nodos. La extracción usa AST local sin llamadas a IA ni costo de tokens del proveedor. Limitaciones visibles del índice: dos migraciones SQL no indexadas por ausencia de `tree_sitter_sql`, colisiones de identificadores de namespace durante actualización y un self-loop en el diagnóstico final. Las migraciones y fuentes relevantes se revisaron directamente; el grafo es orientación, no prueba de integridad o de funcionamiento.
