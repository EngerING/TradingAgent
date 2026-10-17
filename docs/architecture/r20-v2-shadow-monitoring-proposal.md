# Seguimiento V2 — propuesta precisa, sin nuevo Dashboard

13/oct/2026. La página de configuración diaria ya existe y renderiza los cinco
controles. Esta fase no modifica Vue ni publica un servidor de ciclo. El usuario
permitió entregar propuesta cuando la vista requiriera una fase adicional.

Se propone añadir un panel de sólo lectura en `R20ConfigurationPage.vue`, junto
al estado y presupuesto existentes. Guardar/validar/activar siguen siendo las
únicas mutaciones de configuración; no botones Run, órdenes o permisos implícitos.
Los campos permanecen vacíos hasta selección explícita; cargar historia no activa.

| Sección | Fuente backend y campos |
|---|---|
| Procedencia | clasificación, scope/cohorte real o «sin cohorte», última fuente/timestamp, edad y estado de conexión |
| Configuración | perfil vigente/histórico, cinco valores, versión/hash, vigencia económica, permiso independiente y blockers |
| Señales | decisiones del ledger, ID por estrategia/timeframe/cierre, LONG/SHORT/NO_SIGNAL, hash fuente y motivo de rechazo |
| Posiciones | PositionSnapshot: side, q, entrada/quote, SL/TP, perfil de entrada, exposición, margen modelado y riesgo adicional |
| Contabilidad | equity dinámica, cash, PnL bruto/neto, costos por estado/procedencia, reservas; decimales exactos sin cálculo cliente |
| Límite diario | día/zona, referencia, budget, pérdida utilizada, riesgo abierto/pendiente, restante y latch |
| Historial | trades virtuales completos, precio/quote salida, motivo, PnL/costos, hashes y revisiones |
| Recuperación | estado de conciliación, eventos DATA_UNAVAILABLE, bloqueos persistentes y última valoración válida |

El contrato `ShadowCycle.view()` implementado entrega inventario, trades,
contabilidad diaria, última transición y cabeceras desde una lectura consistente.
El agregador futuro expondrá diagnóstico de señales y desglose contable a partir
de ese ledger, sin crear filas de fills ni usar fixtures como sustituto de datos.

API propuesta: GET `/api/r20-v2/shadow` y GET `/api/r20-v2/shadow/history`, sesión
de lectura, esquema Zod estricto, límites de paginación y decimales como strings.
No permitir scope, rol, equity o cantidad arbitrarios como autoridad HTTP. El
host debe elegir destino y alcance. Sin ledger operativo: NO_COHORT/NO_DATA,
valores desconocidos null; nunca capital de fixture ni saldo millonario Paper.

SignalR futuro: evento de lectura con revisión/hash del estado confirmado. Ignorar
revisiones anteriores y releer snapshot tras reconexión; no inventar continuidad
a partir de eventos perdidos. Un save de perfil no habilita el canal ejecutor.

Desktop: posiciones y presupuesto junto al estado del perfil; móvil: tarjetas
apiladas con side/SL/TP/PnL, sin esconder EmergencyStop, Live o procedencia.
Tabla de historia con scroll contenido, no overflow de página. Pruebas requeridas
en la fase de integración: contratos backend, sesión de lectura, dos perfiles,
sin perfil, UNKNOWN, posiciones abiertas al vencer perfil, cierre/lostACK,
SignalR/reload y Playwright desktop/móvil con DB aislada identificada.

No se presentan capturas nuevas: este panel es una propuesta, no una interfaz
implementada o verificada. Se conserva la evidencia de la UI existente de la
fase anterior; no se suma a las pruebas nuevas.
