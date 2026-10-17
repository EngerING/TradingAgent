# R20 V2 — persistencia aislada y política económica pendiente

12/oct/2026. Complementa r20-v2-core-contract.md sin modificar sus fórmulas ni
activar perfiles. V1 permanece STOPPED; no existe una cohorte operativa V2.

## Alcance y alternativa elegida

Se añade un adaptador Python pequeño sobre psql, ya instalado en el entorno,
para probar los contratos V2 contra PostgreSQL real. Evita añadir un driver o
duplicar el CLI .NET operativo mientras no se apruebe la integración.
No es el adaptador final de producción: usa conexiones cortas y verifica toda
la cadena de cada ledger; su costo crece con el historial. Migrar a un repositorio
con conexiones administradas y roles mínimos requiere otra fase.

Destino obligatorio:127.0.0.1:55432, usuario trading_test, system_identifier
7692346685552779632 y base r20_v2_test_<32 hex>. Tanto el instalador SQL como cada
conexión verifican destino. No acepta connection strings ni variables Paper.
No hay relación con journal011, ni modificación de tablas existentes.
Los scope_id r20-v2-test-ledger-* identifican ejemplos contables sintéticos,
no experimentos/cohortes, lectores, estrategias ni runners.

## Contratos persistidos

- Perfil económico completo, versión, hash, zona económica y timestamps UTC.
  La clave scope/version es inmutable; cada decisión conserva el perfil exacto.
- Snapshot de capital inicial contable, PnL bruto realizado, PnL abierto por ID,
  costos por ID/estado/procedencia/evidencia y DailyState completo.
- DailyState contiene referencia diaria, equity actual, presupuesto mínimo del
  día, pérdida consumida, riesgos abiertos adicionales, reservas pendientes,
  latch de pérdida y bloqueos operacionales. No se guarda un permiso de operar.
- Registro append-only con revisión, previous_hash, request_id, payload,
  event_hash y recorded_at UTC de PostgreSQL. Reloj económico separado del reloj
  de recepción del almacenamiento.

`append(snapshot, request_id, expected_revision, previous_hash)` valida el objeto
y su transición, luego ejecuta una transacción bajo advisory lock por ledger.
CAS verifica la cabecera después de adquirir exclusión. Perfil y evento se
confirman juntos. Dos escritores con la misma cabecera y solicitudes distintas:
uno gana y otro debe recargar. Una solicitud idéntica retorna su recibo original,
incluso si existen revisiones posteriores; no se interpreta como cabecera actual.
Misma clave con contenido distinto se rechaza. Un timeout requiere recargar o
reintentar exactamente la misma clave/payload, nunca generar otra clave a ciegas.

Hash = SHA256 UTF8(previous + LF + revision + LF + request_id + LF + payload).
JSON canónico conserva decimales como strings. Lectura verifica toda la cadena,
perfiles, hashes internos, coherencia contable y transiciones. UPDATE/DELETE/
TRUNCATE rechazados. Trigger de INSERT comprueba CAS/cadena, identidad de perfil,
equity, latch/budget intradía, conservación de bloqueos y gastos reconocidos.

Este prototipo usa el propietario del clúster de pruebas. Un administrador puede
desactivar triggers: una prueba lo hace deliberadamente y verifica detección al
recargar. Hash no equivale a firma ni protege contra un administrador capaz de
reescribir la cadena completa. Antes de producción: roles sin DDL, privilegios
solo sobre funciones autorizadas, validación completa de entradas SQL, límites
de volumen, retención/backup y ancla de integridad externa. El API tipado y sus
validaciones siguen siendo parte de la frontera; no publicar SQL arbitrario.

## Contabilidad sin descuento duplicado

```text
cash = capital_base + PnL_bruto_realizado − costos_SETTLED
equity = cash + ΣPnL_bruto_abierto − costos_ACCRUED − costos_RESERVED
equity_operativa = max(0, equity − reserva_de_entradas_pendientes)
equity_elegible = equity_operativa, o min(equity_operativa, techo_explícito)
```

Capital_base no es un techo al crecimiento. No alimentar cash ya neto de fees
como si fuese capital_base+PnL_bruto y restarlos otra vez. Cada obligación conserva
un cost_id al pasar RESERVED→ACCRUED→SETTLED; la transición reemplaza su estado,
no agrega un segundo gasto. Estimaciones pueden corregirse/liberarse; gastos
devengados o liquidados no desaparecen. Correcciones de gastos confirmados y
reembolsos requieren futuro contrato de reversión: hoy se rechazan.

Con precios midpoint, spread ida/vuelta=q(spread_entrada+spread_salida)/2.
Slippage modelado=q(slippage_entrada+slippage_salida). Con fills reales bid/ask,
el PnL realizado ya contiene la fricción de precio: no descontar nuevamente el
spread/slippage como fee. El mapper de fills aún no existe y deberá probar esta
distinción; los snapshots contables por sí solos no certifican un fill externo.

```text
U = max(0, equity_día0 − equity_actual)
R_abierto = Σmax(0, neto_actual_i − neto_estresado_i)
R_pendiente = Σpérdida_neta_estresada_de_entradas_no_abiertas
capacidad = max(0, presupuesto_día − U − R_abierto − R_pendiente)
```

Las reservas de costos de posiciones abiertas ya reducen equity; R_abierto sólo
es deterioro adicional. Entradas pendientes aún no están en equity, por eso su
pérdida total incluye costos una vez. Caso persistido de dos posiciones: equity92,
U8, riesgo adicional7, reserva pendiente4; consumo19, no27. Perfil intradía nuevo
con mayor porcentaje conserva presupuesto20 y capacidad1. El latch nunca se
borra ese día; nuevo día Santo_Domingo conserva EmergencyStop/órdenes inciertas
y exige revaloración antes de habilitar admisión. No hay ruta para limpiar esos
bloqueos en este adaptador.

## Configuración diaria sin valores implícitos — propuesta, no implementada

1. Formulario/API exige las cinco elecciones: riesgo por precio, capital asignado,
   apalancamiento, pérdida diaria y cupo. Sin valor elegido: PROFILE_REQUIRED.
   Capital base/equity lógico, techo opcional y políticas de costos/margen deben
   quedar explícitos. No heredar silenciosamente el perfil del día anterior.
2. Previsualización determinista muestra fórmulas, costos estimados/confirmados,
   razones de rechazo y hashes de políticas/escenarios; no presenta elegibilidad
   matemática como autorización Paper.
3. Confirmación crea versión inmutable con effective_from/until UTC y zona
   America/Santo_Domingo. Una revisión nueva afecta sólo nuevas aperturas.
   Persistir perfil y decisión económica con CAS e idempotencia comunes.
4. Frontera diaria verificada desde ledger/reconciliación. Sin fuente fresca o
   reconstrucción confiable: bloquear entradas, conservar gestión y obligaciones.
   Cambiar perfil o llegar a medianoche no limpia bloqueos operacionales.
5. API ASP.NET Core futuro: lectura de perfiles/historial/estado económico;
   previsualización y versionado autenticados, separados de la autorización de
   ejecución. SignalR publica revisión y origen persistidos. Dashboard muestra
   V1 histórico detenido y V2 sin activar; baseline sólo histórico.

No se implementaron API, SignalR, Dashboard, roles operativos, ejecución ni
activación de configuración. Costos, escenarios y margen operativo deben superar
los pendientes de calibración documentados antes de aprobar una política diaria.
