# R20 V2 — pruebas propuestas y gates

12/oct/2026, revisión 3. **NÚCLEO Y REGRESIONES EJECUTADOS; INTEGRACIÓN PENDIENTE.**
Resultado: [informe del núcleo](../../artifacts/aggressive-growth-r20-20261010/r20-v2-core-20261012/report.md).
Esta matriz conserva también escenarios futuros; no todos están implementados. Complementa el
[diseño económico](r20-v2-economic-design.md) y el
[contrato de fórmulas](r20-v2-formulas.md). No contiene fixtures para Paper ni
autoriza arranque V2. Los ejemplos numéricos de tests serán datos sintéticos
identificados, sin convertirse en configuración operativa.

## Matriz de aceptación

| ID / capacidad | Caso y evidencia exigida |
|---|---|
| P01 C1 | Perfiles con cero/negativos/fuera de techo, campos faltantes, desconocidos, floats no finitos, decimales ambiguos, integer booleano y referencias inválidas: rechazo antes de persistir. No fallback a R1/R5/R10 ni V1. |
| P02 C1 | Canonicalización C#/Python produce exactamente mismo material/hash. Cambiar cualquier campo económico, actor, intervalo o política cambia hash. Hash del cliente no se acepta como evidencia. |
| P03 C1 | Guardar versión no activa. Activar con revisión antigua da 409. Dos activaciones concurrentes: una gana; ninguna reescribe la anterior. Idempotency key igual/cuerpo igual conserva resultado; cuerpo diferente se rechaza. |
| P04 C1/C4 | Sin perfil, expirado, revocado o política desconocida: cero aperturas y motivo concreto. Inventario existente sigue valorándose y cerrándose con su perfil congelado cuando hay quote válida. |
| P05 C1/C3 | Cambio de perfil con posiciones abiertas conserva perfil/hash, tamaño, SL/TP y política de costos de cada posición; devengos y estimaciones continúan según esa política. Sólo una nueva señal posterior usa nueva versión. Capital de referencia no limita crecimiento; techo opcional explícito sólo limita nuevas entradas, sin abonos a cash. |
| P06 C1/C6 | Día America/Santo_Domingo 00:00–00:00 con UTC persistido y zona explícita, independiente del timezone del equipo. Vigencia half-open: en effective_until no admite; publicación posterior no aparece en replay anterior. Tests genéricos de horas ambiguas/inexistentes y días 23/25h verifican el resolvedor temporal sin atribuir esos cambios a Santo_Domingo. |
| S01 C2 | Variar riesgo manteniendo asignación y viceversa. Oráculo muestra techos independientes y restricción vinculante; no aumentar leverage al pedir mayor riesgo. |
| S02 C2 | LONG/SHORT simétricos con stop válido. `q*D ≤ B_price`; stop/target conservan reglas de señal. SHORT con target no positivo o stop del lado incorrecto rechaza. |
| S03 C2 | Quantización al incremento siempre hacia abajo; mínimo mayor al techo rechaza. Tras redondear se verifican todos los límites, incluido target neto. |
| S04 C2 | Comisiones con mínimo y tramos: tamaño pequeño no viable aunque uno mayor sí lo sea. Comparar solver con enumeración de rejilla acotada; no asumir monotonicidad injustificada. Timeout de solver rechaza. |
| S05 C2/C3 | Exposición bruta incluye LONG y SHORT, abiertas y pendientes. Límites de cartera/margen/liquidez prevalecen aunque riesgo por precio cumpla. Dato desconocido/stale impide entrada. |
| S06 C2 | Costos reservados antes de calcular leverage posterior. Holgura positiva y estrés hasta stop/gap deben pasar simultáneamente; caso auditado V1 no puede aceptarse V2 si viola política aprobada. No afirmar qué tamaño V2 tendrá antes de fijar políticas. |
| S06b C2 | H_0≥H_required equivale a L_post≤L×(1−h_min) y X_j≤L×(E_j−b_j), exigiendo E_j>b_j. Cubrir ΔX negativo, costos no lineales, igualdad y déficit mínimo. Falta de calibración bloquea, no asigna buffer cero. |
| S07 C2 | Neto al target >0, =0 y <0; los dos últimos rechazan bajo la propuesta. Un target positivo no marca `statistically_validated` ni `paper_execution_eligible`. |
| S08 C2/C4 | Cupo máximo incluye reservas. Dos señales simultáneas, misma capacidad: CAS permite sólo lo que cabe; orden determinista y ganador único. Igual señal nunca abre dos veces por retry o cambio de perfil. |
| C01 C2/C3 | Midpoint + costos: spread entrada/salida por medias mitades, no bid/ask más spread adicional. Prueba contable con precios equivalentes y pérdida conocida. |
| C02 C2/C3 | Comisión apertura/cierre, slippage por lado y financiación tienen unidades y procedencia distintas; UNKNOWN nunca equivale a cero. Una sola quote no cambia piso/política. |
| C03 C3 | Mark repetido con mismo timestamp/inputs mantiene cash/equity/reservas. Tick posterior devenga sólo diferencia de financiación; restart produce el mismo estado. |
| C04 C3 | Cierre con costos finales iguales a reservas mantiene equity; diferentes generan delta explicable. Reserva desaparece, cash realiza neto una vez. ACK perdido y replay del evento no duplican fees ni PnL. |
| C05 C3 | Pendiente→abierta mueve la misma reserva, no la duplica: E_available se conserva sin otro cambio de mercado. Margen reservado no resta un gasto de equity. R_pending incluye costos porque aún no están en E_net; R_open sólo deterioro desde valor neto actual. |
| D01 C3 | Pérdida diaria incluye cambio de equity neta por realizadas, abiertas y costos; reconciliación con ledger. R_open usa riesgo adicional, no vuelve a contar pérdidas ni reservas ya reflejadas. |
| D02 C3 | Ganancias compensan pérdida neta pero no amplían presupuesto original. Una vez disparado latch diario, recuperación de equity no lo limpia. Probar frontera exacta U_day = D_budget. |
| D03 C1/C3 | Aumento de porcentaje intradía no reinicia ni amplía presupuesto; mínimo histórico D_budget persistido. Reducción evalúa latch contra U_day y bloquea si procede, sin modificar stops previos. Un cap explícito limita sizing, no reescribe cash ni amplía presupuesto diario. |
| D04 C3 | Medianoche con posiciones: carry de inventario/riesgo/financiación, nuevo presupuesto sin duplicar cargos. Caída/restart a medianoche produce un solo evento de día. |
| D05 C3/C4 | Sin mark válido en frontera: DAY_BOUNDARY_UNVALUED, ninguna entrada. Gap desde último mark previo se atribuye conservadoramente, no se perdona tomando primer mark posterior como base. Sin referencia íntegra sigue bloqueado. |
| G01 C4 | Quote obsoleta/inválida, sesión cerrada o desconexión: no fill, no inventario fabricado; observación interrumpida preserva posiciones. Stop persistente con quote vencida espera; quote fresca permite gestión según contrato. |
| G02 C4 | Reutilizar paridad de barras completas, gaps, timestamps, señal caducada, stop primero si una barra toca ambas barreras y ausencia de look-ahead. Primera barra parcial desde entrada nunca finge trayectoria ejecutable. |
| G03 C4 | Exceso de leverage administrativo por fluctuación o reducción de L no genera cierre virtual. Bloquea nueva entrada que no cabe en exposición agregada, conserva SL/TP/tamaño. Déficit de margen/mantenimiento/exposición dura sigue activando su gestión defensiva; no se disfraza como exceso administrativo inocuo. No hay fill sin datos válidos. |
| J01 C3/C4 | PostgreSQL real aislado: CAS concurrente, revisions/previous_hash, FK perfil/día, identidad de cohorte, rechazo UPDATE/DELETE, alteración de hash y cambio de perfil de una posición. |
| J02 C3/C4 | Corte antes/después de commit y ACK perdido. Recargar confirma una sola evaluación/reserva/posición; retry no inventa nueva identidad. Cambiar perfil concurrentemente no permite commit con revisión invalidada. |
| J03 C4 | Segundo consumidor no obtiene singleton; tras caída puede recuperarse sin consumir doble señal. Un lock local no se presenta como exclusión de cuenta Paper. |
| A01 C5 | Anónimo 401; lector no crea/lista perfiles administrativos ni activa/revoca, aunque la ruta sea /api/ui. Cookie de lectura y falso scope no elevan privilegios. |
| A02 C5 | Sesión de configuración sólo mediante credencial admin válida; scope corto no sirve en órdenes/confirmaciones/otros endpoints administrativos. Caducidad, revocación, logout, CSRF, Origin y replay de sesión cubiertos. |
| A03 C5 | Guardar/activar perfil no escribe permisos Paper, no limpia EmergencyStop, no cambia Live, no llama ningún transporte. Spy de ejecución debe fallar si se invoca. |
| A04 C2/C5 | Preview y runner entregan el mismo assessment para mismo material. Preview sin señal muestra métricas dependientes null y motivo; no genera señal sintética. Snapshot/head expirado fuerza recálculo. |
| U01 C5 | Vitest de decimales/porcentajes, loading/error/stale, posición con perfil anterior y conflictos SignalR. Desconocidos preservados; no falsear probabilidad Kronos ni elegibilidad Paper. |
| U02 C5 | Playwright desktop y móvil: formulario admin, lector sin mutación, error 403 real, preview reproducible, historial inmutable, aviso futuras entradas, reconexión y ausencia de overflow. Capturas y respuestas sanitizadas. |
| V01 C6 | Hashes de 74 protegidos y manifiesto V1 idénticos antes/después; mismo contrato 011 y baseline. Nueva suite no escribe DB operativa ni arranca/detiene runner V1. |
| V02 C2/C6 | Mismas barras y as_of producen exactamente la misma señal V1/V2: dirección, indicadores y distancias. Variar sólo perfil cambia admisibilidad/cantidad, nunca señal. |
| V03 C3/C5 | V1/V2 separados en ID, almacenamiento, snapshots y eventos. Payload V2 enviado al Store V1 rechaza; payload V1 no adquiere semántica V2. V1 sigue renderizando sin requerir perfiles V2. |
| V04 C6 | R20-Only no se declara completo por estos tests: regresiones de vías heredadas ya bloqueadas siguen pasando; restantes se reportan pendientes. Ningún endpoint nuevo acepta perfiles históricos ni emite órdenes. |
| V05 C6 | V2 carece de baseline operativa, V1 la conserva completa. Neto TP≤0 rechaza entrada normal sin afectar historia; ensayo técnico requiere identidad/almacenamiento/estadísticas y autorización separadas. No hay flag de perfil normal para omitir costos ni autorización implícita de ensayo. |

## Secuencia TDD futura

1. Perfil/canonicalización/selección temporal: P01–P06 en memoria, RED específico
   antes de implementación mínima. Números de ejemplo sólo en tests aislados.
2. Calculadora/ledger/día: S/C/D, oráculos independientes por ecuaciones y
   propiedades; no tests que sólo repitan línea por línea la implementación.
3. Persistencia/recuperación: J/G en PostgreSQL de pruebas, identidad de clúster
   comprobada, DB temporal propia y sin cliente IBKR. No usar un alias que pueda
   resolver a Paper55433. Runtime de tests sin credenciales de broker.
4. API/frontend: A/U y V03 con sesión real de test; pruebas negativas de seguridad
   obligatorias. Dobles de transporte rechazan toda transmisión o cancelación.
5. Paridad, replay y suites globales después de integrar. Builds aislados para
   no bloquear/sustituir DLLs usadas por V1; ningún test requiere detenerla.

Esta entrega ejecuta sólo núcleo aislado y regresiones vecinas; no aprovisiona DB ni ejecuta la integración prevista. Implementar pruebas
unitarias no autoriza fixtures operativos, migraciones Paper ni arranque V2.

## Replay con datos auténticos

- Copias de sólo lectura de barras/quotes y manifiestos SHA256 de evidencia
  auténtica. Nunca adjuntar resultados al journal FORWARD V1 ni alterar sus filas.
- Preregistrar versión candidata, perfiles y políticas antes del tramo de
  validación; separar ajuste y evaluación. No escoger costos conociendo resultado.
- Reloj `as_of`, cierre de barra y timestamp de disponibilidad independientes.
  Warmup no habilita señal caducada. Quote de callback local no se denomina
  timestamp de exchange. Si sólo hay OHLC, incertidumbre intrabar explícita;
  política conservadora fija (stop primero), sin reconstruir ticks inexistentes.
- Replay histórico de V1 usa su motor congelado; V2 usa la misma señal y perfiles
  predefinidos para ese replay. Ambos en partición HISTORICAL con IDs nuevos de
  test/replay, nunca la cohorte FORWARD existente. Los perfiles contrafactuales se
  identifican como tales, no como configuraciones disponibles en aquel mercado.
- Reportar cantidad, exposición, riesgo por precio, pérdida neta/estrés, margen,
  holgura, costos por componente, motivos de rechazo, PnL y tiempo sin datos. Cubrir
  sensibilidad a costos y gaps, operaciones nulas y rechazo de target negativo.
- Un replay no equivale a fills realmente observados ni prueba rentabilidad futura,
  margen IBKR, protección en servidor, aceptación de SHORT o exclusión por cuenta.
  Si todas las entradas resultan inviables, ese es el resultado que debe entregarse.

## Evidencia y criterios de finalización futura

Por entrega: RED/GREEN, comando/entorno, resultados sin omisiones ocultas,
hashes antes/después, IDs/revisiones test, vectores canónicos y ejemplos de
rechazo. Para replay: datos/versión/corte y matriz causal. Para navegador:
capturas desktop/móvil, API auth y eventos SignalR sanitizados.

Antes de operación V2: decisiones económicas aprobadas; políticas de costos y
holgura con evidencia; pruebas pertinentes y globales; revisión de migración y
destino; autorización independiente de despliegue/preregistro/arranque. Ninguno
de estos gates habilita Paper. Su adapter, RiskEngine, dirección, exclusión,
conciliación y consentimiento requieren otra fase.
