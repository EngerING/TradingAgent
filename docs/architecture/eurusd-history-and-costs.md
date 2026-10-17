# Ampliación de entrega D: seis meses de historia y costos

Fecha: 2026-10-04. Descarga auténtica IBKR Paper y evaluación completadas. **Cero órdenes, Live bloqueado, Read-Only sin cambios y cero llamadas a OpenAI.** Se conservaron US$100 de asignación y US$20 de pérdidas acumuladas. El millón simulado de Paper no se utiliza para dimensionar propuestas.

## Históricos obtenidos

Se solicitó `[2026-04-03T00:00:00Z, 2026-10-03T00:00:00Z)`: seis meses calendario, 183 días. El último cierre disponible es el viernes 2 de octubre a las 21:00 UTC. Se completó el objetivo inicial de seis meses; **no se descargaron doce meses** ni se afirma que todos los instrumentos/permisos permitan esa extensión.

La autorización DPAPI vigente para la cuenta terminada en **3784** fue reconocida. El handshake confirmó servidor API 226 y coincidencia exacta con la cuenta completa autorizada, sin imprimirla. Paper y Read-Only continúan sustentados por la comprobación manual vigente; la API no certifica esos estados de la interfaz. El adaptador reutiliza el cliente que bloquea operaciones de órdenes, incluido what-if.

| Temporalidad MIDPOINT | Originales auténticos | Nativas completas analizadas | Parciales excluidas |
| --- | ---: | ---: | ---: |
| 15M | 12.423 | 12.423 | 0 |
| 1H | 3.138 | 3.009 | 129 |
| 4H | 915 | 655 | 260 |
| Total | 16.476 | 16.087 | 389 |

Hubo 76 respuestas disponibles: 27 páginas MIDPOINT 15M, siete 1H, siete 4H, 27 BID_ASK 15M, siete calendarios SCHEDULE y una muestra de ticks BID/ASK. No hubo tipos marcados no disponibles ni huecos de barras completas esperadas dentro de los seis meses solicitados. Duplicados, conflictos de precios, timestamps sin zona y OHLC inválidos provocan rechazo, sin relleno artificial.

Las páginas 15M usan siete días; 1H/4H usan 28 días, con fechas UTC explícitas. Una única conexión realiza solicitudes secuenciales, separadas al menos 12 segundos, o 24 para BID_ASK por su peso doble. Los originales llevan solicitud, procedencia, recepción, disponibilidad y hash de contenido. Se reutilizan páginas completas idénticas y se comprueba su integridad. Un bloqueo de archivo impide dos colectores concurrentes; un registro de pacing conserva el último envío para futuras reanudaciones. Permisos inválidos, pérdida de conexión o autorización vencida bloquean lecturas. Una indisponibilidad de un tipo se registra y suspende sus solicitudes posteriores; no se fabrica una serie alternativa.

Los límites publicados para barras pequeñas y los tamaños de solicitud se usaron como referencia conservadora; no se presentan como una garantía de disponibilidad de esta cuenta. La disponibilidad de seis meses quedó comprobada mediante las respuestas recibidas. [Límites históricos de IBKR, documentación oficial heredada](https://interactivebrokers.github.io/tws-api/historical_limitations.html).

## Sesiones y series derivadas

Se obtuvieron horarios históricos reales mediante `reqHistoricalData(..., "1 day", "SCHEDULE", ...)` y `historicalSchedule`, con zona `US/Eastern`. Se combinaron intervalos idénticos de páginas solapadas y se comprobó cobertura de la solicitud. Esta ampliación usa **IBKR_HISTORICAL_SCHEDULE**, en lugar de extrapolar la plantilla provisional de D. Se incluyen las excepciones que devolvió IBKR; no se confunden festivos de liquidación con cierres. [SCHEDULE y tipos históricos](https://interactivebrokers.github.io/tws-api/historical_bars.html).

`ForexCalendar` acepta ahora intervalos explícitos UTC recibidos del bróker. La conversión usa `tzdata` y zonas IANA; las pruebas cubren DST y ventanas regionales de Londres/Nueva York. La muestra abril–octubre no atraviesa el cambio DST de Nueva York: sus pruebas de invierno/verano son sintéticas y no acreditan barras nativas de invierno. Ampliar a doce meses requiere volver a obtener y validar sesiones y anclaje de barras para esas fechas.

Las barras 1H/4H de frontera se conservan completas como evidencia original, pero no se fuerzan a duración nominal. La serie nativa de análisis excluye intervalos cortos, solapados o fuera de rejilla UTC. La derivación opcional desde 15M exige todos los constituyentes y una sesión completa: produjo 3.009 barras 1H y 655 de 4H, etiquetadas `DERIVED_IBKR_MIDPOINT_15M`, con versión de agregación. **El análisis de señales utiliza las series nativas; no las mezcla con las derivadas.**

## BID/ASK y costos

Se recuperaron **12.423 barras BID_ASK** y **1.000 ticks BID/ASK**. Las barras contienen promedio temporal bid en `open` y promedio temporal ask en `close`; no se interpretan como apertura/cierre de una operación. La diferencia corresponde al promedio del intervalo, no al spread instantáneo de entrada/salida. [Semántica oficial BID_ASK](https://interactivebrokers.github.io/tws-api/historical_bars.html).

- 4.608 barras tienen diferencia positiva: `OBSERVED_BAR_AVERAGE`. Usarlas como costo de ejecución sería una estimación.
- 7.815 barras devuelven promedios iguales: se conserva `raw_average_difference=0`, pero `spread=null` y `UNKNOWN_ZERO_AVERAGE_DIFFERENCE` para costos. Agregación/redondeo no prueban un spread ejecutable gratuito.
- Los ticks registran bid, ask y spread en su timestamp: `OBSERVED_AT_TIMESTAMP`. Cubren aproximadamente 20:44:58–20:57:36 UTC del 2 de octubre; no representan spreads de cada entrada durante seis meses. Su mediana observada es 0.00004.

Las barras/cotizaciones agregadas no se convierten en fills históricos. Los originales permanecen archivados, incluso cuando no permiten resolver el spread. La API histórica limita cada petición de ticks; esta entrega conserva una muestra, sin afirmar haber descargado el libro de cotizaciones completo. [Ticks históricos de IBKR](https://interactivebrokers.github.io/tws-api/historical_time_and_sales.html).

La apertura manual informada por el usuario, **US$2 estimados para 100 EUR**, queda como `MANUAL_ESTIMATE`. Cierre, slippage y restricciones de lotes pequeños continúan desconocidos/no verificados. La tarifa pública directa Tier I indica un mínimo de US$2 por orden, pero advierte posibles variaciones por programa/intermediario. Los precios efectivos de esta cuenta no se certifican mediante esa tabla. Las órdenes inferiores al mínimo IDEALPRO son odd lots y tienen condiciones distintas de exhibición/ejecución. [Tarifas actuales](https://www.interactivebrokers.com/en/pricing/commissions-spot-currencies.php), [condiciones Forex IBIE](https://gdcdyn.interactivebrokers.com/Universal/servlet/Registration_v2.formSampleView?formdb=4762).

No se usó `placeOrder`, what-if ni órdenes pequeñas para verificar costos. Se solicitó una comprobación manual de la vista previa de cierre, sin transmisión; sigue pendiente. Aun una vista previa sería una estimación, no una comisión realizada.

## Desarrollo, validación y resultados

Se mantuvieron los parámetros de D sin optimización. Desarrollo: 3 de abril–3 de agosto; validación reservada: 3 de agosto–3 de octubre, con frontera UTC y exclusión del final. La validación puede usar barras anteriores para calentamiento, sin usar cierres futuros. Cada hipótesis/partición tiene una asignación virtual independiente US$100/20; no se trasladan posiciones ni equity entre particiones. Los resultados no representan una cartera ejecutada continuamente durante seis meses.

| Hipótesis | Desarrollo | Validación | Total | Admitidas |
| --- | ---: | ---: | ---: | ---: |
| Tendencia | 140 | 78 | 218 | 0 |
| Retroceso | 902 | 436 | 1.338 | 0 |
| Reversión | 17 | 6 | 23 | 0 |
| Total | 1.059 | 520 | 1.579 | 0 |

Cada propuesta pasó por el `RiskEngine` y su evaluación de viabilidad existentes. Las 1.579 fueron rechazadas con `EXECUTION_DATA_INCOMPLETE`. Motivos adicionales, que pueden coincidir: 118 con calentamiento multitemporal insuficiente, 620 con contradicción del contexto y 21 con gap de entrada. El calentamiento inicial sigue excluido aunque ahora el último estado 4H está preparado.

También se ejecutó una hipótesis de costos claramente estimada: US$2 de apertura y US$2 de cierre, usando límites favorables de cero para otros costos y mínimo de cantidad de una unidad. **No son tarifas de cuenta verificadas ni prueba de spread/slippage cero.** Incluso con esas condiciones favorables, las 1.579 propuestas obtuvieron `COST_EXCEEDS_RISK_BUDGET`. El costo fijo excede el presupuesto normal US$0.25 por propuesta con equity US$100; no se modificó la política para admitirlas.

No hay operaciones hipotéticas admitidas. Ganancias/pérdidas brutas, costo total, neto, drawdown, profit factor, expectativa y rachas **no son evaluables** y permanecen `null` en las métricas verificables. Un cero contable de una simulación sin trades no demuestra rentabilidad. El cálculo de métricas para escenarios con trades se probó con resultados conocidos: neto incluye costos; profit factor usa P&L neto; drawdown usa equity al cierre de trades y se identifica como tal, sin pretender medir drawdown intrabar.

## Condiciones y comparación de escenarios

| Marco | Alcista | Bajista | Lateral | Indeterminado |
| --- | ---: | ---: | ---: | ---: |
| 15M | 3.095 | 4.014 | 5.264 | 50 |
| 1H | 723 | 1.008 | 1.228 | 50 |
| 4H | 107 | 205 | 293 | 50 |

Volatilidad 15M: 6.284 normal y 6.089 reducida; 1H: 2.959 normal; 4H: 272 elevada y 333 normal. Cada marco conserva 50 puntos iniciales indeterminados. No aparecieron todas las combinaciones de condiciones en cada marco con estos umbrales.

Las señales se agrupan por estrategia, partición, tendencia, volatilidad y ventanas regionales: Tokio 09–18, Londres 08–17 y Nueva York 08–17 en su hora local. Son ventanas de estudio superpuestas, no sesiones oficiales del contrato. Hubo 652 pertenencias Tokio, 652 Londres, 571 Nueva York y 166 fuera de esas ventanas; los solapamientos explican que su suma exceda el número de señales. La distribución completa está en JSON. **Sin operaciones admisibles/costos resueltos no se concluyen diferencias estadísticamente significativas de rentabilidad.** No se calcularon p-values sobre señales autocorrelacionadas para presentarlas como evidencia de ejecución.

El último cierre histórico clasifica 15M lateral/volatilidad normal, 1H bajista/normal y 4H bajista/elevada. Los tres están `READY`. Esto describe el cierre del viernes, no una cotización actual del domingo.

## Persistencia, experiencia y Sol

Informe final: `artifacts/research/6dd3f0c7e256f1c86fdb397133513a2896ab57822250b0e2748ca1acd6e6ab40.extended.json`; contexto Sol: mismo identificador con `.extended.sol-context.json`. Ambos son locales e ignorados por el repositorio. Motor: `research-extension-v2`, que distingue las diferencias promedio cero no resueltas.

El PostgreSQL protegido conserva un snapshot de entrada con las páginas originales, otro con análisis y otro con validación ampliada; también tres versiones de hipótesis para la configuración final, tres backtests generales, 1.579 decisiones y 1.579 evaluaciones de riesgo. Desarrollo/validación, escenario estimado, métricas, derivados, spreads y ticks están en los snapshots. Se reutilizan las estructuras JSON existentes y una transacción. Las **616 velas originales C permanecen intactas**; la ampliación se archiva separadamente para conservar procedencia y posibles revisiones entre capturas.

La clave de ejecución combina cuenta interna, dataset, parámetros, calendario y corte. Repetir el mismo corte/configuración no duplica registros. El usuario de aplicación continúa con SELECT/INSERT, sin UPDATE/DELETE para estos datos. Las capturas/resultados de versiones anteriores se conservan como evidencia histórica; no se sustituyen.

Se añadió un contrato de comparación futura: versión de estrategia, señal, condición, precios/costos/neto teóricos, referencia de observación Paper y diferencias de ejecución/costos. Por ahora `paper_execution_observations=[]`, diferencias `null` y estado `NO_AGENT_EXECUTION_OBSERVED`. **Los históricos no se registran como experiencia de ejecución real.**

El contexto Sol incorpora indicadores, calidad, incertidumbre, evidencia de costos, condiciones, particiones, evaluaciones, métricas, límites financieros y evidencia de pruebas ejecutadas. No activa cliente OpenAI ni delega la admisión al modelo.

## Reproducción y verificaciones

```powershell
# Con TWS Paper y autorización local vigentes; solo solicitudes de datos.
.\scripts\collect-research-history.ps1 -Start '2026-04-03T00:00:00Z' -End '2026-10-03T00:00:00Z'

# Archivo descargado completo; cálculo y persistencia sin TWS.
dotnet build TradingAgent.sln -m:1
.\scripts\run-extended-research.ps1 -ValidationStart '2026-08-03T00:00:00Z'
```

La descarga queda en `.local/research-history` con páginas y manifiesto. El segundo script exige que el colector haya terminado, carga la identidad protegida únicamente para seleccionar datos, la retira del trabajador y utiliza credenciales PostgreSQL SCRAM protegidas. Detiene el clúster si lo inició. Las pruebas usan un clúster diferente y datos sintéticos.

**192 pruebas aprobadas: 110 C# y 82 Python, cero omitidas.** Conservan las 180 anteriores. Build sin errores/advertencias; incluye validación de fuentes/hash, paginación, bloqueo de órdenes, expiración, calendario explícito, separación nativa/derivada, spreads no resueltos, DST regional, contrato estricto, ausencia de look-ahead con señales no vacías, particiones cronológicas, costos prohibitivos y métricas conocidas. Se verificaron la ejecución auténtica, persistencia SQL e idempotencia. Los procesos de descarga terminaron y los clústeres iniciados quedaron detenidos.

Incidencias resueltas: ACL de directorios temporales de Windows en pruebas (pasaron con ejecución aprobada), una firma incorrecta al integrar persistencia detectada por compilación, sintaxis de un resumen PowerShell y anotaciones JSON incompatibles con el contrato estricto (se separaron sin relajar el contrato). La revisión automática rechazó inicialmente la descarga por no reconocer la autorización del adjunto y porque las pruebas aún fallaban; tras aprobar esas pruebas y aportar la instrucción explícita del usuario, autorizó la descarga. No quedan operaciones pendientes de aprobación automática.

Antes de habilitar operaciones Paper faltan evidencia de cierre/moneda de comisión de esta cuenta, reglas efectivas de odd lots/margen y ejecución, slippage y spreads comparables a cada entrada/salida. La comisión de apertura sigue siendo una estimación manual. Más historia no elimina una incompatibilidad de costos con US$100. Esta entrega no habilita operaciones Paper ni recomienda alterar los límites.
