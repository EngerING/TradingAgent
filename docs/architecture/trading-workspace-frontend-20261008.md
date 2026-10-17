# TradingAgent: interfaz operacional verificada — 2026-10-08

La interfaz existente Vue 3/Pinia/ECharts quedó actualizada y compilada, con verificación visual real en Chromium: escritorio de 1600×1080, móvil de 360×800 y 390×844. No se reemplazó la aplicación ni se cambiaron motores, estrategias o autorizaciones. URL: **http://127.0.0.1:5080/**. Recargar la página permite adoptar la nueva compilación.

Se aplicaron senior-software-engineer, graphify, tradingagent-product-design, tradingagent-ui-ux, vue3-fintech-frontend y trading-data-visualization. Consulta inicial de Graphify: 424 nodos, sin cobertura Dashboard/Vue/Kronos; la limitación y las búsquedas dirigidas están en [frontend-query-feedback.md](../../graphify-out/frontend-query-feedback.md). No hubo extracción ni investigación facturable.

## Entrega funcional

| # | Área | Resultado y evidencia |
|---|---|---|
| 1 | Páginas | Home e indicadores de Mercado modificados directamente. Trading, Experimentos, Research, Sol y Configuración reutilizan los componentes y estilos compartidos. No se añadieron rutas ni controles de ejecución. |
| 2 | Componentes nuevos | `AppCard`, `SectionHeader`, `EmptyState`, `AgentStatus`. Se reutilizaron badges, métricas, skeletons, navegación, tablas, tabs y el dialog nativo de Sol. |
| 3 | Design system | `workspace-tokens.css`: espaciado 4/8/12/16/24/32, radios, tipografía, sombra, foco, superficies y estados. Conserva los colores semánticos de `trading-app.css`. |
| 4 | Móvil | Cuenta → estado → Autotrading → inventario → carteras horizontales → Kronos → feed. A 360 px, equity y estado caben antes de la navegación inferior. Detalles progresivos; sin overflow horizontal de documento. |
| 5 | Escritorio | Equity y estado/Autotrading en la primera fila; inventario y carteras a continuación; feed central y Kronos lateral. Sol abre en drawer sin ocupar permanentemente el contenido. |
| 6 | Temas | Dark emerald/cyan y modo claro persistente. Se corrigieron superficies claras heredadas en señales oscuras. Las capturas esperan a que finalice la transición de tema. |
| 7 | Cuenta | Una cartera seleccionada, US$100 de equity actual, P&L realizado y drawdown del journal, riesgo proporcionado por backend. No se suman carteras ni se muestra el millón ficticio del bróker. Balance de efectivo, capital disponible/reservas Shadow y P&L de sesión permanecen DATA_UNAVAILABLE cuando el contrato no los expone. |
| 8 | Autotrading | Instrumento/timeframe, estrategia y versión según evidencia, régimen, perfil, calibración, EV y motivo de NO_TRADE. Shadow y Paper bloqueado se muestran por separado. Los botones navegan o consultan evidencia; no simulan iniciar/pausar un servicio. |
| 9 | R1/R5/R10 | Equity, riesgo monetario, wins/losses, trades, comisiones, acierto, expectativa, drawdown y estado diario. Selección modifica sólo presentación; detalle desplegable muestra presupuesto diario, pérdida restante y evidencia. UNKNOWN se conserva. |
| 10 | Trade Feed | Categorías existentes más COST_REJECTION y ERROR; filtros y contadores derivados de eventos reales. Almacenamiento acotado a 300 eventos y 9 filas virtuales. SNAPSHOT es estado recuperado, no un historial completo ni trades nuevos. |
| 11 | Kronos | Degradación ámbar con motivos y conteos reales; RAW_ONLY separado de salud del proveedor. Sin señal elegible: `TP/SL probability: NOT_AVAILABLE — NO_ELIGIBLE_SIGNAL`. Bandas descriptivas, no confianza calibrada. |
| 12 | Sol | Drawer escritorio/bottom sheet móvil, preguntas según cartera/inventario/evidencia. Con presupuesto US$0, `LOCAL EVIDENCE · GPT inactivo`. Respuestas del journal, sin llamada OpenAI ni capacidad de modificar controles. |
| 13 | Realtime | Deltas granulares, orden de secuencias, deduplicación y batching exclusivo de quotes conservados. Se corrigió la persistencia de DATA_UNAVAILABLE después de source.unavailable: lectura completa con backoff 1/2/4/8/16/30 s sólo durante recuperación; cancelación por logout/desconexión/epoch. Los deltas normales no solicitan snapshots periódicos. |
| 14 | Accesibilidad | Foco visible, labels, navegación por teclado, Escape y restitución de foco en Sol, tablas accesibles del forecast, estados textuales y reduced motion. Contraste ≥4.5 comprobado para acciones principales/secundarias, Sol, navegación seleccionada y superficie de decisiones. No constituye una certificación WCAG integral. |
| 15 | ECharts | Se retiró el agrupamiento forzado de todo ECharts/zrender en un chunk. Rollup conserva dependencias compartidas y componentes lazy. Mayor chunk: **555.61 kB / 189.14 kB gzip**, frente a aproximadamente 614 kB antes. La advertencia de 500 kB permanece; no se elevó su umbral. Reducir el mayor chunk no implica igual reducción del total de todos los gráficos. |
| 16 | Pruebas | **674 pruebas únicas aprobadas**: Python relevante 121, C# 451, Vue 73, Playwright 29. Fallos finales 0; skips en estas suites 0. Compilación C# Release y Vue/TypeScript aprobadas. No se presenta esta selección Python como ejecución de toda la suite histórica. |
| 17 | Capturas escritorio | [Dark](../../artifacts/frontend-workspace-20261008/accepted/desktop-dark-viewport.png), [Light](../../artifacts/frontend-workspace-20261008/accepted/desktop-light-viewport.png), [Mercado/Kronos](../../artifacts/frontend-workspace-20261008/accepted/market-dark-final.png). Inspeccionadas visualmente después de la ejecución. |
| 18 | Capturas móvil | [360 px](../../artifacts/frontend-workspace-20261008/accepted/mobile-360-viewport.png), [página completa](../../artifacts/frontend-workspace-20261008/accepted/mobile-360-full.png), [Sol](../../artifacts/frontend-workspace-20261008/accepted/sol-mobile-sheet.png). |
| 19 | URL local | http://127.0.0.1:5080/ — sesión protegida de lectura existente; no requiere reiniciar los observadores. |
| 20 | Servicios | Kronos, Shadow y Cost-Aware conservan sus procesos originales; PostgreSQL Paper y API activos. Kronos sigue DEGRADED/RAW_ONLY. EmergencyStop ACTIVE, Live false, ordersSupported false y SolBudget 0. |

## Forecast: coordenadas sin alterar evidencia

El contrato identifica cada vela con su **apertura UTC** (`quantiles.at`), mientras `median/p05/p95` describen su **cierre**. La UI deriva el cierre con el timeframe declarado, sin modificar timestamps originales, cuantiles ni precios en persistencia. Si el timeframe es desconocido, no supone una hora.

Sólo los cierres posteriores al reloj NOW aparecen en la zona futura. Los puntos vencidos se omiten del gráfico y se conservan en la tabla con apertura original y cierre derivado; no se convierten en velas observadas ni se desplazan hacia el reloj actual. NOW queda visible y el rótulo redundante de inicio de forecast se oculta para evitar solapamiento. Tooltips y leyendas distinguen mercado realizado, cierre pronosticado y dispersión no calibrada.

Mercado podía presentar indicadores como ausentes porque consultaba únicamente `quote.features`; los indicadores existentes estaban en `prediction.features`. Ahora se usa el registro completo de la fuente disponible y se expone `QUOTE_FEATURES` o `SHADOW_SIGNAL_FEATURES`, su procedencia y fecha. No se mezclan indicadores recalculados ni se deducen EMA20/EMA50 a partir de otros períodos.

## Estado y límites de evidencia

Snapshot de aceptación: **2026-10-08T06:07:04.6876049Z**, guardado en [snapshot-accepted.json](../../artifacts/frontend-workspace-20261008/snapshot-accepted.json). Kronos: **22 trayectorias válidas / 32; 10 inválidas**, `INVALID_MODEL_OHLC_TRAJECTORIES`, `RAW_ONLY`, sin señal técnica elegible. Este conteo corresponde a esa predicción; la UI recibe los nuevos conteos cuando el observador genera otra. No se cambió ninguna regla ni se declaró HEALTHY.

Shadow continúa `SHADOW_RESEARCH_RUNNING`; Cost-Aware `COST_AWARE_SHADOW_RUNNING`. Workers conservados: Kronos **5212**, Shadow **18784**, Cost-Aware **38640**. [Procesos finales](../../artifacts/frontend-workspace-20261008/processes-final.json) y archivos `*-status-final.json` documentan las consultas de sólo lectura. Las observaciones y forecasts continuaron durante los builds.

No hay posiciones registradas en el estudio mostrado; esto no sustituye conciliación de toda la cuenta IBKR. La versión Shadow no expuesta permanece UNKNOWN, y la versión Paper se rotula por separado. Calibración, EV y probabilidades insuficientes siguen sin valor favorable. Una recuperación de la interfaz no demuestra rentabilidad ni autoriza Paper/Live.

Se observaron avisos transitorios de fuente no disponible. Se corrigió el defecto de recuperación del cliente, no se atribuye ni se declara resuelta la causa de toda indisponibilidad posible del backend. Los fallos siguen mostrando evidencia STALE hasta obtener un snapshot completo. La investigación de nuevas métricas de efectivo/sesión o de causas del proveedor queda fuera de esta fase visual.

## Archivos y verificación

Manifiesto con rutas y SHA-256: [files.json](../../artifacts/frontend-workspace-20261008/files.json). Cambios funcionales concentrados en:

- `frontend/src/modules/dashboard/`: HomePage, AccountCard, AgentCard y nuevo AgentStatus.
- `frontend/src/modules/experiments/ProfileQuickCards.vue`, `modules/trading/OpenInventory.vue`, `modules/kronos/KronosHomeCard.vue`, `modules/market/MarketPage.vue`.
- `frontend/src/components/`: AppHeader, KronosCard, KronosDiagnostics, KronosForecastChart, SolChat; nuevos AppCard, SectionHeader y EmptyState.
- `frontend/src/app/workspace-tokens.css`, `main.ts`, `chart-options.ts`, `stores/activity.ts`, `realtime.ts`, `frontend/vite.config.ts`.
- Tests: `product-ui.test.ts`, `realtime-lifecycle.test.ts`, nuevo `workspace-redesign.test.ts`, `e2e/dashboard.spec.ts` y nuevo `e2e/workspace-redesign.spec.ts`.
- Nota de Graphify y este informe. Sin cambios de dependencias ni archivos de configuración de ejecución.

Evidencia: [Playwright JSON](../../artifacts/frontend-workspace-20261008/accepted/e2e-results.json), [Vitest](../../artifacts/frontend-workspace-20261008/vitest-final.log), [Python](../../artifacts/frontend-workspace-20261008/python-relevant-tests.json), [C# TRX](../../artifacts/frontend-workspace-20261008/backend-tests/frontend-workspace.trx), [verificación final](../../artifacts/frontend-workspace-20261008/verification.json).

Los fallos intermedios de configuración del harness, fixture incompleto, selector del antiguo launcher móvil, posición del estado a 360 px y contraste heredado se corrigieron y se conservaron los resultados/capturas intermedios en directorios separados. La ejecución aceptada no usa retries Playwright.

**74 archivos protegidos idénticos** al baseline: [protected-verification.json](../../artifacts/frontend-workspace-20261008/protected-verification.json). No se modificaron RiskEngine, AccountBinding, autorizaciones, emergencia, estrategias, datasets sellados, configuración/modelo de Kronos ni límites operativos. Cero órdenes y cero llamadas facturables a OpenAI. Sólo el clúster desechable de tests fue iniciado y detenido; los servicios de investigación permanecieron activos.
