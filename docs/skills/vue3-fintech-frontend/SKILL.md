---
name: vue3-fintech-frontend
description: Implementa y verifica el frontend financiero existente de TradingAgent con Vue 3 y TypeScript, componentes tipados, estado en tiempo real y pruebas; no implementa lógica de trading.
---

# Vue 3 Fintech Frontend

Preserva el stack y las versiones instaladas: Vue 3, TypeScript estricto, Composition API, script setup, Pinia, Vue Router, Tailwind, ECharts, SignalR, Vitest, Vue Test Utils y Playwright. Consulta Graphify y lee sólo contratos/componentes afectados antes de editar.

- Componentes para presentación e interacción; ningún sizing, decisión de trading, SQL, credencial o autorización en Vue. Las únicas llamadas son al API autenticado del proyecto; nunca OpenAI/IBKR directos.
- Tipos de dominio explícitos, sin any. Trata respuestas externas como unknown en los límites y valida los contratos que requieran seguridad. Conserva null como desconocido. No conviertas casts TypeScript en prueba de validación.
- Stores pequeños por responsabilidad, shallowRef para snapshots grandes e inmutables; actualiza sólo el slice correspondiente al evento. UI state separado del journal y de los controles protegidos.
- Mantén secuencia, deduplicación y resync de snapshot ante huecos o reconexión SignalR. Serializa eventos para que un refresh lento no sobrescriba deltas posteriores. Coalesce quotes de alta frecuencia de forma acotada; no descartes fills, comisiones, alertas o transiciones.
- Reconexión con backoff acotado, limpieza de timers/listeners al desmontar y STALE durante desconexión. No refresques la página ni reintentes acciones sensibles a ciegas.
- Lazy load de rutas/gráficos cuando reduce carga real; usa ECharts modular y evita dependencias nuevas sin necesidad. Redimensiona con ResizeObserver y libera charts/listeners. Para listas largas usa paginación o virtualización con límites visibles.
- Usa componentes accesibles, botones nativos, labels, focus-visible y diálogos con gestión de foco. Evita HTML o JavaScript generados por modelos; Vue renderiza contratos estructurados con componentes permitidos.
- Comprueba scroll móvil, estado loading/error/empty, performance y budget de assets. No ocultes un warning de build ajustando el umbral sin resolver su causa.

Verificación proporcional: Vitest para lógica de presentación/estado; Vue Test Utils para estados; Playwright para flujo real, teclado, conexión y screenshots. Ejecuta npm run build. Pruebas no deben transmitir órdenes ni consumir OpenAI. Mantén compatibilidad con Python/C# y registra lo ejecutado realmente.
