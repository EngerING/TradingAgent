# Observador Paper y memoria completa de investigación

Servicio aislado de solo lectura para Ford (F), sin acceso a herramientas OpenAI, estrategias ni transporte de órdenes. La preparación no inicia conexiones. La implementación todavía no ha observado una sesión auténtica: las comprobaciones del transporte y del ciclo se hicieron con fixtures. Su funcionamiento real se verificará después de revisar configuración e iniciar explícitamente el observador.

## Memoria

`memory_decisions` recupera todos los eventos RESEARCH_DEFERRED, sesiones y resultados del proveedor, incluidos errores sin candidato. Verifica cadena, llamada completada, evento de consulta y snapshot original. `memory.build` comprueba hash del archivo original y contrato del plan; conserva el plan completo, procedencia, decisiones y errores seguros. research-openai-003 permanece intacta. No es reentrenamiento del modelo.

El contexto incluye las siete especificaciones únicas del historial actual. Ejecuciones offline repetidas se agrupan en la vista compacta; H40 auditado sustituye su contabilización antigua solamente en el resumen. La memoria completa conserva ambas. Todos los experimentos siguen disponibles para el control determinista de duplicados. Los tres DEFER más recientes se resumen con textos acotados y conteo total; los planes originales completos siguen en snapshots/journal. Se preservan las métricas auditadas de inventario pendiente. No se recortan especificaciones silenciosamente para caber en tokens: si el ledger obligatorio supera el límite, se bloquea la llamada.

Cambios de nombre/riesgo, parámetros inertes o ajustes relativos inferiores al 20% no eluden controles anteriores. El comportamiento exacto ya investigado sigue rechazado incluso con evidencia nueva: una repetición formal requeriría una fase independiente futura. Una decisión de aplazar no se considera ganancia, estrategia ni backtest.

Antes de llamadas reales del investigador, `research_preflight` exige un estudio terminado, íntegro y READY que incluya en su baseline todos los DEFER actuales y el mismo historial de experimentos. Se comprueba antes de leer credenciales OpenAI, reservar una llamada o crear sesión. El contexto recibe la procedencia y resumen económico de la nueva evidencia, con IDs citables; una futura decisión DEFER que cite esa evidencia también será recuperable. La vía de smoke-test de conexión OpenAI queda separada; este gate se aplica a la investigación completa.

## Configuración revisable

Archivo: `config/paper-evidence-observer.json`.

| Regla | Valor |
|---|---|
| Entorno / instrumento | PAPER_TRADING / F, STK, USD, SMART |
| Capital / exposición | US$100 / 1×, sin dimensionamiento desde saldos Paper |
| Ventana | 20 sesiones RTH auténticas consecutivas |
| Primera sesión | Primera sesión completa cuya apertura ocurra después del primer Run explícito |
| Muestreo | 60 segundos más tiempo de consulta; no se supone periodicidad perfecta |
| Calendario | SCHEDULE actual de IBKR (30 D, RTH) y liquidHours; renovación cada 3.600 segundos |
| Capacidades de cuenta | Cuatro consultas de lectura, cada 86.400 segundos y después de reconectar |
| Timeout por consulta / clientId | 20 segundos / 92; comprobar que clientId esté libre |
| Calidad de recepción | BID y ASK recibidos hace como máximo 30 segundos |
| Cobertura mínima | 90% de slots LIVE válidos en **cada** sesión |
| Gap máximo | 180 segundos, incluyendo bordes apertura/cierre |
| Anomalía | Libro cruzado, timestamp futuro/inválido, discontinuidad de midpoint >10% sin explicación causal |
| Futuro presupuesto preparado | US$1,00; cero gasto automático |

`prepare` guarda copia canónica inmutable de configuración, protocolo, timestamps, hashes de memoria/binding y condiciones de análisis. Si se altera config después, un estudio preparado continúa usando su especificación original. Nunca se sobrescribe una especificación: para cambiarla debe preregistrarse otro identificador antes de observar. La fecha de inicio efectiva se registra una única vez con Run y persiste tras reinicios; retrasar la revisión no consume sesiones del estudio.

El calendario no usa días hábiles inferidos, holidays propios ni PROVISIONAL_REGULAR_TEMPLATE. Conserva recibos SCHEDULE, horarios del contrato y UTC; conflictos/DST incierto bloquean calidad. La cobertura de calendario debe cubrir todo el intervalo desde inicio hasta cierre de la vigésima sesión. Las declaraciones por día del contrato cubren también CLOSED y el cierre actual aunque SCHEDULE termine en la hora de consulta. Si un apagado supera cobertura disponible, no se presume que las sesiones conocidas sean consecutivas.

Se cuentan las primeras veinte sesiones auténticas elegibles, incluidas sesiones sin muestras o de baja calidad. Nunca se prolonga el estudio para sustituir días malos por buenos. Una sesión anterior al primer Run o parcialmente iniciada queda excluida por la regla preregistrada. La vigésima sesión terminada produce evaluación determinista y detiene el loop aunque el resultado esté bloqueado.

## Observaciones y reanudación

Journal SQLite independiente, transacciones durables y cadena de hashes, vinculado al SHA de la especificación. Bloqueo de proceso por estudio; status/evaluate abren SQLite de solo lectura con una transacción consistente. Reiniciar usa el mismo inicio, calendario, observaciones y slots. `stop.request` solo pertenece al observador; no toca EmergencyStop ni autorizaciones. Ctrl+C registra parada y desconecta. Un crash mantiene evidencia ya confirmada para el próximo Run.

Se guardan BID/ASK originales, spread derivado, timestamps UTC de recepción por campo, tipo de mercado IBKR, last-trade timestamp si llega, tamaños BID/ASK y volumen bruto con timestamps cuando existen, códigos IBKR, errores por tipo y desconexiones. Las unidades de volumen/tamaño quedan UNKNOWN mientras no se verifiquen. No hay interpolación, backfill histórico de muestras perdidas ni precios futuros. Gaps se calculan en el reporte, incluyendo sesiones completamente ausentes. Capturas repetidas dentro del mismo slot no inflan cobertura.

LIVE significa callback IBKR tipo 1; DELAYED tipo 3. Frozen/delayed-frozen o edad de recepción excesiva se clasifican STALE. BID/ASK incompletos, tipos desconocidos, valores inválidos o timestamps incoherentes se clasifican MISSING. La recepción reciente **no** es un timestamp de bolsa del BID/ASK; esa condición se etiqueta explícitamente UNKNOWN. Last-trade time no se reutiliza para fechar BID/ASK. Slippage y aceptación efectiva de protección no se miden. Ninguna cotización se marca ejecutable por este servicio.

Identidad exacta Paper se vuelve a exigir al conectar mediante AccountBinding existente; no se migra ni renueva. Cambio de binding o contrato y errores de identidad/permiso en el ciclo de conexión suspenden el servicio. Permisos de negociación no expuestos permanecen UNKNOWN. Otros fallos de lectura/desconexión se registran, desconectan y reintentan solo lecturas en el siguiente ciclo, con nueva verificación exacta al reconectar. No existe API de órdenes; placeOrder, variantes ProtoBuf, cancelOrder, global cancel, ejercicio y auto-open-orders siguen bloqueados en ReadOnlyClient. No se usa what-if.

## Comandos desde la raíz, después de revisar la configuración

Preparar un estudio (solo archivos locales, sin conexión):

```powershell
$env:PYTHONPATH = 'python'
.\.venv\Scripts\python.exe -m trading_agent.paper_evidence_observer prepare --root . --study ford-evidence-001
```

Si `ford-evidence-001` ya está preparado, no repetir prepare. Iniciar o reanudar en la terminal:

```powershell
$env:PYTHONPATH = 'python'
.\.venv\Scripts\python.exe -m trading_agent.paper_evidence_observer run --root . --study ford-evidence-001
```

Consultar progreso desde otra terminal:

```powershell
$env:PYTHONPATH = 'python'
.\.venv\Scripts\python.exe -m trading_agent.paper_evidence_observer status --root . --study ford-evidence-001
```

Detener cooperativamente desde otra terminal (también se admite Ctrl+C):

```powershell
$env:PYTHONPATH = 'python'
.\.venv\Scripts\python.exe -m trading_agent.paper_evidence_observer stop --root . --study ford-evidence-001
```

La parada respeta la consulta de lectura en curso; se revisa entre consultas y cada segundo de espera. No es un servicio instalado que arranque automáticamente con Windows. Reanudar exige repetir Run y borra solamente la petición de parada de este estudio.

`evaluate` usa el mismo motor determinista que status. `preflight` comprueba toda la evidencia disponible sin credenciales ni red:

```powershell
.\.venv\Scripts\python.exe -m trading_agent.paper_evidence_observer evaluate --root . --study ford-evidence-001
.\.venv\Scripts\python.exe -m trading_agent.paper_evidence_observer preflight --root .
```

## Capacidades automáticas y evidencia humana

Se recogen summary, ledger USD, updates y multi con marcador de completitud, callbacks y valores originales. SettledCash solo se verifica si fue reportado consistentemente en una consulta completa; no se sustituye por AvailableFunds, BASE ni un cero inferido. El saldo recibido nunca modifica los US$100 virtuales. MinSize/incremento, tipos de orden y horarios son declaraciones del contrato, no permisos ni aceptación efectiva. La cuenta real nunca se consulta como fallback.

Permisos efectivos, fracciones, plan Fixed/Tiered aplicable, cargos efectivos, margen específico, restricciones intradía y aceptación de bracket normalmente no se exponen en estas consultas: quedan UNKNOWN. Se conserva la diferencia VERIFIED/ESTIMATED/UNKNOWN y origen. No se concede IBKR Lite ni se presume margen/PDT universal. Fracciones UNKNOWN no impiden describir enteras, pero no habilitan fallback fraccionario.

La intervención pendiente sigue el procedimiento Paper de `equity-account-data-integrity.md`: confirmar la cuenta Paper en TWS/Portal, leer permisos US/fracciones y plan, tipo/régimen, fondos liquidados y restricciones; solicitar confirmación escrita de IBKR si el panel Paper no los expone. Obtener calendario corporativo/dividendos completos de F. Sin Transmit, Preview/what-if, cambios de permisos o panel Live como sustituto. Una fuente pública de tarifas sola no demuestra aplicación a esa cuenta.

Existe `attach-evidence --manifest <archivo>` para adjuntar **documentación Paper verificada por el operador**, sin atribuir esa verificación al API. No concede permisos operativos. Cada fuente debe archivarse en `artifacts/research/paper-evidence-observer/evidence/`, con SHA256; el manifiesto debe tener environment PAPER_TRADING, account_binding_sha256 de la especificación y facts. Se rechazan scope Live, binding ausente/distinto, archivos modificados, fechas previas al preregistro, valores desconocidos favorables y campos extra.

Cada fact tiene name/status/value/source/source_path/source_sha256/observed_at; source debe ser OPERATOR_VERIFIED_PAPER_DOCUMENT y status VERIFIED. Nombres requeridos: stock_etf_permissions (true), effective_fee_plan (TIERED/FIXED), SettledCash_USD (importe ≥100), effective_minimum_quantity y quantity_increment (enteros ≥1). effective_per_order_fees debe contener reviewed_for_fully_funded_100_usd_long=true y conservative_roundtrip_cost_usd_at_minimum positivo, respaldado por reglas completas de ambos lados; no implica una comisión realizada. effective_intraday_restrictions y contract_specific_margin requieren reviewed_for_fully_funded_100_usd_long=true y compatible_with_study=true. corporate_action_coverage requiere value COMPLETE, coverage_start/end UTC que cubran toda la ventana. Fechas/documentos deben expresar su ámbito y condiciones; los textos se validan contra secretos. La fuente humana se identifica siempre como tal y se revalida por hash al consultar progreso.

Adjuntar datos no es inventarlos: si no pueden confirmarse con documentación Paper suficiente, no crear un manifiesto favorable. Tamaños/fracciones/protección declarados por metadata no satisfacen aceptación efectiva. Los tests usan documentos y datos sintéticos; no prueban permisos reales.

## Criterios exactos de evaluación

1. Menos de veinte sesiones cerradas: INSUFFICIENT_EVIDENCE.
2. Veinte sesiones, pero calendario discontinuo/conflictivo, cobertura LIVE inferior al 90% en alguna, gap >180 segundos o anomalías: DATA_QUALITY_BLOCKED.
3. Calidad suficiente, pero falta cualquiera de ocho capacidades requeridas: EXECUTION_CONSTRAINT_BLOCKED. SettledCash debe alcanzar US$100 y tener observación de como máximo 24 horas. Todos los demás valores necesitan evidencia pertinente y fuente; no se inventan desde contrato.
4. Capacidades completas pero cobertura corporativa de la ventana no documentada: DATA_QUALITY_BLOCKED.
5. Tamaño mínimo efectivo × ASK máximo observado + costo conservador roundtrip al mínimo >US$100: EXECUTION_CONSTRAINT_BLOCKED. No se aumenta exposición ni capital.
6. Todas las condiciones anteriores pasan: EVIDENCE_READY_FOR_RESEARCH. Prepara problema y presupuesto máximo US$1,00, sin candidato, backtests o llamadas. La novedad consiste en observaciones prospectivas y documentación posteriores al preregistro, no resultados reutilizados. Un baseline desactualizado respecto de nuevos DEFER/experimentos no autoriza la siguiente investigación.

READY habilita únicamente la preparación de una investigación futura explícitamente autorizada. No certifica edge, win rate >80%, viabilidad de ejecución, rentabilidad ni aprobación Paper/Live. Comisiones realizadas, fills, slippage efectivo y aceptación de protección permanecerán UNKNOWN sin evidencia previa o una fase posterior expresamente autorizada. La prueba final sigue sellada.

## Referencias del transporte

IBKR documenta los tipos Live/Frozen/Delayed/Delayed-Frozen y los callbacks tickPrice/tickSize; el servicio conserva la etiqueta recibida y no confunde fallback solicitado con entitlement efectivo. [Market data types](https://www.interactivebrokers.com/docs/tws-api/doc/market-data-delayed/introduction), [Requesting market data](https://www.interactivebrokers.com/docs/tws-api/doc/quick-start/requesting-market-data).

La petición SCHEDULE usa historicalData/historicalSchedule y no precios para inferir calendario. [Historical schedule](https://interactivebrokers.github.io/tws-api/historical_bars.html). Los timestamps de last trade y tamaños tienen callbacks separados. [Tick types](https://interactivebrokers.github.io/tws-api/tick_types.html).
