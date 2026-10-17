---
name: tradingagent-ui-ux
description: Diseña y mejora interfaces de TradingAgent para observar mercado, riesgo, experimentos y estados operativos; úsala en tareas de UI/UX, no en cambios exclusivos de backend.
---

# TradingAgent UI / UX

Trabaja sobre Vue existente. Consulta Graphify y las instrucciones del proyecto antes de abrir componentes; amplía con búsquedas dirigidas cuando el índice no cubra el frontend.

## Jerarquía y composición

- La primera pantalla debe permitir distinguir en cinco segundos conexión, entorno Paper, Live bloqueado, EmergencyStop, calidad de datos y actividad. Una conexión UI no acredita conexión IBKR.
- Ordena estado del sistema → mercado y señal → R1/R5/R10 → inventario → forecast → investigación. Mantén Sol accesible desde todas las páginas.
- Usa filas de estado, áreas de trabajo y tablas además de cards. Reserva la expansión progresiva para parámetros, errores técnicos, procedencia y evidencia larga; no ocultes incertidumbre o bloqueos importantes.
- Mantén capital/equity, riesgo próximo, resultado neto, drawdown y detención diaria visibles por perfil. No conviertas ausencia de métricas en cero ni confianza subjetiva en probabilidad calibrada.
- Identifica IBKR PAPER, SIMULATED_SHADOW y KRONOS FORECAST por texto y estructura, además del color. Mostrar un próximo perfil no concede autorización.

## Sistema visual

Fondo #F8FAFC; superficies #FFFFFF; texto #0F172A. Acentos #10B981 / #059669 y #06B6D4 / #CFFAFE. Amber para incertidumbre; rojo para peligro. Evita colorear toda la pantalla de verde.

Usa una escala de espacios consistente de 4/8/12/16/24/32 px, números tabulares y jerarquía tipográfica. Prioriza legibilidad y densidad útil frente a decoración. Verifica contraste, también en textos pequeños y botones; el verde brillante no sirve siempre como texto sobre blanco.

## Estados y acceso

- Diseña estados inicial, carga, vacío, error, desconexión y degradación. Un valor conservado durante desconexión debe estar marcado STALE, no LIVE. Un estado vacío debe explicar qué evidencia falta.
- Mantén navegación por teclado, foco visible, nombres accesibles, orden de encabezados, enlaces de salto y cierre con Escape/restauración de foco en diálogos.
- En móvil evita overflow de página; tablas con scroll localizado y resumen de los campos principales. No ocultes EmergencyStop o calidad para que quepan.
- Skeleton sólo durante carga real; transición corta y respeto a prefers-reduced-motion. No uses animaciones decorativas continuas.

## Verificación

Revisa la UI con datos reales autorizados y fixtures explícitos de ausencia/desconexión. Captura desktop/móvil, comprueba teclado y solapamientos, y ejecuta pruebas Vue/Playwright relevantes. Reporta estados desconocidos sin sustituirlos por estados favorables. Esta skill no autoriza órdenes, permisos, promociones ni cambios de controles.
