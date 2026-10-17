# TradingAgent · aplicación operacional Paper / Shadow

Entrega de WritingBlock 68241, sobre el frontend existente. Identidad propia emerald/cyan, sin copiar una referencia visual ni introducir capacidades de ejecución. Se conserva también la instalación de las cuatro skills y las mejoras de lectura de WritingBlock 81734.

## Experiencia implementada

Home sigue balance → agente → señal → forecast → inventario → resultado. El resumen inmediato identifica inventario del experimento, Kronos, decisión y actividad de Sol. El balance pertenece a **una** cartera virtual seleccionada; no suma R1/R5/R10 ni utiliza el saldo ficticio de IBKR.

- AccountCard: capital, equity, P&L realizado, drawdown y estado del observador. P&L de sesión permanece DATA_UNAVAILABLE: el read model no expone esa métrica; no se inventa una cifra.
- AgentCard: instrumento y temporalidad procedentes del read model; versión Shadow cuando existe evidencia; versión Paper independiente desde la rotación; próxima cartera Paper condicionada; probabilidad y EV conocidas. Una versión desconocida permanece UNKNOWN.
- ProfileQuickCards: equity, riesgo fijo, trades completos, win rate, expectancy, drawdown y estado diario por cartera. Seleccionar una card cambia presentación, no el riesgo.
- OpenInventory/OpenTradeCard: IBKR PAPER y SIMULATED SHADOW en columnas separadas; quantity, entry/current, stop/target, bruto/neto, comisiones, estado, protección, régimen y evidencia. Comisiones/resultados pendientes no se convierten en ganancias. No se atribuye el último forecast a una operación sin un vínculo registrado.
- KronosHomeCard: dirección, frecuencias RAW TP/SL/NEITHER, estado de calibración, muestra, latencia, horizonte y consenso; mini-chart auténtico con futuro separado de velas realizadas. RAW no equivale a probabilidad calibrada.
- TradeFeed: MARKET, SIGNAL, KRONOS, TRADE_OPEN/UPDATE/CLOSE, NO_TRADE, RISK, SOL y SYSTEM. La lista usa origen explícito, filtros, máximo 300 filas conservadas y ventana virtual de nueve filas. No constituye un journal completo: estados recuperados se identifican SNAPSHOT; el historial íntegro permanece en el servidor.
- Sol global: botón persistente; drawer desktop y bottom sheet móvil, Escape, foco inicial, límites de Tab y restauración del foco. Respuestas renderizadas mediante componentes y contrato estructurado, nunca JavaScript generado. Presupuesto cero utiliza evidencia local y no llama a GPT.
- Temas: dark #071A18/#0B2421 con emerald/cyan y light conservado; preferencia local persistente. Ambos afectan superficies y gráficos.

Los botones son navegación y consulta. No se añadieron botones que inicien/pausen/reanuden un runner, concedan autorización o envíen órdenes. La operación protegida del servidor conserva sus comandos externos existentes.

## Arquitectura

`app/` contiene rutas lazy, layout avanzado, navegación inferior y tokens de la aplicación. `modules/` separa dashboard, trading, experiments, market, kronos, research, sol y system. Se eliminó `pages/WorkspaceView.vue`: las páginas avanzadas se trasladaron a rutas de dominio sin perder memoria, reportes, parámetros ni controles de lectura.

`stores.ts` mantiene los slices Pinia existentes del read model. `stores/interface.ts` contiene únicamente tema, selección de cartera y apertura de Sol; `stores/activity.ts` conserva la actividad reciente de la UI, deduplicación y límite de filas. `composables/useInstrument.ts` obtiene metadatos de instrumento desde los contratos. `api.ts`, `realtime.ts` y `types.ts` siguen siendo límites compartidos existentes; no se crearon capas vacías ni conexiones a otros proveedores.

La cadena permanece Vue → ASP.NET API autenticado → servicios de aplicación → journal/IBKR/Kronos/Sol. No hay acceso del navegador a PostgreSQL, IBKR credentials, OPENAI_API_KEY ni secretos HF. Los componentes nuevos no contienen sizing, aprobación ni decisiones de ejecución. Añadir instrumentos exige ampliar los contratos y capacidades del backend, pero no duplicar Home o inventario.

### Eventos existentes

| Hub/evento | Estado de UI afectado |
|---|---|
| market.quote.updated | Mercado + una fila MARKET coalescida |
| prediction.updated | Señal/decisiones + SIGNAL o NO_TRADE por perfil |
| kronos.updated | Forecast y calibración + KRONOS |
| position.updated | Inventario + TRADE_OPEN/UPDATE |
| trade.completed | Historial + TRADE_CLOSE |
| experiment.updated | Carteras/riesgo mostrado + RISK |
| rotation.updated | Próximo perfil y versión Paper |
| connection.updated / study.updated | Estado del sistema/estudio |
| research.updated / journal.updated | Calibración/memoria persistente |
| notification.updated / source.unavailable | Alertas y calidad |
| analysisCompleted | Notificación Sol; su respuesta estructurada llega por API y también se incorpora al feed |

No se inventaron nombres de hub nuevos. Eventos secuenciados/deduplicados; huecos y reconexión recuperan snapshot antes de aplicar deltas posteriores. Un refresh antiguo no sobrescribe datos nuevos después de logout/reconnect. Sólo quotes se agrupan por frame; fills, comisiones y transiciones no se descartan. No hay polling añadido ni recarga de documento.

## Responsive y accesibilidad

Desktop conserva sidebar y workspace de dos columnas. Mobile/tablet estrecha tiene Inicio, Trading, Research, Sol y Más; Más abre la navegación avanzada existente. Sol móvil ocupa 88dvh con scroll interior y áreas seguras. Teclado, skip link, nombres de controles, Tab/Escape y foco fueron verificados. Tablas tienen scroll localizado; canvas cuenta con datos de forecast accesibles. Se respeta reduced motion. Se revisaron capturas dark/light, desktop/móvil y el contraste del diálogo Sol.

## Performance y límites

Rutas y Sol/gráficos se cargan diferidos. Feed virtualizado y limitado; historial de trades paginado a 25 filas. Quotes no redibujan Kronos; el marcador de reloj se actualiza sin reconstruir todas las series. Gráficos se liberan al desmontar y utilizan ResizeObserver.

**Pendiente:** ECharts + renderer genera un chunk de aproximadamente 614 kB (208 kB gzip). Dividirlos artificialmente produjo una dependencia circular confirmada en navegador; se corrigió agrupándolos. Se conserva la advertencia Vite de 500 kB y no se elevó el umbral para ocultarla. Las rutas y componentes de aplicación sí permanecen separados y lazy. No se declara una auditoría WCAG exhaustiva ni un benchmark de rendimiento en dispositivos físicos.

## Verificación y evidencia

| Suite | Aprobadas | Evidencia |
|---|---:|---|
| Python completa | 1.242 | artifacts/ui-ux-20261007/python.log |
| C# completa | 448 | artifacts/ui-ux-20261007/csharp.log y ui-ux.trx |
| Vue / Vitest | 55 | artifacts/operational-ui-20261007/vitest.log |
| Playwright | 23 | artifacts/operational-ui-20261007/e2e-results.json |
| **Total** | **1.768** | 0 fallos finales |

Compilación Release C#: cero errores/advertencias. `vue-tsc` y build Vue: PASS, con advertencia ECharts descrita. Los E2E cubren Home, feed, inventario, R1/R5/R10, Kronos, Sol estructurado, navegación móvil, temas persistentes, teclado y SignalR disconnect/reconnect sin reload. El inventario abierto se prueba con fixture MOCK_TEST_ONLY **sólo en el navegador**, sin escribir al backend o broker. Se conservó el primer intento fallido de E2E; no se presenta como éxito.

Cambios adicionales de lectura heredados de la preparación: estado diario del Shadow en `dashboard_projection.py`, con tres pruebas sobre ausencia, America/Santo_Domingo y cambio de día. No altera política ni ejecutor.

`artifacts/operational-ui-20261007/research-health.json` contiene la comprobación real del read model. Shadow, Cost-Aware y Kronos originales siguen activos; no se detuvieron por el rediseño. Último estado observado: cero posiciones del experimento, cero cierres Paper registrados, EmergencyStop ACTIVE, Live false, PaperAuto UI_NOT_AUTHORIZED y Sol presupuesto cero. Mercado LIVE se observó en la comprobación de lectura; durante algunas pruebas también se mostraron estados STALE/DATA_UNAVAILABLE, que no se sustituyeron por valores favorables. Kronos actualizado sigue DEGRADED/RAW_ONLY; la fracción inválida del forecast más reciente observado fue 46,875%, conservada sin reparar ni convertir en confianza.

Se comprobaron hashes de los 74 archivos protegidos de la línea base: cero cambios. No se concedieron autorizaciones, limpiaron emergencias, transmitieron órdenes, realizaron llamadas OpenAI facturables ni promovieron estrategias. Se detuvo únicamente el PostgreSQL temporal de pruebas después de terminar sus suites; PostgreSQL Paper continúa independiente.

Capturas en `artifacts/operational-ui-20261007/`: home-dark-desktop.png, home-light-desktop.png, home-dark-mobile.png, sol-mobile-sheet.png, sol-panel.png, kronos-market.png, research.png y operations.png. Capturas adicionales de viewport se conservan para revisar tamaños reales sin el escalado de una captura full-page.

## Uso local

Dashboard ya disponible: http://127.0.0.1:5080. No iniciar otra instancia mientras ese puerto esté ocupado.

Si está detenido, desde la raíz:

```powershell
.\scripts\start-dashboard.ps1 -SolBudget 0 -CopyAccessCode
```

El código copiado es acceso local de lectura; pegarlo únicamente en el formulario del dashboard, nunca en el chat ni en logs. No es una autorización de trading. Ctrl+C detiene ese backend UI; no los investigadores independientes.

Frontend de desarrollo opcional:

```powershell
Set-Location frontend
npm run dev
```

Abrir la URL que Vite imprima, utilizando el backend 5080 existente para `/api` y `/hubs`.

Consultas de progreso, sin iniciar otra investigación:

```powershell
.\scripts\eurusd-shadow-research.ps1 -Action Status -Study eurusd-shadow-3786f123021b41e491fc1c9a0b29e6fd
.\scripts\eurusd-cost-aware-research.ps1 -Action Status -Campaign forward-a14466fba41f4a1091438964d3db5899
.\scripts\kronos.ps1 -Action Status
```

Las skills instaladas son tradingagent-ui-ux, vue3-fintech-frontend, trading-data-visualization y tradingagent-product-design; fuentes mantenibles en docs/skills y reglas de aplicación en frontend/AGENTS.md. Senior Software Engineer y consulta Graphify se aplicaron; el grafo de 424 nodos carece de cobertura Vue y se complementó con lecturas dirigidas.
