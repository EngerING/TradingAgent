# Entrega E.0: viabilidad económica y preparación de Paper

Actualización posterior: [E.1 implementa el laboratorio Paper separado](paper-execution-laboratory.md), con 245 pruebas aprobadas y ninguna orden IBKR enviada. La autorización diagnóstica sigue pendiente; los bloqueos económicos de StrategyPaper y los resultados históricos E.0 permanecen vigentes.

Fecha: 2026-10-04. Estudio offline ejecutado. **EUR/USD con US$100 no tiene viabilidad verificada y queda bloqueado.** La estimación manual de US$2 para abrir 100 EUR supera por sí sola los presupuestos ordinario US$0.25 y máximo US$0.50. Con la tarifa pública Tier I aplicada como escenario, las ocho cantidades estudiadas incumplen el riesgo vigente. Aumentar cantidad para diluir comisiones tampoco resuelve la exposición máxima de 1× capital.

Cero órdenes, cero conexiones TWS en E.0, Read-Only API sin cambios, Live bloqueado y cero llamadas a OpenAI. Capital US$100 y pérdidas acumuladas US$20 intactos. No se amplió la autorización de lectura a ejecución. La primera ejecución Paper requerirá autorización manual independiente y una entrega posterior.

## Estado y alcance

Graphify se consultó primero con vocabulario del grafo: `execution feasibility analyzer risk broker restrictions instrument order`. Localizó `ExecutionFeasibilityAnalyzer` en `src/TradingAgent.Core/ExecutionFeasibility.cs:L34`, `RiskPolicy` y `RiskEngine` en `Risk.cs`, y `PaperDataBroker` en `python/trading_agent/broker.py`. El grafo anterior no contiene todas las adiciones C/D; sus resultados truncados se contrastaron con lecturas dirigidas. No se reconstruyó.

La autorización local DPAPI para **3784** fue reconocida como vigente mediante `paper-identity.ps1 -Action Status`. Es la comprobación manual del 4 de octubre a las 06:15:53.9199908 UTC, válida hasta el 5 de octubre a la misma hora mientras se conserve la sesión atestada. E.0 no repite handshake ni certifica el estado actual de TWS. Antes de cualquier lectura futura se conservan los controles de conexión, identidad completa exacta, vigencia y sesión; ni prefijo ni puerto ni cuatro dígitos autorizan una cuenta.

`ExecutionFeasibilityAnalyzer`, `RiskEngine`, `ResearchSimulation`, transporte IBKR, autorizaciones y `config/research-policy.json` permanecen sin cambios. Se añadió un comparador diagnóstico, un comando offline y contratos de preparación sin transporte de órdenes. No se añadieron endpoints para transmitir ni tablas con órdenes simuladas presentadas como ejecuciones IBKR.

## Evidencia de condiciones y comisiones

| Requisito | Evidencia disponible | Estado de esta cuenta |
| --- | --- | --- |
| Contrato | Captura auténtica C: CASH EUR/USD, IDEALPRO, conId 12087792 | Identificación capturada; no permiso de ejecución |
| Tick de precio | C: `min_tick=0.00005`, regla 3188 | Metadato recibido; reglas de órdenes pendientes |
| Cantidad/incremento | C: `minimum_size=0.01`, `size_increment=0.01` | `restrictions_verified=false`; mínimo ejecutable y rejilla no verificados |
| Tamaño estándar Forex | Tabla pública: 20.000 EUR | Umbral público; no demuestra el mínimo permitido para odd lots en esta cuenta |
| Odd lots | Documentación pública: cantidades bajo el estándar tienen tratamiento distinto | Permisos, tipos de orden y condiciones efectivas pendientes |
| Apertura 100 EUR | Propietario informó US$2 estimados | `MANUAL_ESTIMATE`; no comisión realizada ni extensible a otras cantidades |
| Cierre | No hay vista previa aportada ni fill del agente | Desconocido |
| Moneda de comisión | Apertura expresada por el propietario en USD; cuenta C tenía moneda base USD | Moneda efectiva de cargos de ambos lados pendiente de vista previa/reporte |
| Margen | Depende de cuenta, entidad, permisos y posición | Desconocido para estas cantidades; no se usa AvailableFunds/BuyingPower Paper para financiar la asignación |
| Spread/slippage | D.1 tiene promedios de barras y 1.000 ticks fechados; no fills | Spread en cada entrada/salida y slippage no verificados |
| Permisos/tipo de cuenta | Lectura de un contrato/históricos no acredita negociación | Pendientes de comprobación manual |

La tarifa pública Tier I de Forex es 0.20 puntos básicos por valor negociado, mínimo US$2 por orden o equivalente, con cargo convertido a moneda base. Programas/intermediarios pueden cambiar las condiciones. Se usa únicamente como escenario público, nunca como tarifa de cuenta verificada. [Comisiones Forex IBKR](https://www.interactivebrokers.com/en/pricing/commissions-spot-currencies.php).

La tabla de tamaños publica 20.000 EUR. El documento de IBIE describe como odd lots las órdenes inferiores al mínimo y advierte que sus límites no se muestran en IDEALPRO. Citarlo no identifica nuestra entidad ni acredita sus reglas particulares. [Tamaños públicos](https://www.interactivebrokers.com/en/trading/forexOrderSize.php), [condiciones Forex IBIE](https://gdcdyn.interactivebrokers.com/Universal/servlet/Registration_v2.formSampleView?formdb=4762).

IBKR distingue cuentas Cash/Margin y exige cualificaciones/permisos adicionales para Cash Forex; una cuenta Cash no puede pedir prestadas divisas. Los requisitos también dependen de residencia, producto y posibles exigencias internas. No se asigna una tasa de margen pública arbitraria a nuestra cuenta. [Tipos de cuenta](https://www.interactivebrokers.com/en/accounts/configuring-your-account.php), [requisitos de margen](https://www.interactivebrokers.com/en/trading/margin-requirements.php).

Las 7.815 diferencias promedio cero BID_ASK de D.1 siguen siendo spread desconocido para ejecución. La mediana 0.00004 de ticks del viernes no es un spread actual ni aplicable automáticamente a las señales de seis meses. No se convierten históricos en fills. [Evidencia D.1](eurusd-history-and-costs.md).

## Comparación económica ejecutada

`EconomicComparison` complementa el analizador existente. Acepta evidencias con fuente, valor, categoría, vigencia y alcance por cantidad; las comisiones llevan moneda y conversión a USD independiente. No convierte un costo desconocido en cero. Evidencia pública, manual, histórica o hipotética produce `UNVERIFIED`; evidencia de cuenta caducada o de otra cantidad tampoco permite un resultado verificado.

Incluso `VERIFIED_MODEL_ONLY`, usado por fixtures sintéticos completos, es únicamente una comprobación matemática. `ExecutionAuthorized=false` siempre. El comparador consulta el motor de riesgo original sin hechos ejecutables para obtener el presupuesto efectivo y sus bloqueos; nunca sustituye la revisión de admisión.

Para cantidad `q`, multiplicador `m` y conversión de moneda cotizada a USD `fx`:

```text
Exposición nominal = q × precio declarado × m × fx
Pérdida al stop = q × distancia de stop × m × fx
Costos = comisión apertura USD + comisión cierre USD
       + q × (spread ida/vuelta + slippage ida/vuelta) × m × fx
Pérdida prevista = pérdida al stop + costos + q × gap adverso × m × fx
Beneficio bruto = q × distancia objetivo × m × fx
Beneficio neto = beneficio bruto − costos
Distancia de equilibrio = costos / (q × m × fx)
Margen de escenario = exposición × tasa declarada
```

Spread/slippage son distancias totales de ida/vuelta referidas al precio de análisis; no se añaden otra vez como diferencias de fills. La exposición tabulada usa el precio declarado. El futuro envío requiere cotización ejecutable y la revisión conservadora del analizador existente. El gap es un escenario adverso, no una garantía de pérdida máxima de un stop. El límite inferior de costos suma solamente componentes conocidos y se identifica por separado; los totales completos permanecen `null` si falta alguno.

Estudio en `config/economic-study.json`: precio **supuesto** 1.10 USD/EUR, stop 10 pips y objetivo 15 pips, independientes de una señal rentable. Escenario público favorable: tarifas Tier I en ambos lados, spread/slippage/gap cero como límites inferiores hipotéticos, margen 100%, mínimo/paso hipotéticos de 1 EUR. Estas condiciones no representan autorización, cotización ni reglas verificadas. La fila de apertura manual solo usa US$2 cuando q=100; el cierre y sus totales reales siguen nulos.

| EUR | Exposición USD | Comisiones ida/vuelta estimadas USD | Pérdida stop + costos USD | Beneficio neto estimado a 15 pips USD | Equilibrio pips |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1.10 | 4.00 | 4.001 | −3.9985 | 40,000 |
| 10 | 11.00 | 4.00 | 4.010 | −3.9850 | 4,000 |
| 50 | 55.00 | 4.00 | 4.050 | −3.9250 | 800 |
| 80 | 88.00 | 4.00 | 4.080 | −3.8800 | 500 |
| 100 | 110.00 | 4.00 | 4.100 | −3.8500 | 400 |
| 1,000 | 1,100.00 | 4.00 | 5.000 | −2.5000 | 40 |
| 20,000 | 22,000.00 | 4.00 | 24.000 | 26.0000 | 2 |
| 100,000 | 110,000.00 | 4.403 | 104.403 | 145.5970 | 0.4403 |

Las dos cantidades mayores ilustran beneficio bruto/neto positivo en un objetivo supuesto, pero **no viabilidad**: incumplen exposición, capital, margen y riesgo. Las ocho filas son `UNVERIFIED` y bloqueadas. Reducir tamaño mantiene la comisión mínima; aumentar tamaño incumple US$100/1×. A ese precio, el techo nominal sin costos es 90.909… EUR; un escenario totalmente financiado debe además reservar costos. No es una cantidad aprobada.

La tarifa mínima estimada de US$4 es 16 veces el presupuesto ordinario y 8 veces el máximo; la apertura manual de US$2 por sí sola equivale a 8 y 4 veces respectivamente. Aunque el cierre resultara gratuito, esa apertura de 100 EUR no cabe en la política.

## Política preservada

Asignación inicial US$100, pérdida acumulada US$20, riesgo ordinario 0.25%, techo previamente autorizado 0.50%, una posición y exposición 1×. Con equity US$100: US$0.25 y US$0.50 por propuesta. El techo no se selecciona automáticamente; la configuración activa continúa ordinaria. Límites diarios, semanales, drawdown, reservas y reducciones preventivas siguen pasando por `RiskEngine`. El presupuesto efectivo puede ser menor que esos montos. Ganancias no reponen pérdidas acumuladas. No se activaron perfiles experimentales.

## Alternativas investigadas

No hay instrumentos alternativos con permisos y requisitos de nuestra cuenta acreditados; por ello `accountVerifiedAlternatives=[]` y no se calculó una comparación ejecutable ni se cambió EUR/USD.

Se revisó el mercado público de acciones/ETF estadounidenses y fracciones como posible trabajo posterior. La tabla de acciones distingue Pro Tiered/Fixed y Lite, con mínimos, topes y cargos externos; Lite limita elegibilidad a residentes estadounidenses. Las fracciones tienen condiciones propias y no son automáticamente gratuitas. No se infiere residencia ni plan desde el idioma o la zona horaria. [Comisiones de acciones](https://www.interactivebrokers.com/en/pricing/commissions-stocks.php).

La documentación API contempla restricciones por instrumento, tipo de orden, routing, negociación fraccionaria y permisos. Poder comprar fracciones manualmente no demuestra compatibilidad con nuestra vía TWS API. [Errores oficiales 10243–10250](https://www.interactivebrokers.com/docs/tws-api/doc/error-handling/error-codes).

Para comparar un ticker concreto harán falta primero entidad/plan/tipo de cuenta, permiso para el instrumento y vía, contrato inequívoco, mínimo/paso, cotización con timestamp, moneda/cambio, ambas comisiones y margen efectivo. Después se podrán introducir esos hechos en el comparador genérico. Costos menores no acreditan rentabilidad ni una estrategia válida; no se recomienda una alternativa ahora.

## Preparación de ejecución Paper

Contrato actual: `PaperExecutionPreparation.Check` revisa coincidencia ordinal de **la identidad completa** con una única cuenta gestionada; su salida nunca contiene la identidad. Examina entorno, Live, atestaciones, vigencia, conexión, conciliación, emergencia, evidencia, riesgo y protección. Aunque todos los indicadores sean verdaderos, siempre devuelve `E0_EXECUTION_DISABLED` y transmisión falsa. Es un diagnóstico, no un mecanismo de autorización confiable. No recibe permisos desde una salida de IA.

Se prepararon `PaperIntentReference`, `PaperFillObservation` y `PaperCommissionObservation` como contratos inertes. La clave de intención usa JSON sin ambigüedad y hash de cuenta interna Paper, estrategia/versionado, señal, contrato y lado. No es un orderId IBKR, no asigna números del bróker y no garantiza deduplicación sin almacenamiento transaccional. Los siguientes componentes están **diseñados**, pendientes de implementación y validación en otra entrega:

| Componente futuro | Diseño exigido antes de habilitarlo |
| --- | --- |
| Autorización de ejecución | Registro protegido independiente del DPAPI de lectura; cuenta completa, Paper verificado manualmente, contrato/estrategia/versionado, alcance de orden, vencimiento y firma/autor propietario. Reinicio o cambio relevante exige revisión. Sin fallback Live. |
| Separación de servicios | Servicio Paper separado, credenciales/colas/journal con namespace Paper; no reutilizar un transporte Live. Transportes de lectura actuales conservan todos sus bloqueos. E.0 no contiene `placeOrder`, cancelación ni what-if. |
| Revisión final y reserva | Bajo bloqueo transaccional por asignación, comprobar datos actuales, autorización, permisos, RiskEngine, viabilidad, equity US$100/20, margen virtual disponible y restricciones reales. Reservar la pérdida/costos/exposición antes del intento; volver a revisar al vencer cotización o cambiar precio/cantidad. No sustituir margen virtual por Paper BuyingPower. |
| Journal e idempotencia | Restricción única de clave de intención + hash del contenido y estado persistido. Misma clave/contenido retorna el estado; distinto contenido produce conflicto. Guardar intención/reserva antes de I/O. No hay journal activado aún. |
| ID del bróker | Con contador durable y exclusión mutua, usar un entero mayor o igual al `nextValidId` de la sesión y mayor que IDs ya observados/usados; registrar clientId, orderId, permId, orderRef y correlación. No reiniciar ni reutilizar IDs después de un timeout. |
| Ciclo de vida | PROPOSED → RESERVED → SEND_PENDING → ACKNOWLEDGED → PARTIALLY_FILLED/FILLED o CANCEL_PENDING/CANCELLED/REJECTED. Un timeout después de SEND_PENDING pasa a UNKNOWN y obliga a conciliación; jamás se reenvía a ciegas. No se libera reserva por timeout o por mera solicitud de cancelación. |
| Conciliación | Al iniciar/reconectar, recuperar identidad, órdenes abiertas/completadas, ejecuciones, comisiones y posiciones, con marcadores de fin. Comparar journal por referencias estables. Posiciones/órdenes ajenas, faltantes o estado incierto bloquean entradas y requieren revisión; una posición Forex virtual TWS no sustituye saldos/exposición efectivos. |
| Parciales y comisiones | Deduplicar callbacks por execId, validar cantidades acumuladas contra intención, guardar eventos fuera de orden y comisiones tardías por execId/moneda. No contar costos dos veces ni asignar cero a cargos pendientes. Mantener reserva de la parte pendiente y protección de la parte ejecutada. |
| Protección y capital | Confirmar protección efectiva para cantidad ejecutada, permisos/tipos de orden y vínculos/OCA antes de admitir otras acciones. Escalado parcial no deja exposición desprotegida. Actualizar patrimonio, P&L bruto/neto y pérdidas acumuladas mediante reglas existentes; pérdidas/gaps/comisiones superiores a reserva suspenden nuevas entradas. |
| Emergencia | Estado durable que bloquea nuevas entradas incluso sin IA/conectividad. Conservar protecciones existentes; no usar cancelación global que elimine stops. Cancelar pendientes o liquidar requiere política y autorización específicas en la futura entrega. En E.0 no se transmite ninguna acción de emergencia. |
| Recuperación | Arrancar suspendido, reconstruir reservas/fills/costos desde journal, conciliar órdenes y posiciones y comprobar protecciones antes de desbloquear. Costos, identidad o fills inciertos dejan suspendido. La asignación virtual no se reinicia a US$100 para borrar pérdidas. |

La autorización Paper futura debe resolver explícitamente las condiciones de la sesión para ejecutar. La comprobación Read-Only actual no autoriza quitar ese control y E.0 no lo cambia. Se requiere además evidencia equivalente de restricciones reales; el saldo simulado no las acredita. Ninguno de estos contratos habilita operación Live.

## Ejecución, pruebas y pendientes

```powershell
dotnet build TradingAgent.sln -m:1
.\scripts\run-economic-study.ps1
```

El comando `--economic-study` termina antes de cargar PostgreSQL, feed Paper o secretos. El script usa la política activa y deja el informe local en `artifacts/economics`, ignorado por el repositorio. No descifra identidad ni necesita TWS. Configuración JSON estricta con categorías de evidencia legibles; precio/stop/objetivo hipotéticos se conservan en el informe para reproducción.

Ejecución: `artifacts/economics/20261004T1854463198614Z.json`, ocho comparaciones de evidencia incompleta y ocho de escenario público favorable. No se descargaron nuevas velas ni se modificaron los históricos/resultados D.1.

Verificación: **206 pruebas aprobadas: 124 C# + 82 Python, cero omitidas**, preservando las 192 anteriores. Build sin errores/advertencias, compilación Python y demostración de riesgo ejecutadas. PostgreSQL desechable de pruebas fue iniciado en loopback:55432 y detenido al terminar. Las 14 pruebas nuevas cubren aritmética/costos únicos, monedas, desconocidos, alcance de preview, evidencia vencida, pérdidas mayores al presupuesto, mínimos/paso, límite virtual, políticas y reservas, multiplicadores, informe offline, identidad exacta, Live bloqueado, atestación separada, reinicio y claves sin colisiones por delimitadores. No acreditan fills, deduplicación persistente ni recuperación de órdenes reales.

Incidencia resuelta: la primera prueba del comando offline falló porque reutilizaba un contrato JSON snake_case para una configuración camelCase. Se corrigió usando opciones estrictas propias del estudio; no se relajó el contrato IBKR. Las pruebas finales pasaron.

Pendiente del propietario, solicitado durante E.0:

1. Dentro de TWS **Paper**, conservar **Read-Only API**. Revisar únicamente una vista previa manual de 100 EUR/USD CASH IDEALPRO, BUY y SELL; informar comisión/rango y moneda de cada lado, cambio de margen, mínimos/incrementos y advertencias odd lot. **No transmitir ni crear una posición para obtener un cierre.** Con cero posiciones, SELL puede ser una apertura corta: identificarlo como tal y no certificarlo como cierre efectivo. Si la vista previa no representa liquidación o no informa un campo, declararlo pendiente.
2. Confirmar tipo de cuenta, entidad/plan y moneda base actuales; permisos Forex/odd lots y, opcionalmente, mercados de acciones/ETF/fracciones para estudiar alternativas. No enviar identificadores completos ni credenciales.
3. Si TWS reinició o cambió sesión/configuración desde la atestación, repetir la comprobación manual de identidad completa, Paper y Read-Only con el mecanismo local existente antes de nuevas lecturas.

El método what-if de TWS para estimar comisión/margen utiliza `placeOrder`; no se invocó. Un endpoint de preview de otro API no constituye una integración ya autorizada y no se incorporó como atajo. [What-if TWS](https://interactivebrokers.github.io/tws-api/margin.html). Una vista previa aportada seguirá siendo estimación; cargos efectivos se conocen por reportes de ejecuciones, y E.0 no produce esas ejecuciones.

Hasta recibir y validar los datos esenciales, se conserva `UNVERIFIED`. Confirmar costos no implica habilitar operaciones, y con la estimación de apertura vigente no se satisfacen los límites financieros para 100 EUR.
