# R20 V2 — frontera de admisión y futura conexión Shadow

Actualización13/oct/2026: el ciclo sintético de reserva→posición→cierre se añadió
en `r20_shadow.py`. El documento [ciclo Shadow](r20-v2-shadow-cycle.md) sustituye
las limitaciones de ausencia de PositionSnapshot/cierre descritas abajo.
Las restricciones de aislamiento, costos UNKNOWN y no activación operativa siguen
vigentes. El resto conserva el alcance de la etapa anterior como referencia.

Alcance implementado: **reservas contables sintéticas en pruebas**, sin cohortes,
observadores, fills ni órdenes. No es un runner Shadow listo para operación.

## Arquitectura mínima

1. Reader IBKR existente de sólo lectura verifica AccountBinding, contrato,
   calendario, timestamps y calidad, sin autoridad de órdenes.
2. Función existente `aggressive_growth.signal` produce una decisión técnica
   AGGRESSIVE_TREND_BREAKOUT_V1. EMA/ATR/breakout y sus parámetros no se cambian.
3. SignalProposal adapta side, stop_distance y cierre temporal; side=null produce
   NO_SIGNAL. Se preservan hash técnico y hash de evidencia. El parser no acredita
   autenticidad: esa responsabilidad pertenece al reader y al almacén de fuentes.
4. Un coordinador compara perfil activado, política/evidencia, datos y estado
   reconciliado; el solver V2 calcula la mayor cantidad admisible.
5. Reserva atómica precede a una futura apertura **virtual**. La gestión de
   inventario usa condiciones de entrada conservadas, independientemente del
   perfil nuevo o de su caducidad. Paper constituye otra frontera autorizada.

SignalProposal y AdmissionCoordinator existen en `r20_admission.py` como prueba
de ese contrato. El coordinador **rechaza toda fuente distinta de
SYNTHETIC_TEST_ONLY**: no se habilitó una vía de observación auténtica ni un bucle.
Los hashes de fixture son explícitos; no se presentan como evidencia de mercado.
La adaptación al motor existente se ejecutó en LONG y SHORT con barras sintéticas,
comparando la decisión técnica antes/después sin cambiar sus resultados.

## Transacción de admisión

La clave de exclusión es el scope lógico del ledger de pruebas. El SQL toma el
mismo advisory lock que las escrituras contables y de configuración. Comprueba:

- CAS de ambas cabeceras y perfil activado exacto.
- Vigencia UTC y día America/Santo_Domingo; inventario conciliado.
- Cupo que incluye posiciones abiertas y reservas pendientes.
- Costos nuevos excluyentes, riesgo adicional y presupuesto disponible.
- Certificado coherente con cantidad/stop, costo reservado, pérdida estresada y
  perfil. No permite modificar PnL realizado o inventario abierto al reservar.
- Idempotencia por requestId y exclusión por signal_id.

Un commit añade Snapshot y recibo en **la misma transacción**. Si una cabecera
cambia se rechaza; se debe recargar y reevaluar, no repetir un tamaño antiguo a
ciegas. Dos procesos pueden compartir el head, pero sólo uno confirma. Señales
posteriores usan equity, exposición nominal, margen, cupos y riesgo ya reservados.
Los escenarios reprician el nominal de reservas existentes y sus pérdidas/margen;
SHORT aumenta exposición con un movimiento adverso al alza.

Respuesta perdida tras commit: recuperar el recibo estable antes de validar una
señal nueva o caducada. Conexión terminada antes del commit: rollback de Snapshot
y recibo. Se probaron ambos caminos. No hay exactly-once de órdenes IBKR aquí.

En el ensayo conocido, primera reserva: costo2USD, equity98, riesgo pendiente10;
segunda: costo2USD, equity96, riesgo pendiente agregado16. Consumo diario4+16=20,
no24. Una tercera solicitud es denegada. Son números de fixture, no sizing EUR/USD
operativo ni posiciones creadas por el agente.

## Perfil, inventario y día

Modificar perfil no cambia las reservas anteriores ni el inventario abierto.
Cada recibo conserva perfil y decisión de origen. Una futura PositionSnapshot
debe conservar position_id, side, quantity, entrada, SL/TP, engine_hash,
entry_profile_hash, cost_policy_hash, timestamps y costos por id. Ni un cambio
administrativo de apalancamiento ni caducidad del perfil son por sí solos órdenes
de cierre. Margen real, protección, emergencia y recuperación siguen siendo
acciones defensivas obligatorias en el futuro gestor.

El ledger contable actual representa PnL/riesgo, no todo el ciclo de vida de una
posición. El laboratorio no implementa cierre, conversión de reserva en fill,
liberación de reserva ni un motor de salidas. No se afirma que gestione una
posición Shadow operativa. Se demuestra que solicitudes rechazadas, cambios de
perfil y caducidad preservan el inventario sintético, y que no fabrican cierres.
Con inventario abierto el coordinador rechaza OPEN_INVENTORY_CONTEXT_REQUIRED,
sin interpretar como cero su exposición ausente.
Antes de nuevas aperturas con inventario real debe existir un snapshot completo
de exposición/margen/costos, reconciliado con el ledger.

Al cambiar el día, next_day conserva términos abiertos/pendientes y bloqueos
operativos; marca inventario sin verificar. El API ya no puede convertir ese
estado en verificado simplemente al previsualizar o activar otro perfil. Requiere
conciliación separada. Caducar un perfil deniega aperturas; lectura y recuperación
de obligaciones siguen disponibles. El latch diario no puede levantarse por
cambio de perfil, reinicio o rebote de equity. EmergencyStop/recovery no se
levantan por medianoche.

## Permisos de laboratorio

| Principal DB NOLOGIN | Leer | Cambiar perfiles | Reservar | Insertar tablas directamente | Órdenes |
|---|---|---|---|---|---|
| r20_lab_reader | Sí | No | No | No | No |
| r20_lab_profiles | Sí | Sí, función de configuración | No | No | No |
| r20_lab_shadow | Sí | No | Sí, función de admisión | No | No |
| r20_lab_paper_disabled | Sí | No | No | No | No |

Las funciones de escritura autorizadas usan SECURITY DEFINER con search_path
pg_catalog y nombres de schema explícitos. PUBLIC no puede ejecutarlas. La capa
Python/backend sigue siendo responsable de las fórmulas; SQL protege la carrera,
las cabeceras y las invariantes de reserva. No es un solver duplicado en SQL.
No se concede una autorización de trading al crear estos roles en test55432.

El host escoge RoleStore exclusivamente del principal autenticado; el cliente
no proporciona role, actor, cantidad admitida ni destino DB. HTTP de lectura no
puede modificar perfiles; no existe endpoint de admisión/órdenes. El login del
host único de pruebas tiene20 intentos/15min, sin cola; una política de despliegue
con varios hosts necesitaría contador compartido. Tokens y cookies sólo sirven
al laboratorio; no permisos Paper ni sesión de broker.

Limitación explícita: test55432 usa trust loopback y el bootstrap trading_test es
propietario. SET ROLE demuestra ACL reales en DB, pero no elimina el poder del
administrador local. Producción requiere credenciales individuales restringidas,
separación del owner de migración, validación de alcance/RLS y protección del
proceso ejecutor. No exponer el TestStore/execute genérico como API de producción.

## Despliegue futuro sin activación automática

1. Aprobar supuestos/evidencia acotada de costos y margen, capital lógico y
   calendario; mantener UNKNOWN bloqueado hasta resolverlo. No copiar fixtures.
2. Revisar un store/identidad de entorno operativos separados. No quitar el guard
   de TestStore para apuntarlo a Paper. Diseñar un schema V2 aditivo separado de011,
   aplicar sólo con autorización nueva, identidad y plan de recuperación.
3. Desplegar API/UI de configuración sin perfil activo ni runner. Exigir selección
   explícita de los cinco valores y actor; verificar DB, auth y lecturas.
4. Completar reserva→posición→cierre, conciliación de inventario/día, protección,
   costos confirmados/estimados e idempotencia con los mismos presupuestos.
5. Integrar reader y función técnica detrás de arranque manual; preregistro y
   cohorte FORWARD sólo tras aprobación separada. No activar el último perfil
   al arrancar API/servicio ni reutilizar automáticamente el del día anterior.
6. Paper: además RiskEngine/ExecutionGuard compatibles y sin debilitamiento,
   LONG/SHORT/protecciones, autorización específica y exclusión durable por cuenta
   incluyendo emisores heredados. El lock por scope aquí probado no demuestra
   exclusión por cuenta ni exclusividad global R20-Only.

Esta fase no aplica ese despliegue ni inicia un servicio. V1 permanece retirado.
