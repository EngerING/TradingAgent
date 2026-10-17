# EUR/USD V2 — evidencia de costos y límites de calibración

12/oct/2026. Documento de evidencia; **ninguna política operativa activada**.
Artefactos reproducibles en
`artifacts/aggressive-growth-r20-20261010/r20-v2-persistence-20261012/`.

## Hechos, estimaciones y desconocidos

| Concepto | Evidencia | Tratamiento V2 propuesto |
|---|---|---|
| Comisiones | Tarifa publicada IBKR spot FX, tramo inicial:0,20 puntos básicos sobre valor negociado, mínimo US$2 por orden. No hay ejecución R20 IBKR ni commissionReport R20. | Estimación por orden: max(2,0.00002×notional_USD); nunca etiquetarla como cargo confirmado. Verificar entidad, plan y cuenta antes de una política operativa. |
| Spread | 3644 quotes distintas LIVE/OPEN válidas del journal V1. Min0.00001, mediana0.00002, p95/p990.00003, máximo0.00004 USD/EUR. | Entrada: quote fresca verificable; salida: estimación versionada con ventana, sesión, tamaño de muestra y fuente. Percentil histórico no es garantía ni valor aprobado por defecto. |
| Slippage | V1 usaba0.00045 USD/EUR por lado. No existen fills IBKR R20 para medir diferencia respecto al precio contemporáneo. | Desconocido, no cero. Mantener como supuesto explícito de estrés hasta calibrar. Quotes/cambios temporales no equivalen a slippage de ejecución. |
| Financiación | V1 reservaba US$0.25 fijos por operación, sin cálculo por duración. | No cargo confirmado ni curva temporal. Faltan saldo por moneda, plazo, tasas aplicables y condiciones de la cuenta. No sustituir por cero implícito. |
| Margen | Fracciones V1 inicial10%/100%, mantenimiento5% son del modelo. | No acreditan margen IBKR, disponibilidad ni aceptación del tamaño. Mantener validación operativa independiente. |

[Tarifario oficial spot currencies](https://www.interactivebrokers.com/en/pricing/commissions-spot-currencies.php),
consultado12/oct/2026. La tarifa distingue órdenes FX de conversión automática;
no intercambiar ambas. Mínimos pueden verse afectados por modificaciones,
órdenes que permanecen overnight y acuerdos de intermediación. Confirmación
por operación requiere evidencia del bróker, no sólo la página pública.

[Limitaciones oficiales Paper](https://www.interactivebrokers.com/campus/trading-lessons/paper-trading-vs-live-trading-whats-the-difference/):
los fills Paper son simulados y usan el mejor nivel visible, no profundidad
completa. Incluso futuros fills Paper no demostrarán slippage de ejecución real.

## Método de muestreo reproducible

SELECT en transacción REPEATABLE READ READ ONLY sobre3858 revisiones de la cohorte
retirada; head `ec20e823e3b65bfd887ee6f2612b2bbb231082e2729391f055e51c118176830d`.
Filtro: IBKR_PAPER, LIVE, OPEN, available_for_execution=true, bid>0, ask≥bid,
edad de quote entre0 y30s respecto al timestamp de observación. Se excluyeron211
filas inválidas/ausentes/obsoletas; se deduplicaron timestamp,bid,ask. Quedan3644
quotes del12/oct00:39:10.477562 a19:38:39.323723 UTC. Percentil de rango más próximo.

No es cinta de ticks, distribución ponderada por tiempo ni muestra independiente
de todas las sesiones. Hay dependencia temporal y huecos por desconexión. La zona
de recepción no prueba timestamp de exchange. El resultado describe esta muestra;
no autoriza a usar0.3pip como techo futuro ni descarta spreads mucho mayores.

El piso V1 de0.0014 equivale a14pips:35× el máximo observado y70× la mediana.
Es un supuesto del protocolo V1, no una medición. No se cambió retroactivamente.

## Cuatro salidas V1 y contrafactual V2

Se reusan los cuatro trades históricos y se comprueban SHA256 de sus barras.
No hay replay persistido, nuevos fills, señales ni cohortes. Costos V1 y PnL se
reconstruyen en memoria; V1 y BASELINE_1X siguen intactos.

| Operación | q V1 EUR | L al cierre V1 | Target neto V1 USD | Cota q con estrés* | L en mismo precio con esa cota* |
|---|---:|---:|---:|---:|---:|
| R20 primera | 839.17 | 10.001446 | -3.803160 | 827.79 | 9.863046 |
| R20 segunda | 786.47 | 10.007397 | -3.684394 | 775.09 | 9.859554 |
| Baseline primera | 85.46 | 1.000070 | -4.204494 | 85.25 | 0.997607 |
| Baseline segunda | 81.65 | 1.000036 | -4.191280 | 81.43 | 0.997335 |

*Cotas mecánicas de una posición aislada con los costos V1 y shock adverso igual
a distancia al stop+0.00001. Un tick adicional sirve para demostrar la aritmética,
no calibra gaps, slippage ni un buffer operativo. Se verifica mantenimiento
modelado5% y equity positiva. **Estas cantidades no son entradas admitidas V2.**
La comparación Baseline sólo explica historia; V2 no crea esa cartera.

Con capital E, precio P, costos f+cq, límite L y shock adverso g>0, exigir
exposición estresada≤L×equity estresada produce:

```text
SHORT: q ≤ L(E−f) / [P + Lc + (L+1)g]
LONG:  q ≤ L(E−f) / [P + Lc + (L−1)g]
```

Se redondea hacia abajo al paso de cantidad. SHORT aumenta nominal al subir
precio; LONG lo reduce al bajar. Aún deben cumplirse riesgo por precio, capital
asignado, margen inicial y mantenimiento, exposición dura, costos, liquidez,
presupuesto diario y cupo. La cota no sustituye el solver ni es promesa de pérdida
máxima. El núcleo implementado considera también escenarios de cartera existente.

**Resultado de admisión:** el solver V2 rechaza las cuatro entradas normales.
Incluso dando una estimación deliberadamente optimista de sólo US$4 ida/vuelta,
sin spread/slippage/financiación, el máximo target bruto posible bajo capital y
apalancamiento de cada cartera es menor que US$4. La prueba evalúa toda la rejilla
admisible y conserva NONPOSITIVE_NET_TARGET. Eliminar el piso14pips no resuelve
por sí solo la falta de economía de estas operaciones con esos capitales/stops.
No se aumentó exposición para consumir el techo de riesgo20%.

Los cuatro triggers V1 excedieron apenas el límite administrativo; mantenimiento
modelado estaba cubierto. V2 usa L para admisión y holgura, no para cerrar por una
fluctuación mínima. El núcleo no administra posiciones ni demuestra todavía
acciones defensivas reales. El futuro ciclo de vida debe conservar emergencia,
conciliación y defensa ante margen real insuficiente, protección inválida,
exposición dura y recuperación. No se puede inferir que toda liquidación futura
quede evitada ni ignorar una exigencia real del bróker.

## Política definitiva y pendientes

Son definitivos para el diseño: costos excluyentes y trazables, equity que evoluciona,
rechazo de target neto≤0 en entradas normales, dimensionamiento máximo simultáneo,
holgura basada en escenarios, latch diario persistente y perfil explícito inmutable.
Target neto positivo no demuestra ventaja estadística ni rentabilidad esperada.

No quedan fijados como política operativa: slippage, financiación, percentil/
ventana de spread de salida, distribución de gaps, buffers de margen, liquidez,
cantidades aceptadas ni condiciones efectivas IBKR. Sin estas evidencias y una
aprobación explícita del conjunto, no activar una configuración V2 diaria.
Pruebas técnicas requieren identificación/autorización separadas; no relajar
el filtro económico normal ni mezclar sus resultados con evidencia FORWARD.
