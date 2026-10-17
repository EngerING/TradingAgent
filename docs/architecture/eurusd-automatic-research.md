# Entrega D: investigación automática de EUR/USD

Fecha: 2026-10-04. Implementada y ejecutada con datos auténticos de la entrega C. Es una **demostración técnica**, con evaluación económica incompleta. Cero órdenes, Live bloqueado y cero llamadas a OpenAI. El proceso es offline: no conecta con TWS y no cambia Read-Only API. No certifica de nuevo el estado actual de la interfaz TWS.

Ampliación posterior: [seis meses de historia, calendario auténtico y evidencia de costos](eurusd-history-and-costs.md). Las cifras siguientes conservan la captura inicial de D.

## Resultado observado

Corte del informe: `2026-10-04T07:18:36.304840Z`. Identificador de ejecución: `ea7ce12d197c51f99a0806ce1bc4a82b91487f8348cacdf88a65133a45cc9e94`. La captura cubre la semana que empieza el 27 de septiembre; el último cierre 15M/1H es el 2 de octubre a las 21:00 UTC. No representa condiciones actuales ni una muestra suficiente para evaluar rentabilidad.

| Temporalidad | Velas nativas ya almacenadas en C | Originales recibidos conservados | Serie normalizada D | Barras cortas excluidas |
| --- | ---: | ---: | ---: | ---: |
| 15M | 475 | 475 | 475 | 0 |
| 1H | 115 | 120 | 115 | 5 |
| 4H | 26 | 35 | 25 | 10 |
| Total | 616 | 630 | 615 | 15 |

Las 616 filas de `market_candles` permanecen intactas. Se recuperaron también los originales locales 1H/4H descartados durante C, después de comprobar que cada vela retenida en PostgreSQL tiene idéntico timestamp y OHLC en el archivo recibido. Los 630 originales quedaron archivados en un snapshot separado de los 615 datos normalizados. Se conservan timestamps de recepción y hashes de los archivos 1H/4H; la evidencia de recepción de 15M continúa en las observaciones de C.

La barra 4H del viernes a las 20:00 UTC cierra efectivamente a las 21:00, aunque su intervalo nominal termina a las 00:00. D la excluye, de modo que aparecen 25 barras completas frente a las 26 retenidas por C. No se modifica su OHLC ni se elimina su registro original.

No se encontraron duplicados, precios inválidos ni aperturas esperadas ausentes dentro del rango normalizado, **según el calendario provisional configurado**. Esto no certifica cobertura anterior/posterior a la captura ni excepciones históricas desconocidas.

## Calendario y normalización

`config/forex-sessions.json` versiona sesiones en `America/New_York`, abiertas domingo a jueves a las 17:15 y cerradas al día siguiente a las 17:00. `tzdata==2026.5` permite resolver DST también en Windows. Las conversiones de invierno/verano tienen pruebas. IBKR publica ese intervalo semanal para IDEALPRO; el descanso diario también figura en su material educativo. El contrato auténtico capturado en C corrobora la plantilla para la semana siguiente. [Horario Forex de IBKR](https://www.interactivebrokers.co.uk/es/trading/cacheFX.php), [explicación del descanso diario](https://www.interactivebrokers.com/campus/trading-lessons/client-portal-order-entry/).

Aplicar esa plantilla a la semana anterior es una inferencia explícita, marcada `PROVISIONAL_REGULAR_TEMPLATE`. La cobertura inicial es 2026-09-27 a 2026-10-10. `overrides` acepta una fecha de apertura con `null` para cerrar la sesión o un objeto `opens`/`closes` para cambiarla. No se convierten automáticamente festivos de liquidación en cierres de negociación. Antes de ampliar la muestra deben verificarse las excepciones y el anclaje de las barras del contrato para las nuevas fechas. [Calendario de liquidación de divisas de IBKR](https://investors.interactivebrokers.com/en/general/currencyHoliday.php?ib_entity=ir).

Los timestamps deben contener zona horaria y se comparan en UTC. La documentación de IBKR advierte que los timestamps textuales dependen de la zona elegida en TWS; la captura C usó timestamps intradía epoch y los convirtió a UTC. [Recepción de barras históricas](https://www.interactivebrokers.com/docs/tws-api/doc/market-data-historical/historical-bars/receiving-historical-bars).

La serie nativa usa una rejilla UTC explícita, adecuada a esta captura. Una barra se incluye si su intervalo completo está dentro de una sesión, está alineada y ha cerrado antes del corte. Se auditan apertura, cierre nominal, cierre efectivo, frontera y motivo de exclusión. Las barras de apertura 1H duran 45 minutos; las 4H de apertura y cierre duran menos de cuatro horas. Se excluyen de los indicadores de intervalo uniforme.

Las fechas sin zona, los duplicados, el desorden, los OHLC no finitos/inconsistentes y una temporalidad incorrecta hacen fallar la validación. Una interrupción programada no es un gap. Una apertura completa ausente se registra como gap y reinicia el calentamiento posterior, sin rellenar precios. El calendario finito evita extrapolar sesiones indefinidamente.

La ejecución usa exclusivamente barras nativas completas. Existe una agregación opcional separada de 15M hacia 1H/4H: exige los 4/16 constituyentes consecutivos, completos y dentro de una misma sesión. Sus resultados son derivados, nunca nuevos originales IBKR. No se utilizó para este informe y no completa huecos.

## Indicadores y clasificación

`config/research-indicators.json` fija parámetros antes de ejecutar. Python reutiliza los cálculos existentes de EMA y Wilder RSI/ATR, sin modificar sus módulos. EMA se inicia con la media simple de su período; RSI necesita 14 cambios, ATR14 usa una media inicial de 14 rangos verdaderos y el primer rango es high-low. MACD es EMA12 menos EMA26, con EMA9 de la línea disponible. El histograma resta esa señal.

La pendiente es la diferencia de EMA dividida por el número configurable de barras. La volatilidad es la desviación poblacional de 20 retornos logarítmicos y el cociente ATR/cierre. El rango es high-low. No se anualiza la volatilidad ni se inventa volumen/spread para MIDPOINT.

Valores utilizables, descontando calentamiento y exclusiones:

| Indicador | 15M | 1H | 4H |
| --- | ---: | ---: | ---: |
| RSI14 | 461 | 101 | 11 |
| EMA20 | 456 | 96 | 6 |
| EMA50 | 426 | 66 | 0 |
| MACD 12/26 | 450 | 90 | 0 |
| Señal MACD9 | 442 | 82 | 0 |
| Histograma MACD | 442 | 82 | 0 |
| ATR14 | 462 | 102 | 12 |
| Pendiente EMA20 | 455 | 95 | 5 |
| Pendiente EMA50 | 425 | 65 | 0 |
| Desviación de retornos20 | 455 | 95 | 5 |
| Rango | 475 | 115 | 25 |
| ATR/cierre | 462 | 102 | 12 |

Durante el calentamiento los valores son `null`. El estado completo exige RSI, ambas EMA, señal MACD, ATR, pendiente lenta y volatilidad. Necesita al menos 51 barras con esta configuración. Los indicadores parciales se conservan aunque el estado sea `INSUFFICIENT_DATA`.

Reglas deterministas: alcista si EMA20−EMA50 > 0.25 ATR, pendiente EMA50 > 0.03 ATR y pendiente EMA20 positiva; bajista con las condiciones simétricas negativas; lateral en los demás casos preparados. Volatilidad elevada si ATR/cierre ≥ 0.002, reducida si ≤ 0.0004 y normal entre ambos. Sin calentamiento completo se marca indeterminado. Los umbrales son hipótesis configurables, sin entrenamiento ni optimización sobre esta semana.

| Temporalidad | Alcista | Bajista | Lateral | Indeterminado | Vol. elevada / normal / reducida / indeterminada |
| --- | ---: | ---: | ---: | ---: | --- |
| 15M | 36 | 207 | 182 | 50 | 0 / 302 / 123 / 50 |
| 1H | 0 | 48 | 17 | 50 | 0 / 65 / 0 / 50 |
| 4H | 0 | 0 | 0 | 25 | 0 / 0 / 0 / 25 |

Último cierre observado: 15M lateral con volatilidad normal, RSI 50.33 y ATR 0.00065538; 1H bajista con volatilidad normal, RSI 47.83 y ATR 0.00156861. 4H es `INSUFFICIENT_DATA`: tiene RSI y ATR parciales, pero no EMA50 ni MACD completo. Estas condiciones describen el cierre histórico del viernes.

## Contrato multitemporal y estrategias

Cada señal contiene `signal_at`, entrada propuesta y contexto con tres roles: 4H contexto, 1H confirmación y 15M entradas. Cada marco lleva corte, estado, indicadores y `closed_at`. La selección usa el último cierre menor o igual al instante de la señal. La entrada usa la apertura de la siguiente barra 15M completa; un gap o la ausencia de esa barra produce rechazo. No se usan los high/low/close de entrada para generar la señal.

Se registraron tres versiones 1 con hash de calendario, parámetros y versión del motor. Son candidatas de investigación; no autorizan ejecución:

- Tendencia: cruce EMA20/EMA50 en 15M; 1H confirma la dirección y 4H debe estar preparado sin dirección contraria.
- Retroceso: tendencia 15M; la vela toca EMA20 y cierra recuperándola en la dirección de la tendencia; mismas comprobaciones superiores.
- Reversión: 15M lateral; RSI vuelve a superar 30 o a caer bajo 70. No exige alineación direccional de los tres marcos.

Todas usan stop `max(0.00005, 2 ATR)` y objetivo `max(0.00005, 3 ATR)`, calculados con información ya cerrada. Salen por stop, objetivo o regla: cruce contrario para tendencia/retroceso; RSI50 para reversión. El contexto superior inválido provoca salida de tendencia/retroceso; abandonar el estado lateral invalida reversión. La salida por regla se aplica en la siguiente apertura. Si una vela toca stop y objetivo, se considera primero el stop; un gap adverso conserva el peor precio de apertura. Se registra también el cierre por suspensión de riesgo o fin de muestra.

## Evaluaciones y preservación del capital

| Hipótesis | Señales | Aceptadas | Operaciones | Resultado neto |
| --- | ---: | ---: | ---: | --- |
| Tendencia | 5 | 0 | 0 | Desconocido (`null`) |
| Retroceso | 33 | 0 | 0 | Desconocido (`null`) |
| Reversión | 1 | 0 | 0 | Desconocido (`null`) |

Las 39 propuestas pasaron por el `RiskEngine` C# existente y fueron rechazadas con `EXECUTION_DATA_INCOMPLETE`. Las 38 de tendencia/retroceso también tienen `MULTITIMEFRAME_INSUFFICIENT_DATA`. Se conservaron ambos motivos. Las tres evaluaciones tienen estado `INCOMPLETE_COSTS`. Cero operaciones admitidas no equivale a rentabilidad neta cero: el resultado neto sigue desconocido.

El simulador admite escenarios de costos declarados para pruebas: spread, comisiones de apertura/cierre, comisión por unidad, slippage, gap adverso y restricciones de cantidad/margen. Los costos de ida y vuelta se cargan una sola vez. Cada entrada requiere viabilidad económica del motor existente. En la ejecución auténtica no se introdujeron supuestos gratuitos: MIDPOINT no proporciona spread histórico, la última cotización era no disponible y las restricciones del contrato de C no estaban verificadas. Se dejaron los costos desconocidos y se bloqueó la admisión.

Cada hipótesis inicia su propio estado `SIM-*` con **US$100 y presupuesto acumulado US$20**. No consume el saldo Paper ni ejecuta sus señales. Como no se admitieron operaciones, equity permanece US$100 y pérdida consumida US$0. Las ganancias hipotéticas no reponen pérdidas acumuladas. Los límites diarios, semanales y drawdown existentes siguen vigentes. Una prueba de gap que supera US$20 comprueba suspensión de entradas posteriores; el presupuesto de riesgo no garantiza fills de stop. El motor de riesgo original no fue modificado.

## Persistencia, reproducción y contexto Sol

Se verificó PostgreSQL protegido en loopback:55433: 616 velas nativas intactas, snapshot con 630 originales, otro snapshot con análisis, tres versiones, tres backtests, 39 decisiones y 39 evaluaciones de riesgo. Los snapshots contienen indicadores, clasificación por cierre, auditoría de exclusiones, parámetros, contexto multitemporal y señales. Todo se guarda en una transacción usando las estructuras existentes. El usuario de aplicación dispone de SELECT/INSERT, sin UPDATE/DELETE sobre originales e investigación. Repetir un dataset/corte/configuración idénticos es idempotente; el test de integración lo comprobó.

`artifacts/research/<runId>.json` contiene el informe completo y `<runId>.sol-context.json` contiene instrumento, roles, indicadores, condición, calidad, estrategias, evaluaciones y riesgo US$100/20. Son archivos locales ignorados por el repositorio. El contexto estructurado está preparado para un adaptador posterior de Sol; no existe todavía una integración activa, una respuesta de modelo ni una autorización basada en IA. `openaiEnabled=false`.

Ejecución desde la raíz con `.venv` y autorización local ya configuradas:

```powershell
.\.venv\Scripts\python.exe -m pip install -r python/requirements-research.txt
dotnet build TradingAgent.sln -m:1
.\scripts\run-market-research.ps1
```

El script carga la autorización DPAPI vigente solo para seleccionar el dataset, convierte la identidad a una clave interna y retira la identidad/atestaciones del entorno del trabajador. No consulta TWS. Usa PostgreSQL SCRAM con las credenciales protegidas existentes, guarda los artefactos y detiene el clúster si lo inició. El trabajador Python recibe solo JSON y un entorno reducido, sin credenciales de base de datos/bróker ni cliente IA. Hay límites de dataset y timeout. Para repetir exactamente este corte se puede proporcionar `-AsOf '2026-10-04T07:18:36.304840Z'`.

## Verificación y pendientes

Ejecutado: build sin errores ni advertencias; **107 pruebas C# y 73 Python aprobadas, cero omitidas**. Incluye 15 pruebas nuevas Python y 13 C# sobre valores RSI/ATR/MACD/EMA, calentamiento, clasificación, DST, sesiones excepcionales, fronteras, gaps sin relleno, corte temporal, multitemporal, costos de ida/vuelta, stops ambiguos, salida siguiente apertura, presupuesto, independencia del saldo Paper y persistencia idempotente. Las regresiones previas pasaron. También se ejecutaron la compilación Python y la demostración de riesgo.

Incidencia de instalación: el primer intento de instalar `tzdata` falló por timeout/bloqueo de archivo temporal de Windows; el reintento con directorio temporal local aislado completó la instalación. La ejecución auténtica y la verificación SQL terminaron sin errores. Los clústeres locales iniciados para estas comprobaciones quedaron detenidos.

Para evaluar rentabilidad hacen falta más datos: como mínimo 26 barras completas 4H adicionales para el estado técnico de 51 barras, y una muestra mucho mayor que abarque diferentes regímenes, con un período de validación separado. Propuesta de investigación: ampliar inicialmente varios meses y establecer desarrollo/validación antes de ajustar parámetros; alcanzar calentamiento no acredita suficiencia estadística. Se necesitan históricos BID/ASK o evidencia de spread con timestamps, comisiones efectivas de entrada/salida, slippage/gaps y restricciones de cantidad/margen verificadas. También se deben confirmar calendario histórico, festivos y rejilla del contrato a ambos lados de DST. No se descargaron nuevos datos en esta entrega.

Componentes relevantes: `research_calendar.py`, `research_indicators.py`, `research_analysis.py`, `ResearchSimulation.cs`, `ResearchRunner.cs`, `ResearchStore.cs` y `run-market-research.ps1`. Graphify localizó primero los módulos existentes; el grafo previo no incluía las adiciones C/D y sus resultados se contrastaron mediante lecturas dirigidas. Los módulos originales de riesgo y transporte IBKR permanecen intactos.
