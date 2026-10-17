# Kronos: diagnóstico y recuperación · 2026-10-08

## Resultado

El pipeline observacional funciona: archivo IBKR auténtico → validación → inferencia local → artefactos/PostgreSQL → API → SignalR → Vue. **No se declara una recuperación completa de calidad estadística:** el estado correcto sigue siendo `KRONOS_DEGRADED / RAW_ONLY`. No existe probabilidad calibrada admisible ni demostración de rentabilidad.

No se inicia el rediseño visual. Los cambios de presentación explican el diagnóstico y los timestamps. Cost-Aware conserva su PID 38640. Kronos y el Dashboard tuvieron un reinicio específico para cargar Python y reemplazar la DLL bloqueada. La verificación final detectó suspensión de Shadow por `PAPER_READ_ONLY_DISCONNECTED` a las 04:25:35 UTC: sin latch del operador ni posiciones pendientes, se reconectó el mismo estudio con su comando existente Run, presupuesto cero e identidad Paper verificada. Volvió a persistir observaciones desde 04:46:44 UTC, PID 18784; no se afirma una causa de red que el journal no demuestra. Kronos sigue activo, PID 5212. Sol US$0, EmergencyStop activo, Live bloqueado, PaperAuto sin concesión, cero órdenes y cero llamadas facturables.

## Causas verificadas

1. **Salida del modelo, no ausencia del proveedor.** Código y pesos locales coinciden con el manifiesto. Kronos-base `2b554741eca47781b64468546e77fef3e85130e6` y el tokenizer fijado están disponibles. El decoder upstream devuelve columnas OHLC independientes sin imponer su orden económico; el adapter conserva esos nombres y valores. En la ventana auditada 7/32 trayectorias contienen geometría inválida (por ejemplo high inferior a close). Se preservan sin reparar. Las bandas usan las 25 trayectorias válidas y no son confianza calibrada.
2. **RAW_ONLY es independiente.** No hay señal técnica congelada elegible en la ventana actual: no se inventan barreras TP/SL. El replay ofrece tres ventanas CALIBRATION y dos VALIDATION distintas de la configuración actual, todas con trayectorias inválidas; ninguna puede entrenar calibración. Hay diez outcomes entre configuraciones, cinco observaciones descriptivas del modelo/configuración actual y cero muestras de calibración admisibles. Siguen exigiéndose 100 comparables, 30 por bucket, error ≤0.15, embargo y ventanas no solapadas.
3. **Interrupciones por datos.** El journal registra dos errores iniciales `BAR_ALIGNMENT_REQUIRED` y 105 consultas `STALE_INPUT` entre aproximadamente 22:05 y 22:59 UTC del 7 de octubre. No son 105 fallos independientes del modelo. El calendario auténtico IBKR declara apertura 21:15 UTC: la vela parcial se excluye y tarda en existir el siguiente cierre horario completo. No se aumentó el límite de antigüedad. El contexto auditado tiene 64 velas 1H cerradas y tres huecos declarados, sin relleno. Su archivo contiene 703 velas 1H, 2.782 de 15m y 205 de 4H, con calendario `IBKR historicalSchedule + contractDetails.tradingHours / IBKR_AUTHENTIC_SESSIONS`.
4. **Defectos de recuperación.** El Future fallido impedía reintentar el mismo input; un fallo al persistir la excepción PostgreSQL terminaba el observador; la evaluación sólo veía 64 barras; una ausencia se sellaba prematuramente como outcome inválido; un hit de barrera ocultaba OHLC corrupto posterior. La auditoría halló cuatro registros históricos con invalid_frequency subestimada en 1/32. Ya tenían frecuencia inválida positiva y no podían entrenar calibración. Los originales se conservan; las diferencias están en `trajectory-audit.json`.

## Correcciones

- Reintento de inferencia fallida en la siguiente consulta acotada, manteniendo caché de éxitos, cola y hashes. Reinicio sin reinferencia innecesaria; fallback OOM conservado explícitamente.
- El observador sobrevive a caída del journal, registra `UNAVAILABLE_NOT_PERSISTED` en log y vuelve a consultarlo. La API vence el heartbeat incluso con snapshot cacheado.
- Validación antes de inferencia/evaluación. Se evalúan forecasts antiguos con el archivo completo cerrado y autenticado, separado del contexto del modelo.
- Datos ausentes, duplicados o corruptos quedan pendientes, no resultados ficticios. Una evidencia posterior registra su verdadero tiempo de recepción y conserva el embargo. Un outcome persistido no se duplica después de reiniciar.
- Toda trayectoria se valida antes de clasificar TP/SL. El denominador bruto conserva las muestras inválidas; las bandas son condicionales a las válidas.
- Pipeline y calibración se diagnostican por separado. Puntuaciones públicas de calibración null sin pool aprobado y muestra suficiente; los cálculos descriptivos se conservan como tales.
- Home/Mercado/Research explican degradación, señal ausente, antigüedad y muestra. La tabla identifica apertura UTC y cierre pronosticado. No cambia señales, estrategias, temas ni navegación.

## Estados explícitos

| Estado | Criterio |
|---|---|
| HEALTHY | Heartbeat ≤120s, ventana y forecast recientes bajo los límites fijados, inferencia y todas las trayectorias OHLC válidas, sin fallback degradado. No implica calibración ni autoridad. |
| DEGRADED | Forecast disponible con trayectorias inválidas, fallback CPU por OOM o antigüedad con observador activo; razones visibles. |
| UNAVAILABLE | Heartbeat ausente/antiguo, entrada inadmisible, journal/proveedor inaccesible o inferencia fallida. Forecast anterior sólo para inspección. |

RAW_ONLY, CALIBRATION_INSUFFICIENT, CALIBRATION_DEGRADED y CALIBRATED son estados independientes. Ninguno concede elegibilidad Paper o Live.

## Predicción real y trazabilidad

- ID persistido: `kronos-95c8142e17f4bd9e7e1aec1905af01c323bc5d002b9630f4048207ec75df88c2`.
- Contexto: 64 velas EUR/USD 1H; cierre `2026-10-08T04:00:00Z`; horizonte de 12 barras hasta `2026-10-08T16:00:00Z`.
- Último cierre observado 1.120455 USD/EUR. Cierre mediano de la primera vela futura 1.120188; de la última 1.119379. P05–P95 de la última 1.118101–1.122568, dispersión condicional **sin calibrar**. No es cotización ejecutable ni recomendación.
- Una inferencia local nueva reprodujo exactamente el hash persistido de trayectorias en 2.94s de GPU, con 450.12MiB de memoria pico. Se guardó como verificación, no nueva muestra independiente; no sobrescribió el original.
- Playwright verificó la misma identidad y calidad en API, un evento SignalR real `kronos.updated`, store Vue y gráfico. Capturas desktop/móvil conservadas en el directorio de evidencia.
- Los forecasts forward no habían madurado al verificar. El primero empieza el 7 a las 19:00 UTC y vence el 8 a las 07:00 UTC; cruza una barra parcial de sesión y puede continuar pendiente. No se inventaron outcomes forward. Los históricos siguen identificados `OBSERVED_REPLAY`.

El encabezado del Dashboard conserva por separado la última cotización del experimento EURUSD_PAPER_EXPLORATORY suspendido (7 de octubre): STALE/DATA_UNAVAILABLE. No acredita interrupción del recolector Shadow actual ni del input histórico Kronos, que enlaza su propio archivo y timestamps.

## Verificación

Evidencia: `artifacts/research/kronos/recovery-20261008/`, con logs, resultados, auditorías, inventario y hashes. La suite Python se ejecutó completa; las 17 pruebas inicialmente omitidas por falta de TRADING_TEST_DB se ejecutaron después contra PostgreSQL desechable 55432. Los tests de recuperación/publicación se repitieron tras sus últimos cambios. No se suman ejecuciones repetidas como pruebas nuevas.

| Suite | Pruebas distintas aprobadas |
|---|---:|
| Python, incluyendo 17 de PostgreSQL y 23 nuevas de recuperación | 1.264 |
| C# | 451 |
| Vue | 57 |
| Playwright | 25 |
| Total | **1.797** |

97 pruebas focalizadas Kronos pasan; forman parte del total Python. Los cinco flujos E2E Kronos se verificaron nuevamente después de exigir Brier null sin calibración admisible. Cero fallos pendientes; logs iniciales de restricciones sandbox, DLL bloqueada y medición prematura de resize conservados. PostgreSQL de pruebas se detuvo al finalizar; PostgreSQL Paper 55433 continúa activo.

Debug encontró inicialmente una DLL bloqueada; después del reinicio específico compiló sin warnings/errores. El primer E2E midió el ancho inmediatamente tras cambiar viewport; se corrigió para esperar ResizeObserver, conservando el layout. Se conservan resultados iniciales y finales. ECharts mantiene su warning previo: 613.81kB / 207.52kB gzip; no se ocultó aumentando el umbral.

Pendiente: calidad OHLC del modelo base, calibración independiente suficiente y outcomes forward maduros. Pausas de sesión/fines de semana y ausencia de volumen Forex limitan ventanas admisibles. MIDPOINT no prueba fills/slippage. No se reemplaza modelo, ajustan parámetros ni entrena con validación; prueba final sellada. No se justifica empezar el rediseño visual hasta resolver o aceptar explícitamente estas limitaciones.

Comando de inspección, sin iniciar otra instancia:

```powershell
.\scripts\kronos.ps1 -Action Status
```

El observador corregido permanece activo. La siguiente comprobación útil es revisar outcomes después de sus horizontes con observaciones IBKR completas. Mejorar calidad/calibración requiere un experimento independiente preregistrado; esta recuperación no lo ejecuta.

## Archivos modificados

- `python/trading_agent/kronos/{adapter,contracts,persistence,predictor,projection,worker}.py`
- `python/tests/test_kronos_recovery.py`
- `src/TradingAgent.Api/DashboardService.cs`, `tests/TradingAgent.Tests/KronosTests.cs`
- `frontend/src/types.ts`, `frontend/src/components/{KronosCard,KronosDiagnostics,KronosEvaluation,KronosForecastChart}.vue`, `frontend/src/modules/kronos/KronosHomeCard.vue`
- `frontend/src/__tests__/kronos.test.ts`, `frontend/e2e/{dashboard,kronos-recovery}.spec.ts`, `frontend/playwright.config.ts` (directorio configurable para preservar evidencias anteriores).
- Este informe, enlace desde `kronos-observation.md`, feedback de cobertura Graphify y scripts/resultados de auditoría.

Los 74 hashes protegidos de referencia permanecen idénticos: no se modificaron RiskEngine, AccountBinding, estrategias, pesos/configuración Kronos, límites, reservas operativas ni autorizaciones.
