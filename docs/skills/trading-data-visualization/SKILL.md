---
name: trading-data-visualization
description: Diseña gráficos financieros de TradingAgent con procedencia, unidades e incertidumbre explícitas para mercado, forecasts, calibración y comparación de experimentos.
---

# Trading Data Visualization

Usa los componentes de gráficos existentes. Consulta contratos de datos antes de elegir una visualización; no derives métricas económicas nuevas en el frontend.

- Candlesticks OHLC auténticos; no inventes volumen Forex. Reserva una región futura distinta para Kronos: mediana discontinua, banda de dispersión y línea en el límite del forecast con timestamp UTC. Etiqueta NOW sólo si coincide con tiempo actual; distingue límite de predicción de reloj actual.
- REAL MARKET, KRONOS FORECAST, IBKR PAPER, SIMULATED_SHADOW y LIVE son procedencias distintas. Nunca conectes forecasts como velas realizadas ni combines P&L Paper con Shadow en la misma serie sin separación explícita.
- Todo gráfico útil tiene título, unidades, leyenda, timestamps/tooltips, fuente y estado de calidad LIVE/DELAYED/STALE/MISSING. Sin datos muestra ausencia; no dibujes una línea plana de ganancias inventadas.
- Equity/P&L en USD, drawdown identificado como USD o porcentaje, comparación R1/R5/R10 con escalas compartidas. No mezcles porcentaje, ratio y USD en un eje. EV, expectancy y profit factor insuficientes permanecen null.
- Calibración: eje x probabilidad prevista y eje y éxito observado, ambos 0–1; diagonal ideal, buckets, muestra y error. Frecuencia RAW no es probabilidad real; banda de trayectorias no es intervalo estadístico calibrado. Evita apariencia de precisión con muestras pequeñas.
- Para timelines muestra entrada, fill, protección, salida y comisión con origen y UTC; pendientes no son ganadoras. Spread, comisiones y régimen sólo cuando existan datos con procedencia.
- Preferencia por charts interactivos existentes con tooltips seguros. Proporciona resumen/tablas accesibles y alternativa de teclado cuando el canvas no exponga datos. Mantén contrastes y no dependas sólo de rojo/verde.
- No uses gráficos decorativos ni suavizado que oculte gaps. Datos ausentes no se rellenan con información futura.

Verifica visualmente límites real/futuro, unidades, leyendas, eje de calibración, ausencia de datos y responsive. Para informes exportables usa artefactos reproducibles, no screenshots como evidencia estadística.
