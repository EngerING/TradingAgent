# R20 V2 — configuración diaria, integración aislada

Alcance aprobado: API y frontend de pruebas. No conecta un motor Shadow, no crea
cohortes ni posee capacidades de órdenes. V1 y journal011 permanecen intactos.

## Fronteras y decisiones

El componente Vue `R20ConfigurationPage` pertenece al frontend existente, con
Pinia y contratos Zod. La ruta fuente `/r20/configuracion` queda preparada en modo
lectura; no se desplegó en el Dashboard operativo. Una entrada de laboratorio
`r20-config.html` permite verificarlo con autenticación propia en 5182. El build
se escribe en evidencias, nunca en `frontend/dist` servido por 5080.

`TradingAgent.ConfigurationLab` usa ASP.NET Core y cookies, pero es un host
separado sin referencias al API operativo, Infrastructure, reader, SDK IBKR ni
runner. Esto evita iniciar servicios operativos o migraciones al probar la UI.
No replica fórmulas: invoca `trading_agent.r20_configuration`, que reutiliza
EconomicProfile, DailyState, CostModel, Limits y size. Cada proceso recibe sólo
las variables necesarias para Python y el destino de pruebas, no credenciales
del bróker o del Dashboard. Hay límite de cuerpo 16 KB, cuatro solicitudes de
cálculo concurrentes y timeout de 45 segundos. Un timeout no garantiza ausencia
de commit: consultar el historial o repetir la misma clave idempotente.

Se conserva el ledger contable existente. Un ledger adicional de **configuración**
append-only registra revisiones, actor, UTC, día económico, valores, perfil,
hash de contexto, hash contable, petición idempotente y enlace anterior. Se eligió
este ledger frente a reescribir Snapshot con cada borrador: un borrador no puede
cambiar el perfil de una posición existente ni consumir una revisión contable.
La escritura comparte el advisory lock por scope con la persistencia contable,
y exige CAS de cabecera de configuración y cabecera contable. Los triggers
rechazan UPDATE/DELETE/TRUNCATE; la lectura verifica los hashes encadenados.

El guard del destino exige base `r20_v2_test_<32 hex>`, usuario trading_test,
127.0.0.1:55432 y system_identifier 7692346685552779632 en la misma conexión.
El contexto debe declarar SYNTHETIC_TEST_ONLY. No se admite un destino HTTP ni
un contexto económico suministrado por el navegador. Instalar el schema es una
operación de setup separada, nunca una consecuencia de abrir la página.

## Contrato HTTP

Prefijo `/api/r20-v2`. Todos los endpoints económicos requieren sesión.

| Método/ruta | Permiso | Resultado |
|---|---|---|
| POST `/session` | Credencial de laboratorio | Cookie reader o config-admin |
| GET `/session` | Sesión | Rol de configuración |
| POST `/logout` | Sesión | Destruye sesión |
| GET `/configuration` | Lectura | Estado, perfil vigente, historial y bloqueos |
| GET `/configuration/history` | Lectura | Mismo sobre verificable, con historial |
| POST `/configuration/preview` | Lectura | Cálculo sin persistencia |
| POST `/configuration/draft` | config-admin | Guarda borrador inmutable |
| POST `/configuration/validate` | config-admin | Valida los cinco campos y fija perfil/hash |
| POST `/configuration/activate` | config-admin | Registra configuración para futuro Shadow |

Preview recibe `{values:{...}}`. Draft añade `revision` y `requestId`; validate y
activate reciben sólo esos dos campos. El actor lo fija el servidor desde la
sesión, no el cuerpo HTTP. Valores decimales viajan como strings; posiciones es
un string entero de entrada, normalizado por EconomicProfile. No hay valores
operativos por defecto, coerción NaN/Infinity ni cálculo financiero en Vue.

401 sin sesión; 403 para reader que intenta modificar o para Origin/cabecera
CSRF inválidos; 409 CAS/idempotencia; 422 contrato/transición inválidos; 503 fallo
de almacenamiento/timeout. Preview devuelve 200 con `assessment=null` y causas
si falta información económica; una cantidad cero del core rechazado no debe
interpretarse como una orden. `executionEnabled`, `cohortStarted` y
`ordersSupported` son siempre false donde corresponden. No existe `/api/orders`.

Cookie HttpOnly, SameSite Strict, sin renovación deslizante, expiración 60 min.
Sólo loopback y Host 127.0.0.1:5182. Todo POST exige Origin exacto y cabecera
X-R20-Configuration:1. Tokens reader/admin distintos, exclusivos del laboratorio;
no conceden permisos Paper. Las claves de cookie son efímeras: reiniciar el host
invalida sesiones, no perfiles. HTTP local es exclusivo de este ensayo; antes de
otro despliegue se exige diseño de identidad individual, TLS y gestión de secretos.

## Estados y vigencia

`lifecycle` identifica la última transición persistida; `status` identifica la
disponibilidad efectiva. Son distintos: un borrador puede coexistir con un perfil
vigente, o un perfil validado puede seguir BLOCKED por costos desconocidos.

- DRAFT permite valores incompletos, sin autoridad sobre entradas.
- VALIDATED verifica estructura y restricciones de EconomicProfile. No certifica
  calibración de costos, margen del bróker ni elegibilidad Paper.
- ACTIVATED_FOR_SHADOW exige perfil vigente, contexto idéntico al validado,
  condiciones conocidas y ausencia de bloqueos diarios/operativos. Puede existir
  aunque una señal concreta sea económicamente rechazada: no altera ese filtro.
- EXPIRED se calcula al llegar a las 00:00 siguientes de America/Santo_Domingo.
  UTC se conserva en todos los timestamps. No se reutiliza automáticamente al día
  siguiente; tampoco se inventa una conciliación de frontera diaria.
- BLOCKED incluye perfil ausente, datos/políticas desconocidos, pérdida diaria,
  contexto cambiado y bloqueos operativos. No elimina el historial.

Cada decisión guarda configuración inmutable. Preview reutiliza el hash del
perfil validado aplicable; una modificación requiere otro borrador y validación.
Un perfil nuevo sólo configura futuras aperturas; ninguna ruta escribe inventario.

El presupuesto diario es el mínimo del ledger contable y de los presupuestos
activados ese día. Para conservar el latch cuando ambos ledgers aún están
separados, se revisan las observaciones contables y los límites vigentes en su
instante: un cruce persistido bloquea aunque la equity se recupere. No se suman
pérdidas históricas: se comprueba si hubo cruce. La pérdida consumida, riesgo
adicional abierto y riesgo pendiente siguen siendo los términos excluyentes de
DailyState. Cambiar perfil o reconstruir el servicio no borra ese cruce. La futura
integración del motor debe persistir observaciones bajo el perfil activo de forma
atómica, con admisión de entradas dentro de esa misma exclusión; esta API no es
un coordinador de ejecución ni prueba exclusión de órdenes por cuenta.

## Costos y escenario de prueba

Se mantiene la evidencia del documento `r20-v2-eurusd-cost-evidence.md`: spread
histórico mediano 0,2 pip, p95 0,3 pip, separado de la tarifa pública IBKR. El
mínimo publicado de USD2 por orden no es una comisión confirmada de R20.
Slippage y financiación operativos siguen UNKNOWN; ningún endpoint calibra esos
valores ni sustituye el piso de V1 por una mediana.

El escenario conocido de Playwright reutiliza el fixture matemático existente:
precio1, distancia de stop0,02, comisiones sintéticas1+1USD, otros costos0,
estrés LONG−0,02/−0,04 y márgenes sintéticos. Son supuestos de ensayo explícitos,
no costos propuestos para EUR/USD. Con elecciones explícitas20%/50%/5×/20%/3,
el core devuelve250EUR, riesgo5USD, margen25USD, costos2USD, target neto8USD y
pérdida al stop7USD. No se modificó la estrategia para generar ese resultado.
El caso UNKNOWN devuelve assessment=null e impide activar, conservando VALIDATED.
El laboratorio termina en ese estado bloqueado; no hay una política operativa lista.

## Límites y próxima integración

Persistencia y autenticación verificadas sólo en pruebas. El usuario trading_test
es propietario del cluster de ensayo; los hashes detectan alteraciones, no son
firmas frente a un administrador de DB. Antes de producción se necesita un rol
restringido, validación de transiciones en el límite DB, retención/paginación y
observación coherente sin releer el historial completo por solicitud. No hay
stream SignalR V2 nuevo; la pantalla usa lecturas explícitas.

Próxima fase, sólo con autorización: acordar calibración/procedencia y política
operativa de costos/margen; seleccionar identidad/scope y capital lógico reales;
integrar los handlers con auth del API existente; diseñar transacción de perfil,
observación, reservas y latch; probar pérdida de ACK, doble consumidor y medianoche;
planificar schema/adopción operativa sin tocar011; incorporar evento SignalR y
acceso administrativo de configuración en el Dashboard. Después, una aprobación
separada para preregistrar e iniciar V2 Shadow. Paper requiere además RiskEngine,
LONG/SHORT, exclusión durable por cuenta y recuperación, todavía pendientes.
