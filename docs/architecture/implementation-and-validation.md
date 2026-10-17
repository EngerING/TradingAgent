# TradingAgent: implementación posterior y verificación

Estado: plan de fase 1, 2026-10-03. Diseño rector: [capital-preservation.md](capital-preservation.md). Todos los componentes y tests de comportamiento descritos aquí están pendientes de implementación salvo las comprobaciones documentales consignadas al final.

Seguimiento: [informe de la primera entrega funcional de fase 2](phase2-implementation.md). Este plan queda como trazabilidad histórica; los valores, resultados de pruebas y capacidades actuales se describen allí.

## 1. Dependencias necesarias

| Dependencia | Uso y condición de aceptación |
| --- | --- |
| .NET/C# y ASP.NET Core | Núcleo determinista, API administrativa y gateway; fijar una versión soportada y compatible con el SDK seleccionado al implementar |
| Python aislado | Backtesting, métricas, walk-forward, Monte Carlo e investigación IA; fijar dependencias/hashes, semillas y límites de recursos |
| PostgreSQL | Política versionada, snapshots, ledger, reservas exclusivas, outbox e idempotencia; probar transacciones, aislamiento y recuperación real |
| Identidad administrativa/OIDC, MFA y gestor de secretos | Autorización del propietario y separación de identidades de investigación, validación, riesgo, ejecución y administración |
| IBKR TWS API y Gateway/TWS | Adaptador propuesto; verificar compatibilidad de versiones, permisos, metadatos de contrato, reconexión y callbacks en fases posteriores |
| Cuentas Paper/Live segregadas | Credenciales, IDs permitidos, almacenamiento y despliegues independientes; Live permanecerá sin habilitar hasta decisión humana posterior |
| Datos históricos y de mercado | Licencia/permisos, timestamps, zonas, FX, ajustes corporativos y universo sin sesgo de supervivencia; calidad y frescura controladas |
| Modelo de costos y riesgo por producto | Comisiones/tasas, spread/slippage, margin, multiplicadores, mínimos, financiación, borrow y escenarios de gap; rechazar productos sin modelo válido |
| Almacén de artefactos y evidencia | Versiones inmutables, resultados reproducibles y retención protegida para auditoría y autorizaciones |
| Observabilidad y reloj | Logs estructurados, métricas, trazas, alertas, heartbeat, sincronización de reloj y métricas de retraso de eventos |
| Proveedor IA mediante interfaz | Respuestas estructuradas, validación, timeouts, presupuestos y reintentos acotados; falla cerrada para entradas sin afectar el controlador defensivo |
| CI y simulador de bróker | Pruebas sin credenciales Live y fallos reproducibles; comparación entre resultados de investigación y motor operativo |

No es necesaria una cola externa para el primer alcance: un outbox en PostgreSQL con un worker basta si se prueban sus garantías. El motor de riesgo y el Safety Controller no importan ni llaman al SDK de OpenAI. Su salud depende de sus propios datos y controles; la salud de IA es una señal para bloquear entradas, no una fuente de permisos.

## 2. Fases y condiciones de salida

### Fase 1 — Arquitectura actual

Entregables: invariantes, módulos, permisos, cálculos, ciclo de aprobación, ciclo de ejecución, dependencias, riesgos pendientes y matriz de pruebas. Resultado: documentación revisable. No se crean configuraciones operativas, credenciales, conexiones de cuenta ni órdenes, incluidas órdenes Paper, previews o `Transmit=false`.

### Fase 2 — Dominio y riesgo sin bróker

Implementar funciones deterministas con aritmética decimal, políticas inmutables, períodos, índice ajustado por flujos, HWM durable, sizing, reservas, estados de suspensión y permisos. Añadir repositorios, migraciones y transacciones PostgreSQL; administración protegida y registro de auditoría. Un adaptador falso será la única implementación de bróker disponible.

Condición de salida: pruebas de invariantes, límites, concurrencia y permisos aprobadas; reinicios no reinician pérdidas; dos propuestas paralelas no obtienen dos slots; solicitudes de IA no pueden modificar políticas ni aprobaciones. Fuzzing de contratos e inyección de fallos sin efectos externos.

### Fase 3 — Investigación reproducible

Implementar datasets versionados, protocolo administrativo de evaluación, registro de candidatos, backtesting por eventos, holdout, walk-forward, Monte Carlo y reportes. Compartir contratos y casos de referencia con el motor C#; contrastar sizing, costos y suspensiones entre Python y C# para evitar dos modelos de riesgo distintos.

Condición de salida: expediente completo, ejecución reproducible y test de ausencia de fuga temporal; umbrales estadísticos y escenarios definidos antes de evaluar; cambios de parámetros invalidan resultados anteriores. Ningún buen backtest produce aprobación Live por sí mismo.

### Fase 4 — Integración de lectura y simulador de fallos

Una vez iniciado expresamente este alcance posterior, conectar al entorno autorizado para verificar identidad, contratos, posiciones, equity y calidad de datos. Mantener deshabilitado el envío. Añadir simulador para callbacks duplicados/desordenados, rechazos, desconexión, gaps, fills tardíos y parciales. Verificar acceso real a valores necesarios; datos faltantes producen bloqueo.

Condición de salida: conciliación consistente, matriz de capacidades por instrumento y tipo de orden, recuperación demostrada y modelos conservadores de costos/margen contrastados. No confundir una consulta de lectura con prueba de ejecución o de precio de salida.

### Fase 5 — Paper Trading autorizado

Solo al iniciar esta fase posterior: integración de envío Paper, preflight compatible, estados de órdenes, idempotencia, protecciones y parada. Reproducir el capital objetivo y las restricciones de la futura cuenta; no validar factibilidad usando un saldo simulado artificialmente alto. Confirmar identidad de cuenta mediante allowlist y credenciales dedicadas.

Paper aporta evidencia de integración, no equivalencia con Live. IBKR documenta que su simulador usa la parte superior del libro y tiene diferencias en órdenes complejas y ejecuciones parciales: [limitaciones oficiales de Paper Trading](https://www.interactivebrokers.com/campus/glossary-terms/paper-trading-account/). Complementarlo con simulación de escenarios que Paper no representa.

Condición de salida: duración, número de operaciones y regímenes mínimos establecidos previamente; reconciliación, costos y fallos dentro del protocolo; expediente auditable y revisado por el propietario. Una estrategia insuficientemente observada sigue pendiente aunque no haya perdido.

### Fase 6 — Evaluación de habilitación Live, fuera del alcance actual

Solo tras todas las fases anteriores: revisión operativa y de evidencia, aprobación explícita para hash/parametrización/política/cuenta, habilitación humana y despliegue con límites autorizados. Reanudar tras suspensión requiere resolver causas y nueva acción humana. No hay despliegue automático a Live desde investigación ni desde CI.

Criterios de no habilitación: capital incompatible con mínimos/costos, evidencia insuficiente, requisito de riesgo pendiente, falta de permisos/datos, recuperación no demostrada, estrategia modificada sin aprobación, autorización revocada o estado no conciliado.

## 3. Matriz de trazabilidad y pruebas futuras

Los casos siguientes son especificaciones de aceptación, no pruebas ya ejecutadas.

| ID | Requisito | Prueba y resultado esperado | Fase |
| --- | --- | --- | --- |
| CAP-01 | Composición sin elevar porcentaje | E=10.000/11.000/9.800 produce techos 50/55/49 antes de otros controles; `r_trade` permanece 0,005 | 2 |
| CAP-02 | Reducción de tamaño con pérdidas | Con costos y precios constantes, menor equity nunca produce mayor cantidad; redondeos pueden reducirla más | 2 |
| CAP-03 | No operar bajo mínimo | Presupuesto 50, costo fijo 2, riesgo unitario 2,50, lote mínimo 20: denegar; mínimo 1: máximo 19 si pasan controles restantes | 2 |
| CAP-04 | Umbrales exactos | Desde 10.000, sin flujos/costos adicionales: día 9.850, semana 9.700 y HWM 10.000/equity 9.500 suspenden en sus períodos respectivos; ejecutar casos aislados y combinados | 2 |
| CAP-05 | Presupuesto restante | Equity 9.860, base diaria 10.000: room diario 10; denegar operación de riesgo 11 aunque el techo por operación sea 49,30 | 2 |
| CAP-06 | Flujos y períodos | Aportes/retiros no alteran `V` ni borran HWM; modifican U y presupuesto monetario; probar flujos concurrentes, DST, cambio de semana y reinicio | 2 |
| CAP-07 | Pérdida no realizada y costos | P&L abierto y cargos pendientes reducen capacidad; llegada de comisión real reemplaza reserva sin doble conteo | 2 |
| CAP-08 | Persistencia de suspensión | Reinicio, medianoche, depósito o nueva estrategia no eliminan causas; reanudación humana solo tras condiciones válidas | 2 |
| CAP-09 | Una operación total | Dos entradas concurrentes, IDs distintos o dos estrategias en misma cuenta: un solo slot; una reserva/orden parcial/posición ya ocupa el slot | 2 |
| CAP-10 | Sin martingala o promedio | Secuencia de pérdidas, splits de señal y cambio de ID no elevan riesgo ni abren ampliaciones; sizing no tiene multiplicador de recuperación | 2 |
| CAP-11 | Apalancamiento independiente | Stop artificialmente estrecho no permite superar tope de nocional/leverage/margen; límite ausente bloquea instrumento | 2, 4 |
| CAP-12 | Modelos por instrumento | Moneda y multiplicador distintos, cantidades fraccionales y precio por tick: redondeo válido; derivado no lineal sin modelo específico: denegar | 2, 4 |
| ADM-01 | IA sin permisos | Intentar escribir política, aprobar, reanudar o llamar al bróker con identidad Research: denegado a nivel API, BD y red; prompt injection no concede privilegios | 2 |
| ADM-02 | Cambio de política | Nueva versión invalida permisos pendientes y aprobaciones incompatibles; reducción de límites con exposición abierta activa protección; relajación no reanuda sola | 2 |
| ADM-03 | Aprobación exacta | Modificar código, parámetros, prompt decisorio, límites, cuenta o entorno después de aprobar: no admitir hash diferente; probar caducidad y revocación | 2, 3 |
| ADM-04 | Separación Paper/Live | Permiso o mensaje Paper usado en Live y viceversa: rechazo; cuenta inesperada en conexión: bloqueo | 2, 5 |
| AI-01 | IA indisponible o inválida | Timeout, caída, schema inválido, infinito/NaN, campos extra o cantidades negativas: sin nuevas entradas; controlador defensivo permanece independiente | 2, 5 |
| AI-02 | Código candidato hostil | Intento de red al gateway, lectura de secretos, escritura operativa o consumo ilimitado: sandbox deniega/termina; registrar incidente | 3 |
| EVAL-01 | Evidencias completas | Falta cualquiera de las métricas, fuera de muestra, walk-forward, Monte Carlo, regímenes o factibilidad: `INCOMPLETE` | 3 |
| EVAL-02 | Rentabilidad y costos | Estrategia bruta positiva pero neta negativa o expectativa neta negativa no pasa; escenarios de costos peores quedan visibles | 3 |
| EVAL-03 | Fuga y selección | Cambiar datos futuros no cambia decisiones históricas; ajustar con holdout invalida ese holdout; registrar búsqueda de múltiples candidatos | 3 |
| EVAL-04 | Ruina y drawdown | Simular caminos correlacionados, rachas y gaps; reproducir con semilla; declarar intervalo/horizonte; nunca transformar cero eventos en certeza | 3 |
| EVAL-05 | Paridad de motores | Mismas series de eventos y política en investigación y dominio: mismo tamaño, costos, reservas y suspensiones dentro de tolerancias declaradas | 3 |
| IB-01 | Mínimos y margen | Instrumento/ruta sin metadatos fiables, comisiones inciertas, falta de margen o liquidez: denegar; no ampliar leverage | 4, 5 |
| IB-02 | Datos obsoletos | Snapshot viejo, FX ausente, reloj desfasado o posición no conciliada: denegar y alertar; no usar silenciosamente datos congelados | 4, 5 |
| EX-01 | Idempotencia | Reentrega de intención/outbox y callbacks duplicados no crea segunda entrada ni doble fill; IDs de cuentas distintas no se confunden | 2, 5 |
| EX-02 | Caída en ventana de envío | Caer antes/después de enviar y antes/después del ACK: reserva retenida, `UNKNOWN` donde corresponda, conciliación antes de decidir; sin replay ciego | 2, 5 |
| EX-03 | Fill parcial y rechazo | Fill de 4/10 y rechazo/cancelación del resto: posición real 4 protegida, reserva remanente liberada solo tras confirmar; costos reales actualizados | 2, 5 |
| EX-04 | Cancelación tardía | Fill llega después de solicitar cancelación o de callback cancelado: ledger y posición corregidos; ninguna reversión/venta duplicada | 2, 5 |
| EX-05 | Parada concurrente | Activar parada entre riesgo, outbox y gateway bloquea todo lo aún no enviado; conciliar/cancelar lo ya en vuelo; no afirmar atomicidad con IBKR | 2, 5 |
| EX-06 | Pérdida superior a stop | Gap atraviesa stop y límites: registrar exceso real, suspender y aplicar salida defensiva; nunca recortar P&L al límite configurado | 3, 5 |
| EX-07 | Fallo de protección | Rechazo de stop, bracket incompleto o desconexión con posición abierta: cancelar remanente, escalar y ejecutar protocolo defensivo permitido, sin depender de IA | 5 |
| EX-08 | Conciliación y recuperación | Operación manual, orden desconocida, fill corregido o comisiones tardías: detectar discrepancia, detener entradas y reconstruir antes de reanudar | 4, 5 |
| EX-09 | Dos ejecutores | Reinicio/partición/worker antiguo: fencing impide segundo escritor; estado de envío ambiguo permanece bloqueado | 2, 5 |
| AUD-01 | Auditoría y secretos | Reproducir una decisión con snapshot y versiones; intento de modificación de historial denegado a servicios; escaneo de reportes/logs sin secretos | 2, 5 |

Agregar pruebas basadas en propiedades para `Risk(q) <= B_new`, ausencia de cantidades negativas, monotonicidad frente a equity/costos, límites de precisión, y conservación de reservas/exposición bajo permutaciones de eventos. La monotonicidad se comprueba manteniendo constantes los demás factores; el mercado cambiante puede alterar el tamaño por otras causas.

## 4. Operación y criterios de suspensión a documentar en cada expediente

Además de límites de pérdida: calidad de datos, indisponibilidad IA para entradas, pérdida de conexión, error de autorización, órdenes desconocidas, violaciones de contrato, falta de protección, divergencia de conciliación, costos superiores al escenario autorizado, degradación fuera de límites definidos y cambio de régimen que invalide supuestos.

Cada causa tendrá severidad, quién recibe alerta, cuándo expira un permiso, qué se cancela, cómo se conserva/reduce exposición, evidencia necesaria y condiciones de reanudación. Definir objetivos de latencia de detección/protección y probarlos por instrumento y entorno antes de Live; no inventar una garantía universal de tiempo o precio.

Los informes incluirán métricas de abstención, rechazos, datos obsoletos, slips reales frente a estimados, límites alcanzados, duración de estados desconocidos y latencia de conciliación, además de rentabilidad. El objetivo de selección prioriza admisibilidad y robustez de riesgo; si ningún candidato pasa, la salida correcta es permanecer sin operar.

## 5. Verificación de esta entrega

- Ejecutado antes de crear documentos: comprobación de ausencia de grafo y detección Graphify, con cero archivos compatibles en la carpeta inicial.
- Fuentes oficiales de IBKR consultadas para orientar contratos y limitaciones; enlaces junto a las afirmaciones en el diseño. No se consultó ninguna cuenta ni se enviaron solicitudes al bróker.
- Ejecutado: verificación de enlaces locales y bloques de código equilibrados en ambos documentos; nueve comprobaciones aritméticas de los ejemplos (tres presupuestos, capacidad diaria, sizing, tres umbrales y un aporte). Resultados correctos. Son comprobaciones del diseño, no tests de un motor implementado.
- Revisado por inspección: cobertura de requisitos, separación de permisos, estados y correspondencia entre diseño y matriz de aceptación. No equivale a probar componentes de software.
- Pruebas unitarias, de integración, backtests, walk-forward, Monte Carlo y Paper: pendientes; no existe todavía implementación que las ejecute.
