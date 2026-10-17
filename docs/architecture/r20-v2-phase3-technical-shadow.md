# R20 V2 fase 3: validación técnica Shadow

## Alcance y frontera de autoridad

TECHNICAL_VALIDATION es un propósito versionado exclusivo de SHADOW. Sólo permite
omitir el rechazo `NONPOSITIVE_NET_TARGET`. No omite costos desconocidos, datos,
riesgo, exposición, margen, reservas, pérdidas diarias, Stop, permisos ni integridad.
`NORMAL` conserva su criterio y su hash de cálculo anterior. Un target positivo
no es evidencia de rentabilidad esperada; un ensayo técnico puede perder incluso
cerrando por Take Profit. No existe permiso Paper derivado de esta excepción.

El laboratorio conserva TestStore, clasificación sintética y UUID de base en
55432. No se habilita un store operativo, se migra Paper, ni se inicia una cohorte.
No hay nueva ruta HTTP de ejecución. El ciclo con fuentes auténticas todavía no
está habilitado: `ReadOnly` y el replay tienen fronteras distintas.

## Preparación, permiso y admisión

1. Se guardan y validan los seis valores explícitos y el propósito. Riesgo,
   pérdida diaria y máximo de posiciones siguen vacíos inicialmente en la UI.
   El ejemplo 100/20/20 representa capital, asignación y multiplicador; no decide
   los tres límites pendientes ni el cap agregado independiente.
2. `bind_preparation` lee la última preparación VALIDO, SHADOW y vigente. Devuelve
   un contexto ligado al hash, propósito y asignación. No activa ni concede permiso.
3. Un administrador de perfiles realiza las transiciones existentes de laboratorio
   con valores explícitos. El perfil activo debe concordar con la preparación.
4. Una acción independiente del propietario del laboratorio puede emitir el permiso
   sintético ligado a preparación/contexto/ventana. Los roles de lectura, perfil,
   Shadow y Paper no pueden emitirlo. No se añadió automatismo a guardar/validar.
5. Python resuelve el vínculo antes de reservar/abrir. PostgreSQL lo verifica de
   nuevo bajo el lock común, incluyendo la preparación que compite con el commit.
   Perfil nuevo afecta nuevas aperturas; no cambia cantidad, SL/TP ni costos de
   posiciones existentes. La gestión no requiere renovar un perfil caducado.

La recepción de una respuesta perdida recupera el mismo resultado idempotente.
Una reserva abandonada se libera tras una observación válida y se conserva la
identidad consumida de la señal; no se fabrica una apertura a precio antiguo.

## Dimensionamiento y contabilidad

El solver elige la mayor cantidad de la grilla que cumple simultáneamente:

- Riesgo por precio `q × distancia_SL ≤ equity_elegible × riesgo_pct / 100`.
- Exposición objetivo `q × precio ≤ asignación_USD × multiplicador_asignación`.
- Margen inicial modelado y costos reservados dentro de la asignación y capacidad.
- Cap agregado, holgura de escenarios LONG/SHORT, exposición dura y mantenimiento.
- Liquidez, máximo de posiciones/reservas y capacidad neta diaria compartida.

Neto al TP = `2 × q × distancia_SL − costos_RT`; pérdida neta al SL =
`q × distancia_SL + costos_RT`. Sólo la primera condición económica de neto TP
puede ser no positiva en TECHNICAL_VALIDATION. No se aumenta q para pagar comisiones.
La asignación no equivale al presupuesto de pérdida. Los costos desconocidos siguen
bloqueando; este modo no aprueba los supuestos EUR/USD operativos.

Reserva RT → apertura: componentes de entrada SETTLED/MODELED; salida pendiente
RESERVED/ESTIMATED. Cierre: PnL bruto realizado y saldo de reservas una sola vez.
Equity = capital + PnL bruto realizado + PnL abierto − costos contabilizados y
reservados, sin volver a descontarlos del saldo anterior. No BROKER_CONFIRMED.

## Lectura, análisis, salidas y recuperación

ReadOnlyObserver reutiliza PaperReadSource, Research/read_only, identidad exacta,
calendario y velas nativas completas. Cada sondeo termina desconectado. Una falla
devuelve DATA_UNAVAILABLE; el siguiente sondeo revalida identidad. No convierte
fuentes IBKR en sintéticas ni escribe en el ciclo. El diagnóstico del Dashboard
lleva hash, hora y rótulo de corte histórico; no demuestra conexión continua.

El replay usa la estrategia original sin cambios. Cada registro puede incluir
velas 1H o 4H y una quote sintética explícita. Registra NO_SIGNAL y los rechazos;
la identidad de señal permanece estrategia/timeframe/cierre. El proceso mantiene
el singleton existente, por workspace/base, durante el replay. No es exclusión
por cuenta ni entre máquinas. No instala servicio ni autorrestart.

SL/TP y salidas defensivas se resuelven con quote válida al precio disponible,
incluidos gaps. Datos stale/desconectados conservan inventario y última valoración.
Se registra `UNVERIFIED_BETWEEN_QUOTES`: no se afirma conocer qué ocurrió entre
dos ticks ni se inventan fills de barras perdidas. Stop persistente bloquea nuevas
reservas/aperturas, libera pendientes y mantiene inventario hasta salida válida.
La pérdida diaria y bloqueos de recuperación sobreviven perfiles/reinicios; el día
America/Santo_Domingo no levanta EmergencyStop ni incertidumbre de reconciliación.

## Monitor y límites del despliegue

El monitor autenticado muestra perfil usado por contabilidad, propósito, equity,
PnL neto/bruto, apalancamiento, margen modelado, SL/TP, costos, señales, rechazos y
recuperación. PREPARED_REPLAY es preparación, no heartbeat ni actividad forward.
El host puede seleccionar un archivo de evidencia auténtica de sólo lectura;
el cliente HTTP no proporciona rutas. El hash del material se verifica antes de
mostrar el corte; su disponibilidad no concede apertura.

## Antes de un primer forward

1. Elegir límites diarios explícitos y aprobar una política Shadow de costos,
   margen, estrés y gaps con procedencia; no transformar UNKNOWN en cero.
2. Autorizar y preparar store/roles operativos V2 separados de011 y una frontera
   auténtica de admisión/gestión. No quitar el guard de TestStore.
3. Verificar en el entorno objetivo Stop, singleton/exclusión requerida, reinicio,
   reservas, inventario y cambio de día. Resolver autenticación y recuperación.
4. Autorizar despliegue del monitor sin actividad automática y comprobar su sesión.
5. Crear y vincular un preregistro operativo completo sólo con autorización nueva;
   activar el perfil seleccionado y emitir permiso Shadow independiente.
6. Revalidar AccountBinding/datos, integridad V1/protegidos y cero duplicados;
   obtener autorización explícita para un único arranque supervisado.

## Preparación de fase 4 Paper

Revisar compatibilidad de guards y RiskEngine sin eludirlos; transporte LONG/SHORT
y protecciones simétricas; idempotencia durable y reconciliación de órdenes inciertas;
exclusión por cuenta de todos los emisores; margen incremental efectivo, unidades
mínimas, comisiones y condiciones del producto. What-if y cualquier transmisión
requieren autorización explícita posterior. El permiso técnico Shadow nunca se
traslada a Paper. Live permanece fuera de alcance y bloqueado.
