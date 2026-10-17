# R20 V2 — preparación sin activación

Esta fase prepara lectura, control y seguimiento en laboratorio. No autoriza
cohortes, perfil diario, permisos Shadow operativos ni órdenes IBKR. TestStore
sigue restringido a 127.0.0.1:55432/trading_test y system_identifier conocido.
No existe fallback de ese store hacia Paper. Journal011 permanece separado.

## Política de costos y margen

Se conserva `config/r20-v2-cost-policy.proposed.json`, sin activarla ni reducir
supuestos para hacer rentable una señal. Ningún dato de esta fase es un fill ni
commissionReport R20. Política propuesta EURUSD_COST_PROPOSAL_V1:

| Componente | Evidencia y tratamiento | Gate |
|---|---|---|
| Comisión | Tarifa spot publicada: nivel I 0,20 bp, mínimo USD2 por orden; estimación por evento cobrable, no cargo confirmado. Introducer, modificaciones y condiciones de cuenta pueden añadir cargos. | Requiere validar plan/canal y número de eventos cobrables antes de adoptar política. |
| Spread | Bid/ask observados por callback y estadísticas históricas. Precio modelo midpoint; costo RT=(spread entrada+salida)/2 × cantidad. Piso legado 0,0014 conservado, no calibración nueva. | La observación actual no acota spread de salida ni gaps. |
| Slippage | 0,00045 por lado es supuesto legado, no cota empírica. Sin fills no se atribuye medición. | UNBOUNDED, bloquea entradas normales. |
| Financiación | Reserva fija histórica USD0,25 no cubre duración ni saldos por moneda. Tasas publicadas varían; faltan horizonte y saldo deudor/acreedor verificables. | UNKNOWN, bloquea entradas normales. |
| Margen inicial/incremental | Metadata de contrato, saldo total o mínimo publicado no prueban requerimiento incremental de la cuenta. | UNKNOWN. No what-if/placeOrder para obtener evidencia. |
| Mantenimiento | Debe evaluarse conjuntamente con exposición y equity neta bajo LONG/SHORT y shocks. Fracciones sintéticas no acreditan margen real. | UNKNOWN operativo. |
| Exposición/holgura | Solver V2 conserva estrés de nominal, pérdida de equity, costos y margen. No se añade porcentaje arbitrario. Límite administrativo bloquea aperturas, no cierra por fluctuación mínima. | Toda cota necesaria debe tener evidencia versionada; falta implica rechazo. |

Fuentes revisadas: [comisiones spot](https://www.interactivebrokers.com/en/pricing/commissions-spot-currencies.php),
[tasas y financiación](https://www.interactivebrokers.com/en/trading/pricing-margin-rates.php),
[benchmark por moneda](https://www.interactivebrokers.com/en/trading/margin-benchmarks.php),
[requisitos de margen](https://www.interactivebrokers.com/en/trading/margin-requirements.php).
No se extrapolan condiciones de CFD a EUR/USD cash. Tarifas publicadas y quotes
observadas admiten cálculos informativos con procedencia; no eliminan UNKNOWN
críticos. Target neto<=0 rechaza entradas normales, positivo no prueba ventaja.

## Frontera de lectura auténtica

`PaperReadSource` usa el transporte read_only/Research y AccountBinding existentes.
ManagedAccounts debe coincidir exactamente. Cada fallo cierra la conexión; otro
poll recrea sesión y valida identidad nuevamente. No conserva quotes para un fill.
Cada sondeo es acotado y termina desconectado, incluso si falla.

`assess_market` comprueba fuente IBKR_PAPER, datos LIVE tipo1, sesión OPEN y
calendario, geometría bid/ask, edad0..30s, barras MIDPOINT nativas completas y
última barra esperada. Usa ForexCalendar/normalize existentes, nunca rellena,
remuestrea ni altera el motor. Barras futuras no influyen. Se preservan timestamps
de recepción y source_timestamp; null no significa timestamp de exchange.

El resultado AUTHENTIC_IBKR_READ_ONLY_DIAGNOSTIC siempre tiene entryEligible=false.
No acepta posiciones, perfil, cantidad o permisos del frontend. La lectura no
es una cohorte. ShadowCycle y SQL conservan rechazo de fuente no sintética.
El adaptador operativo futuro deberá ligar identidad/fuente/política a un store
operativo separado; no se permite renombrar un evento auténtico como sintético.

## Runner, Stop y recuperación

Runner de replay autónomo preparado en `r20_runner.py`. El CLI admite Status,
Stop y Replay sólo con DB test, contexto explícito y preregistro previo. No instala
schema, activa perfil, crea permiso o prepara ledger implícitamente. Replay exige
archivo SYNTHETIC_TEST_ONLY; no hay comando Run operativo. Sin perfil vigente o
permiso independiente la admisión rechaza. Las decisiones usan el motor R20 sin
modificarlo. Un manifiesto inmutable liga fuentes Python/SQL/config y semántica
del Stop/día/salidas. Los perfiles y eventos conservan sus hashes particulares.

Stop se registra append-only en PostgreSQL. Comparte advisory lock con reserva y
apertura; triggers bajo el mismo lock rechazan entradas posteriores incluso si
se llama directamente a ShadowCycle. Rollback revierte tanto contabilidad como
evento. Retry idéntico devuelve recibo previo: no es una nueva apertura.

Semántica V2: bloquear nuevas entradas y liberar reservas pendientes; gestionar
inventario hasta SL/TP o salida defensiva válida. Stop no crea cierre inmediato
OPERATOR_STOP, a diferencia del contrato V1. Datos inválidos conservan posición.
STOPPED sólo cuando no hay inventario ni pendientes. No se borra Stop ni se
reactiva un scope. Perfil caducado no impide gestión; presupuesto diario y
ECONOMIC_BOUNDARY_UNVERIFIED conservan sus protecciones. No se levantan EmergencyStop
ni bloqueos de conciliación por medianoche.

Singleton por archivo bloqueado durante toda ejecución en un workspace/DB;
pruebas entre procesos y salida abrupta. No es exclusión durable entre máquinas
ni por cuenta IBKR. No hay autorrestart ni servicio instalado. La CLI recarga
estado persistido y usa claves estables de replay, nunca reenvía una orden.
El Stop requiere que un gestor continúe ejecutándose para seguir posiciones.

Salidas basadas en quote fresca; gaps usan precio disponible y no precio ideal.
No se infiere orden intrabar ni ejecución alojada en IBKR. Antes del runner
auténtico hay que aprobar tratamiento de barras perdidas y reconexión.

## V1 y permisos

Wrapper Prepare denegado antes de cargar DB. AggressiveGrowthStore deniega primer
append operativo con head0 en55433; lecturas y recuperación de head existente se
conservan. Ambas configuraciones DLL Debug/R20 deben compilarse. Engine V1 y
protocolo no cambian. SQL directo y binarios históricos externos a los launchers
siguen fuera del control aplicativo: no se revocaron grants ni cambió011, según
restricción. No afirmar exclusividad global de cuenta ni retirada total.

Reader y administrador acceden a proyección GET; no tienen endpoint open/stop/order.
Rol Shadow de test puede registrar Stop y gestionar, nunca activar perfil o crear
permiso. Bootstrap de laboratorio puede preregistrar; no sustituye credenciales
operativas individuales. La autorización Paper permanece ausente.

## Seguimiento y despliegue

Panel R20ShadowMonitor dentro de la ruta existente R20ConfigurationPage. Endpoint
autenticado GET /api/r20-v2/shadow en host de laboratorio5182, sin mutaciones.
Datos vienen de ledger, validación Zod, decimales string y etiqueta sintética.
Muestra inventario, SL/TP, costos realizados/reservados, equity, PnL bruto/neto
por trade, capacidad diaria, señales/rechazos, revisión/hash y recuperación.
Refresco explícito; fallo conserva corte marcado STALE. Estado PREPARED_REPLAY
no se presenta como heartbeat activo. No se añadió SignalR V2 en esta fase.
Compilación aislada no despliega dist ni reinicia Dashboard5080.

Checklist para autorización posterior:

1. Aprobar política versionada con cotas justificadas de costos y margen, o aceptar
   explícitamente sólo diagnóstico sin aperturas. UNKNOWN crítico sigue bloqueando.
2. Revisar store operativo y schema V2 aditivo separado011, roles individuales y
   restauración; autorizar despliegue explícitamente. Nunca quitar TestStore guard.
3. Cerrar frontera real lectura→admisión→gestión, salida/gaps, recuperación de
   medianoche y prueba de Stop operativa. Verificar singleton objetivo de despliegue.
4. Desplegar API/lectura/panel sin runner ni perfil; verificar autenticación y
   decidir publicación SignalR/polling. Revalidar evidencias en ese entorno.
5. Usuario elige los cinco campos del día Santo_Domingo, sin valores preseleccionados;
   guardar/validar/activar no concede permiso. Confirmar capital lógico, políticas
   y hashes del artefacto desplegado.
6. Emitir permiso Shadow independiente; preregistro nuevo sólo tras autorización
   explícita posterior. Confirmar fuente fresca, cero runners, recuperación y Stop.
7. Autorizar un único arranque supervisado Shadow. V1 permanece STOPPED.

Ni este checklist ni permiso Shadow autorizan PaperAuto/Live, órdenes IBKR,
omisión de RiskEngine/ExecutionGuard o limpieza de EmergencyStop.
