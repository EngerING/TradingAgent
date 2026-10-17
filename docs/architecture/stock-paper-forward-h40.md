# H40: preparación de Paper Forward Trading bursátil

Estado del 2026-10-06: `EXECUTION_CONSTRAINT_BLOCKED`. Adapter y laboratorio
implementados; ejecución efectiva no aprobada. Ninguna orden, autorización o
promoción generada. EmergencyStop y Live conservan sus bloqueos.

## Identidad de la estrategia

H40 es `F_Daily_MEAN_REVERSION_Hold40_R4`, versión
`2459b8fbe73d4dec3bff7a1baaf3e382b9473fa5908d25e6d6b58ffd151072d8`.
Se recupera el candidato auténtico de
`artifacts/research/ai-strategy-research/candidates/6093d4afc8961b5278cecea356a2b31c705fe6e51cf1ca343a01d030984c48b8.json`.

Parámetros intactos: F, DAILY, MEAN_REVERSION, fast=10, slow=30,
lookback=20, ATR=14, stop=2 ATR, target=1 R, hold=40 barras, riesgo original=2%.
No se registra una StrategyVersion nueva, ni se otorga PaperEligible o Live.
El operador la seleccionó para observación de ejecución experimental, sin
evidencia de rentabilidad suficiente.

## Componentes y límites

- `stock_paper_forward_wire.py`: contrato F/STK/USD/SMART, clientId 93,
  consultas con callbacks de finalización, identidad exacta AccountBinding,
  bracket BUY LMT + SELL LMT/STP, OCA tipo 2, cancelación de órdenes propias,
  cierre SELL de cantidad restante conciliada, fills y comisiones.
- `stock_paper_forward.py`: configuración, ledger SQLite FULL/WAL con cadena
  hash y compare-and-swap, políticas diarias, reservas y estudios económicos.
- `stock_paper_forward_runner.py`: bloqueo entre procesos, señales H40,
  conciliación, protección, cierre y suspensión sin reintentos ciegos.
- `StockPaperForwardRisk.cs` y protocolo stdin de API: llaman al RiskEngine y
  ExecutionFeasibility originales y agregan restricciones de efectivo y alcance.
- `stock-paper-forward.ps1`: autorización local DPAPI separada de Forex,
  ejecución, consulta, parada de nuevas entradas y revocación.

El capital de dimensionamiento es exclusivamente el ledger de US$100. Las
ganancias se contabilizan, pero el efectivo utilizable y el notional no superan
US$100. Reserva inicial = cantidad × precio límite BUY + comisiones previstas
de ambos lados. Las reservas permanecen durante fills parciales, resultados
inciertos y comisiones pendientes. Una sola intención/posición; acciones
completas exclusivamente; margen de dimensionamiento 100%; exposición 1×.
Ni AvailableFunds ni BuyingPower ficticios de IBKR aumentan esta asignación.

Presupuesto acumulado de pérdidas US$20, sin restauración por beneficios. Una
pérdida que supera el riesgo reservado suspende la ruta hasta revisión. Los
gaps y costos desconocidos impiden garantizar un límite de pérdida realizado.

**Conflicto conservado:** el riesgo original de H40 es 2%; la política productiva
ordinaria permite como máximo 0,5%. RiskEngine devuelve `RISK_EXCEEDS_POLICY`.
Los escenarios 3/5/10/15% pertenecen exclusivamente al laboratorio; jamás
autorizarán esta ruta. El perfil Forex experimental no se reutiliza para acciones.
Falta una decisión y revisión explícita de un perfil bursátil separado; no se
cambia ningún límite actual mediante configuración, autorización o prompt.
También permanecen los límites productivos ordinarios de pérdida diaria 1%,
semanal 2%, drawdown 5% y reducciones preventivas. El ledger no concede permiso
para omitirlos: la política WIN_TO_CONTINUE es un gate adicional de entrada.

## Verificación real de solo lectura

Evidencia preservada en `artifacts/paper-forward/h40/inspections/` con nombres
únicos y hashes. Lectura final: 2026-10-06 20:16:12 UTC.

| Condición | Resultado |
|---|---|
| AccountBinding completo / managedAccounts | VERIFIED, coincidencia exacta Paper |
| Conexión / finalización de consultas | VERIFIED |
| Posiciones / órdenes abiertas / ejecuciones recuperadas | 0 / 0 / 0 |
| Tipo expuesto | INDIVIDUAL; no demuestra CASH/MARGIN ni permisos |
| AvailableFunds USD | VERIFIED; expresamente excluido del dimensionamiento |
| SettledCash USD | UNKNOWN: no fue expuesto |
| Mínimo/incremento declarado del contrato | VERIFIED: 0,0001 / 0,0001; permite representar enteros, no prueba permiso fraccionario |
| Permisos Paper y restricciones intradía | UNKNOWN |
| Margen contractual / tarifas efectivas | UNKNOWN |
| BID / ASK | 12,25 / 12,29, DELAYED tipo 3; no ejecutable |
| Calendario | SCHEDULE + liquidHours auténticos; RTH cerró 20:00 UTC |
| Próxima RTH publicada | 2026-10-07 13:30–20:00 UTC |
| LMT/STP/OCA declarados | VERIFIED en contractDetails |
| Aceptación efectiva y protección de fills parciales | UNKNOWN |
| Acciones corporativas actuales | UNKNOWN |

Los códigos de callback observados incluyen 2104, 2106, 2158, 2100 y 162;
se conservan numéricamente con requestId. No fueron órdenes ni rechazos de
órdenes. Todas las consultas de cuenta terminaron; TWS seguía conectado.
La existencia del contrato y las órdenes declaradas nunca prueban permisos ni
aceptación efectiva. No se transmiten órdenes what-if para obtener margen.

Para resolver UNKNOWN, el operador debe comprobar **la sesión Paper** en TWS
y los documentos/configuración que correspondan a esa identidad: permisos
Stocks US, tipo CASH/MARGIN y restricciones aplicables, efectivo liquidado,
plan Pro Fixed/Tiered y cargos del intermediario. Las fracciones permanecen
deshabilitadas. La aceptación efectiva de protecciones requiere evidencia de
ACK y comportamiento del contrato en una validación controlada independiente;
una vista previa o una captura de opciones del contrato no es esa evidencia.
Esta entrega no autoriza dicha validación ni propone enviar una orden de prueba.

## Referencia de tamaños; no es una señal

Se recuperaron barras diarias TRADES auténticas, con 15 sesiones consecutivas
identificadas por SCHEDULE. ATR14=0,3414285714, close de referencia=12,28,
stop=11,59 y target=12,96 según la geometría original. **No se confirmó señal**.
No se abrió ni modificó el dataset final sellado; estas consultas actuales no
se usan para entrenar, seleccionar o promover la estrategia.

Con BID/ASK delayed 12,25/12,29, BUY límite estimado 12,32, spread 0,04,
slippage conservador 0,05% por lado, gap presupuestado 0,5% y reserva de tick:

| Perfil estudiado | Acciones | Notional | Comisiones BUY+SELL | Reserva de efectivo | Riesgo estimado total | Efectivo libre | Potencial neto al target |
|---|---:|---:|---:|---:|---:|---:|---:|
| 3% | 2 | 24,64 | 0,60 | 25,24 | 2,32748 | 74,76 | 0,41252 |
| 5% | 4 | 49,28 | 0,84 | 50,12 | 4,29496 | 49,88 | 1,18504 |
| 10% | 8 | 98,56 | 0,92 | 99,48 | 7,82992 | 0,52 | 3,13008 |
| 15% | 8 | 98,56 | 0,92 | 99,48 | 7,82992 | 0,52 | 3,13008 |

Precios, spread, costos y gaps son referencias/estimaciones, no un límite
garantizado ni una cotización de ejecución. Las tarifas públicas, mínimos,
topes y cargos se calculan con el modelo auditado V2; las tarifas efectivas de
la cuenta siguen UNKNOWN. Un objetivo neto hipotético positivo no establece
rentabilidad ni expectativa positiva. Una caída superior al gap presupuestado
puede superar el presupuesto de riesgo. Bajo Fixed o cambios de costos pueden
caber menos acciones: en Fixed los tamaños de referencia son 2/4/7/7 acciones,
con riesgos estimados de 2,32748/4,60496/8,01618/8,01618 USD. Para el riesgo
original H40 de 2%, la referencia es una acción, riesgo 1,19374 USD y reserva
12,65 USD; tampoco cumple el máximo productivo de 0,50 USD iniciales.
Las tarifas de fills parciales, modificaciones y ejecuciones en días distintos
no están verificadas; el escenario de una apertura y un cierre completos no
es un límite superior contractual de costos. Cantidad realmente autorizable
**ahora: 0**.

## Estudio económico

60 simulaciones: cuatro perfiles × tres escenarios de costo × cinco ventanas
cronológicas preexistentes. Mismas señales y salidas H40; únicamente cambia el
presupuesto de dimensionamiento del escenario. La función simuladora utiliza
un espacio de globals separado para imponer efectivo ≤100, sin editar ni
parchear globalmente el simulador original. No se registran candidatos nuevos.
Datos de desarrollo/validación ya examinados: no son prueba independiente.

Validación 2022–2023, TIERED_BASE, US$100 iniciales por ventana:

| Riesgo | Cerradas / rechazadas | Acierto neto | P&L neto | Comisiones | PF | Expectativa | DD máximo conservador | Días primera pérdida | Pérdida acumulada consumida |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3% | 12 / 6 | 50,00% | −3,02 | 6,17 | 0,722 | −0,252 | 10,12% | 6 | 10,85 |
| 5% | 11 / 7 | 45,45% | −7,49 | 7,91 | 0,619 | −0,681 | 18,33% | 6 | 19,66 |
| 10% | 9 / 9 | 55,56% | −16,22 | 3,92 | 0,163 | −1,802 | 21,63% | 4 | 19,37 |
| 15% | 2 / 16 | 0,00% | −19,13 | 1,70 | 0 | −9,565 | 23,00% | 2 | 19,13 |

El JSON completo conserva desarrollo, validación, wf1/wf2/wf3, los tres costos,
fills simulados, inventario pendiente y P&L realizado/no realizado. DD incluye
el límite conservador intrabar: no equivale solamente a pérdidas realizadas.
Los tamaños de muestra son pequeños; no justifican rentabilidad. No se
selecciona automáticamente un perfil agresivo. El 3% fue el menos dañino de
los estudiados, pero sigue con expectativa negativa. Se conserva el rechazo
económico anterior; la selección del operador para Forward experimental no
lo convierte en una estrategia económicamente viable.

## Salidas, duplicados y resultados

La señal se calcula con funciones originales sobre barras completas y una
apertura siguiente auténtica. No se desplazan stop ni target por gaps. El
bracket comparte parentId y orderRef; los hijos utilizan OCA tipo 2. BUY tiene
GTD hasta apertura RTH +60 segundos; los hijos son GTC y fuera de RTH=false.
El vencimiento limita entradas tardías; los fills tardíos o inciertos requieren
conciliación. Los precios ejecutados pueden diferir del backtest de aperturas.

Hold40 corresponde a la apertura de la barra observada con índice 39 después
de la entrada. Antes de un SELL independiente: cancelar órdenes propias,
confirmar su finalización, consultar nuevamente posiciones/ejecuciones y cerrar
solamente LONG restante. Si posición=0, no SELL. Ante parcial incierto,
protección insuficiente, timeout, cambio de identidad o posición extranjera,
suspender. No se afirma equivalencia de orden intrabar OHLC frente a fills
reales: stop-first en una vela ambigua es una regla conservadora del simulador.

Journal registra versión, señal/indicadores, cantidad, geometría, reservas,
decisión RiskEngine, SEND_PENDING, ACK/orderStatus, orderId/permId/execId,
fills/precios, comisiones y moneda, fricción estimada, inventario valorado,
P&L bruto/neto, equity, pérdida restante, cierre y decisión diaria. Slippage
real solo puede determinarse con fills y referencias correspondientes; sin
fills permanece sin medir. Se retiene evidencia sin fabricar una ejecución.

Idempotencia = hash de versión y timestamp de señal; orderIds reservados
persistentemente; SEND_PENDING se escribe antes de transmitir. Una revisión
vieja del journal falla. Tras timeout no se repite una orden. Fill parcial,
comisión pendiente o inventario abierto no constituyen una ganancia. El
resultado neto definitivo >0 permite buscar otra señal, con fondos liquidados.
Neto ≤0 bloquea el día del cierre en America/Santo_Domingo. El runner continúa
consultando mercado y gestionando inventario cuando solo se bloquearon entradas.

La autorización DPAPI liga cuenta, TWS PID/start time, endpoint, estrategia,
configuración y hashes de fuentes. Dura hasta ocho horas; no se renueva sola.
Parada/revocación/vencimiento no permiten nuevas entradas. La facultad de
gestionar inventario propio sobrevive, conservando todos los gates de identidad,
cantidad, propiedad, cotización y conciliación.

## Comandos exactos desde la raíz

Revisión de solo lectura y estado:

```powershell
.\scripts\stock-paper-forward.ps1 -Action Inspect
.\scripts\stock-paper-forward.ps1 -Action Status
```

Mecanismos implementados para una futura sesión autorizable:

```powershell
.\scripts\stock-paper-forward.ps1 -Action Authorize
.\scripts\stock-paper-forward.ps1 -Action Run
.\scripts\stock-paper-forward.ps1 -Action Stop
.\scripts\stock-paper-forward.ps1 -Action Revoke
```

**Authorize y Run están bloqueados en el estado actual.** Authorize no escribe
un grant si queda cualquier gate desconocido, riesgo incompatible o emergencia
activa. No hay comando de esta ruta para limpiar la emergencia ni modificar
límites. No sustituirlos por `ExecutionDiagnostics Run` o el runner Forex.
Stop detiene entradas y conserva el deber de gestión; no cerrar a ciegas la
ventana de un runner que esté gestionando inventario. Si el runner murió,
conciliar antes de decidir otra acción; no lanzar otro experimento.

El observador Ford `ford-evidence-001`, su especificación y sus hashes se
conservan separados. Ninguna lectura de este adapter cuenta como sesión de ese
estudio y no se inicia el observador.

## Fuentes

- [Tarifas públicas IBKR](https://www.interactivebrokers.com/en/pricing/commissions-stocks.php): escenarios de costo; no prueba de tarifa efectiva Paper.
- [Bracket Orders](https://www.interactivebrokers.com/docs/general/order-types/complex-orders/bracket-orders): parent/children y transmit; no aceptación efectiva para esta cuenta.
- [Order reference](https://www.interactivebrokers.com/docs/tws-api/ref/order): OCA y condiciones GTC; acciones corporativas pueden cancelar protección y exigen supervisión.

Resultados de compilación, suite completa y comprobación de archivos protegidos
en `artifacts/test-results/stock-paper-forward/verification.json`.

Verificación final: **1.009 pruebas aprobadas** (747 Python + 262 C#), 87 nuevas,
0 fallos y 0 omitidas. Compilación con 0 errores y 0 advertencias; compileall y
parser PowerShell aprobados. 50 archivos/evidencias protegidos sin cambios.
El journal existente del observador ya precedía este trabajo y su lectura de
estado no lo modificó; permanece en 0 sesiones completas. No se inició ni se
detuvo el observador. La base de pruebas se detuvo al terminar.
