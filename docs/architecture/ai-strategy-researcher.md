# AI_Strategy_Researcher

Actualización: [memoria DEFER y observador Paper](paper-evidence-observer.md). Las decisiones sin candidato se recuperan con integridad/procedencia; la vista compacta conserva todas las especificaciones únicas. Una investigación real requiere evidencia nueva validada por un estudio preregistrado de solo lectura antes de credenciales o reservas OpenAI. No se inicia el observador ni se conceden operaciones automáticamente.

Investigador autónomo separado del servicio de trading. Modo exclusivo `SIMULATION_ONLY`: propuestas declarativas, backtesting determinista y memoria persistente. No existe conexión de este módulo a TWS, órdenes, DPAPI, AccountBinding, RiskEngine, autorizaciones, promociones ni Live. `DisabledResearchAi` del servicio C# conserva su comportamiento.

## Componentes

En `python/trading_agent/ai_strategy_researcher/`:

- `contracts.py`: esquema cerrado y validación independiente de respuestas; candidatos LONG F/SPY, cuatro patrones controlados, ventanas y geometrías acotadas. Sin código generado, eval, imports dinámicos, shell ni instrucciones ejecutables del modelo. El nombre no cambia la versión del comportamiento.
- `data.py`: exportación mínima de datos auténticos de desarrollo, hashes/procedencia, resúmenes anuales y resúmenes numéricos de pérdidas ya examinadas. Excluye identidad/saldos/credenciales de cuenta y todas las velas de selección/final.
- `providers.py`: Responses API con `text.format` JSON Schema estricto, `store=false`, truncación deshabilitada y ningún tool del proveedor. Host/path TLS fijos `api.openai.com/v1/responses`; sin endpoints configurables, redirecciones ni fallback. Rechaza resultados incompletos, refusals, tool calls, modelo inesperado, consumo desconocido y JSON inválido.
- `tools.py` / `worker.py`: dos herramientas internas fijas, proveedor y simulación, con procesos de duración limitada. Entorno del simulador sin claves OpenAI/IBKR/BD; solamente el worker proveedor recibe `OPENAI_API_KEY`. No recibe comandos o rutas del modelo. No necesita instalar el SDK OpenAI; HTTP/JSON con biblioteca estándar y TLS verificado.
- `simulation.py`: indicadores causales y entradas en apertura posterior a vela completa; stop antes de target si ambos se tocan, gaps adversos sin limitar pérdidas, salida de regla en apertura siguiente, costos en ambos lados y riesgo independiente del modelo.
- `journal.py`: SQLite local, exclusión entre procesos, reservas previas al trabajo, candidatos/resultados inmutables e historial de eventos encadenados por hash. Un resultado incierto conserva el presupuesto consumido/reservado. Una sesión reiniciada no obtiene un presupuesto o deadline nuevo.
- `runner.py`: ciclo propuesta → validación → experimento → conclusión → próxima hipótesis, circuito de fallos y ranking. El modelo observa resultados previos limitados para formular hipótesis; no se reentrena automáticamente.

La separación se implementa por contratos, imports y herramientas permitidas. El proceso usa la identidad Windows del operador; no es un sandbox de sistema operativo para ejecutar Python arbitrario. Esa capacidad se evita completamente: candidatos JSON, sin fuente Python generada ni herramientas de acceso libre a archivos/red.

## Datos y validez de la evidencia

`prepare` deriva 12.024 velas F/SPY de 2021–2023 de `artifacts/research/equity-evidence/readonly.json`, verificando su SHA256 y vínculo con la revisión de integridad de 773 pruebas. Fuente original sin cambios. SCHX excluido por la discrepancia del split de 2022.

El paquete no contiene velas de selección 2024 ni de prueba final 2025–2026. Los resultados antiguos de selección 2024 ya conocidos se exportan únicamente como resúmenes numéricos etiquetados `PREVIOUSLY_EXAMINED_SELECTION_2024`, no como una validación nueva. No se usan datos abril–octubre 2026 del archivo previo.

Cada candidato queda congelado antes de sus experimentos: desarrollo 2021, validación interna 2022–2023, walk-forward 2022-H1 / 2022-H2 / 2023. Warm-up solamente del pasado y señales purgadas en fronteras. Sin refit en folds. Cada fold reinicia su asignación virtual; sus retornos no se suman como una cartera continua. Una validación continua separada usa una única asignación para 2022–2023.

Estos datos ya se han examinado. Los folds que alimentan nuevas hipótesis se convierten en memoria de investigación; no son una confirmación independiente ni un test final repetible para elegir ganadores. **Este CLI no incluye un comando para abrir la prueba final.** Evaluación formal posterior exige candidato/configuración/costos congelados, datos corporativos completos, datos nuevos independientes y revisión externa al ciclo del modelo.

F/SPY constituyen un universo de conveniencia con sesgo de supervivencia no resuelto. Dividendos/retenciones/intereses no se imputan ni acreditan; su cobertura incompleta bloquea aprobación. Permisos, fracciones, tarifa efectiva, settled cash, margen/intradía y protección IBKR siguen UNKNOWN. Recibir un contrato o tener precio asequible no prueba capacidad de ejecución.

## Política y evaluación

- Capital aislado US$100, exposición máxima 1× equity del simulador, una posición LONG y acciones enteras. Nunca usa el millón ficticio Paper ni fondos no liquidados.
- Riesgos de hipótesis permitidos: 1%, 2%, 3%, 5%, 7.5%, 10%, 12.5%, 15%. Riesgo total incluye movimiento a stop, apertura/cierre, spread, slippage, gap reservado y redondeos. Techo del laboratorio US$15 por operación; pérdidas consumidas máximas US$20, sin reposición por ganancias. No cambia ningún límite operativo.
- `WIN_TO_CONTINUE / FIRST_LOSS_STOPS_DAY` con día America/Santo_Domingo. Beneficio neto positivo permite buscar otra señal con fondos liquidados; loss/break-even bloquean nuevas entradas. Pendiente no equivale a ganador y NO_TRADE no cuenta como operación. No hay cuota diaria.
- Tiered base, stress de spread/slippage/gap y Fixed stress usan la envolvente económica de investigación existente. Tarifas estimadas, no comisiones verificadas de cuenta. Próxima sesión observada se utiliza para T+1 simulado; no presupone capacidad intradía real.
- 15 backtests por candidato: cinco ventanas × tres costos. Métricas incluyen admitidas/rechazadas, win neto, beneficio/pérdida media, expectativa, PF, drawdown marcado conservadoramente, comisiones, spread/slippage, días detenidos, breaches por gaps y resultados no definitivos.
- Wilson95 y Wilson ajustado por comparaciones previas y propuestas reservadas, más bootstrap aproximado por bloques de días. Objetivos mínimos de investigación: 100 operaciones/30 días, win neto y límite inferior ajustado >80%, expectativa positiva con intervalo positivo, PF>1, tres folds positivos, robustez a costos y drawdown ≤20% sin breaches. No constituyen garantías.
- Incumplimiento descarta evidencia (`DISCARDED_RESEARCH_EVIDENCE`). Cumplimiento como máximo produce `INDEPENDENT_VALIDATION_REQUIRED`. Nunca `PAPER_EXPERIMENTAL`, PaperAuto, LiveApproved o autorización de ejecución.
- Ranking lexicográfico: suficiencia de evidencia → expectativa neta → peor neto entre costos → menor drawdown → win rate. No seleccionar por acierto aislado. Ruina/probabilidad de ejecución permanecen null cuando no se pueden estimar.

## Presupuestos y credenciales OpenAI

Configuración: `config/ai-strategy-research.json`. Defaults: tres llamadas, tres candidatos, 45 backtests, 300 segundos, 120.000 tokens totales, salida máxima 2.048 tokens y US$1 por sesión. Provider timeout 30 segundos, simulación 60 segundos, circuito tras dos fallos. Son límites de investigación, no riesgo financiero de operaciones.

Modelo configurado: `gpt-6.1-sol`; su acceso efectivo quedó confirmado por las tres llamadas completadas de `research-openai-001`, descritas en el diagnóstico posterior. El modelo y la tabla de precios deben coincidir explícitamente. Techos conservadores de entrada/salida US$5/US$15 por millón, consultados el 2026-10-06: incluyen el mayor precio estándar publicado de entrada/cache-write para el modelo. Verificar disponibilidad y precios antes de cambiarlo; la fecha de precios caduca a los 30 días para modo online. Tarifa estimada desde usage, no factura OpenAI certificada; cached input se contabiliza conservadoramente sin descuento. No solicita modos Fast, herramientas pagadas ni endpoints regionales.

Reserva previa de tokens: bytes UTF-8 completos del cuerpo más framing conservador y máximo de salida. Si el proveedor devuelve consumo superior a la reserva, suspende. Uso perdido/timeout mantiene toda la reserva. Deadline, llamadas, tokens y costo persisten al reiniciar; configuración/dataset/herramientas distintos no pueden reutilizar el mismo ID de sesión. Nuevo ID es una nueva sesión solicitada explícitamente por el operador, con su presupuesto propio; el runner nunca crea otra para eludir límites.

La única credencial leída es `OPENAI_API_KEY`, proporcionada al proceso mediante entorno/gestor de secretos. No guardar claves en JSON, `.env`, comandos literales, prompts, respuestas archivadas o logs. Preferir clave de proyecto OpenAI dedicado con límites del proveedor además del control local. El consumo registra modelo, correlación, latencia, tokens, costo estimado y resultado; no persiste Authorization ni errores brutos. `store=false` no sustituye los controles de retención del proveedor.

## Inicio en PowerShell

Desde la raíz del proyecto, preparar datos y ejecutar una sesión offline:

```powershell
$env:PYTHONPATH = 'python'
.venv/Scripts/python.exe -m trading_agent.ai_strategy_researcher prepare --root .
.venv/Scripts/python.exe -m trading_agent.ai_strategy_researcher run --root . --provider simulated --session mi-investigacion-offline-001
.venv/Scripts/python.exe -m trading_agent.ai_strategy_researcher status --root . --session mi-investigacion-offline-001
```

Para usar OpenAI después de verificar el modelo/precios y presupuesto, introducir la clave sin mostrarla:

```powershell
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host 'OpenAI API key' -AsSecureString)).Password
.venv/Scripts/python.exe -m trading_agent.ai_strategy_researcher run --root . --provider openai --session mi-investigacion-openai-001
.venv/Scripts/python.exe -m trading_agent.ai_strategy_researcher status --root . --session mi-investigacion-openai-001
Remove-Item Env:OPENAI_API_KEY
```

No introducir ni exportar credenciales IBKR. Estos comandos no renuevan autorizaciones, no revisan/levantan emergencia y no inician ningún runner Paper. Una sesión terminal se consulta sin repetir experimentos. Para una sesión incierta, revisar `status` y el journal; no borrar el registro para recuperar presupuesto.

## Artefactos

`artifacts/research/ai-strategy-research/`: dataset mínimo con SHA, `journal.sqlite3`, candidatos con especificación/version/dataset/herramientas/resultados y `sessions/<id>/report.json` + `report.md`. Reportes con ranking y límites, sin aprobaciones. Cambios en fuentes protegidas, paquete, config o herramientas bloquean la reutilización silenciosa de sesión.

Pruebas y auditoría: `artifacts/test-results/ai-strategy-research/`. La prueba offline verifica el ciclo real de workers con API simulada; el transporte HTTP se verifica con dobles de prueba. No se realiza una llamada OpenAI facturable ni consulta IBKR en esta fase.

## Documentación oficial consultada

- [Structured Outputs y Responses text.format](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).
- [Responses API: creación, max_output_tokens y usage](https://developers.openai.com/api/reference/python/resources/responses/methods/create).
- [Precios publicados](https://developers.openai.com/api/docs/pricing).
- [Controles de datos/retención](https://developers.openai.com/api/docs/guides/your-data).

## Verificación ejecutada

833 pruebas aprobadas: 593 Python + 240 C#, sin fallos ni omisiones. Sesenta pruebas nuevas del investigador. Build .NET con cero errores/advertencias y compileall Python correcto; PostgreSQL desechable detenido al terminar. Auditoría SHA256: 41 archivos/estados protegidos idénticos, incluyendo datos/evidencia anteriores. Emergencia activa, PaperAuto ausente, cero órdenes y Live bloqueado.

[Auditoría y pruebas](../../artifacts/test-results/ai-strategy-research/verification.json). [Informe de la sesión offline](../../artifacts/research/ai-strategy-research/sessions/prepared-offline-773/report.md): 45 backtests, tres candidatos, cero llamadas OpenAI reales, cero tokens API y US$0 de costo API. Trend: 11 operaciones de validación, neto −US$16.33; Mean Reversion: 10, neto −US$14.32; Breakout: 14, neto −US$8.23. Todos descartados por economía y evidencia; no es una búsqueda exhaustiva ni un resultado de OpenAI real. Son hipótesis de prueba del flujo, separadas de las estrategias productivas.

En la fase inicial de 833 pruebas, el transporte OpenAI se verificó con documentación oficial y pruebas HTTP simuladas; todavía no se había conectado realmente al proveedor. La evidencia de la primera sesión real y sus limitaciones se describen a continuación.

## Diagnóstico de la primera sesión real

`research-openai-001` confirmó tres Responses completadas con `gpt-6.1-sol`: 14.827 tokens de entrada y 2.996 de salida. La primera propuesta fue válida y completó 15 backtests; su candidato LONG F/PULLBACK diario al 2% fue descartado por economía y evidencia. Las siguientes dos propuestas fallaron la validación local y suspendieron la sesión mediante `INVALID_PROPOSAL_CIRCUIT_OPEN`. Sus cuerpos y excepciones específicas no se conservaron: solo existe el motivo genérico `UNTRUSTED_PROPOSAL_INVALID`. No es posible identificar retrospectivamente el campo ni atribuir el fallo a un parámetro concreto. No se recuperaron respuestas del proveedor ni se hicieron llamadas API durante este diagnóstico.

Los US$0.119075 corresponden a consumo API confirmado multiplicado por los techos conservadores configurados, no a una factura ni a reservas aún pendientes. Las tres reservas iniciales sumaban US$0.369960; se liberaron US$0.250885 al confirmar `usage`. Caché, desglose de razonamiento y facturación efectiva de esas llamadas no quedaron registrados.

El esquema de generación ahora comunica rangos numéricos, riesgos permitidos, patrón del identificador y referencias de evidencia vinculadas al contexto. Las instrucciones explican `fast < slow`, enteros JSON sin `.0`, unidades, límites de texto UTF-8 y los patrones/semántica que realmente implementa el simulador. La validación independiente continúa siendo obligatoria: no se amplían límites, no se reparan parámetros automáticamente y una propuesta válida puede ser económicamente inviable.

Cada aceptación/rechazo nuevo queda asociado al `call_id` y SHA256 de los bytes UTF-8 de la propuesta. Los rechazos registran código fijo, campo y categoría FORMAT/PARAMETER/EVIDENCE, sin guardar respuestas inválidas, valores sensibles ni excepciones brutas. Solo ese diagnóstico acotado se comunica al siguiente intento dentro del presupuesto existente. Los fallos consecutivos se reconstruyen desde el journal al reiniciar; una propuesta válida los reinicia, pero un descarte económico no se registra como fallo del contrato. El transporte conserva detalles numéricos de caché/razonamiento cuando el proveedor los expone, sin aplicar descuentos optimistas al presupuesto.

Se preservan journal, reportes y candidato originales. El cambio de herramientas/contrato exige un ID nuevo: no reutilizar `research-openai-001`. El presupuesto continúa en US$1, tres llamadas, tres candidatos y 45 backtests máximos. Próxima sesión preparada mediante el CLI existente:

```powershell
$env:PYTHONPATH = 'python'
.venv/Scripts/python.exe -m trading_agent.ai_strategy_researcher run --root . --provider openai --session research-openai-002
```

Este comando no se ejecutó durante el diagnóstico. [Informe y reconciliación de costos](../../artifacts/test-results/ai-strategy-research/research-openai-001-diagnosis.md). Se ejecutaron 75 pruebas del investigador, 15 nuevas, y compilación sintáctica Python; la base anterior de 833 pruebas no se vuelve a contar como ejecutada en esta fase. Emergencia y controles de ejecución sin cambios, cero llamadas API de diagnóstico y cero órdenes.

## Auditoría de costos e inventario H40

La revalidación de `research-openai-002` conserva la versión H40 y sus funciones de señales/salidas. La identidad del modelo de costos se registra por separado como `US_WHOLE_SHARE_CONSERVATIVE_20261006_V2`; el hash de herramientas cambia y no se reutiliza silenciosamente una sesión anterior. [Informe completo](../../artifacts/test-results/ai-strategy-research/h40-accounting-audit/report.md).

`costs.py` separa BUY/SELL, comisión base con mínimo/cap, cargos regulatorios, clearing/pass-through Tiered, contingencia no asignada y reserva por redondeo. Fixed no vuelve a cargar clearing/pass-through incluidos. Se conserva el suplemento antiguo de US$0.02 por orden + US$0.01 por acción como contingencia ESTIMATED para cargos desconocidos, sin afirmar que IBKR lo cobra ni que constituye un techo garantizado. Las tarifas públicas consultadas en 2026 sobre precios de 2021–2023 son un escenario prospectivo conservador, no facturas históricas ni verificación de la tarifa efectiva Paper. La exención temporal TAF no se usa para abaratar el escenario; discrepancias de cap, venue, recargos de cuenta, impuestos, modificaciones, fills parciales y mínimos de órdenes persistentes siguen UNKNOWN. Esos datos no habilitan ejecución ni promoción.

Al terminar una ventana exclusiva, se valora inventario con el último cierre de vela completada estrictamente antes del límite, nunca con datos de selección/prueba final ni precios posteriores. `exit_event` recibe únicamente velas de esa ventana: no se inventa una venta en el límite ni se altera el máximo de permanencia. Si no hay precio válido, la valoración permanece UNKNOWN y el resultado no definitivo.

`net_pnl`, `profit_factor`, `win_rate`, `net_expectancy` y `commissions` mantienen su alcance de operaciones cerradas. `opening_commissions` incluye todas las entradas, `closing_commissions` solo ventas efectivas simuladas y `commissions_incurred` incluye el BUY del inventario pendiente. `portfolio_net_pnl`/`equity` incorporan su movimiento de precio y comisión de entrada; `estimated_liquidation_equity` reserva además fricción y comisión SELL sin registrar un fill ni comisión realizada. El patrimonio se concilia contra efectivo contable + proceeds no liquidados + valor de inventario. Las comisiones estimadas de entrada pendiente se exponen como gasto incurrido, aunque no formen parte de un trade completo.

`marked_drawdown` usa NAV cronológico de entrada, cierres de velas completas y salidas. `maximum_drawdown` conserva un límite conservador intravela que incluye inventario pendiente: OHLC no demuestra si un low ocurrió antes o después del stop, por lo que no se presenta como trayectoria intravela observada. Los dos drawdowns se distinguen. No se cuentan marks positivos como victorias, no se liberan fondos por valorar, no se restaura presupuesto consumido y no se admite otra posición mientras quede inventario pendiente. Cada fold sigue siendo una asignación independiente de US$100; no se suman ventanas solapadas como rendimiento de una cartera continua. Prueba final sellada, PaperAuto sin conceder, emergencia activa y Live bloqueado.

## Memoria y razonamiento con retroalimentación

`memory.py` recupera todos los experimentos del journal (límite explícito 1.000, sin olvidar silenciosamente los antiguos), verifica su cadena y el hash de los resultados completos, y conserva hipótesis/rationale, versión/parámetros, rechazos, métricas netas/costos, intervalos, ventanas cronológicas, inventario pendiente, limitaciones y restricciones UNKNOWN. El plan del modelo no es evidencia económica. Las descripciones históricas no sustituyen la especificación declarativa que realmente ejecutó el simulador: por ejemplo, no se considera probado un filtro narrativo que el patrón fijo no implementó.

Importa automáticamente la auditoría H40 desde su ruta fija, únicamente si resultado/verification coinciden, la versión y candidato se vinculan al journal y la prueba final continúa sellada. El resumen inicial usa H40 auditado; el resultado antiguo se conserva íntegro como evidencia superseded. Posiciones pendientes anteriores sin detalle permanecen desconocidas, sin inventar fills. Los registros de proveedor OpenAI real siguen teniendo rendimiento SIMULATED y costos ESTIMATED; solo procedencia e integridad del registro se confirman. Tarifas efectivas, permisos y protección Paper no se deducen de contratos o backtests.

Los snapshots son archivos inmutables identificados por SHA256 en `artifacts/research/ai-strategy-research/memory/<sha>.json`: reutilización idéntica permitida, sobrescritura divergente prohibida. No se modifican las sesiones antiguas al consultar memoria. CLI local sin API ni backtesting:

```powershell
$env:PYTHONPATH = 'python'
.venv/Scripts/python.exe -m trading_agent.ai_strategy_researcher memory --root .
```

Antes de cada propuesta, el runner reconstruye/persiste el snapshot y entrega un resumen de hasta 7.500 bytes, reduciéndolo si hace falta para respetar el límite completo del request. Selección por recencia/procedencia, nunca por P&L favorable; se registra cuántos resultados quedan fuera del prompt. Los controles de repetición consultan todo el historial, incluso los registros omitidos. Las métricas cortas y códigos de rechazo llevan diccionarios explícitos; hipótesis resumidas son extractos y el texto completo permanece en el snapshot. En el estado inicial incluye research-openai-001, H8/H20 de research-openai-002 y H40 auditado. Si el contexto mínimo no cabe, se detiene antes de reservar/enviar una llamada.

Responses mantiene JSON estricto. `research_plan` exige acción, problema, análisis de fallos, novedad falsable, motivo de evaluación, insuficiencia de evidencia, criterio de refutación, alternativas, referencias previas y campos materialmente cambiados. Las referencias se vinculan a los IDs realmente entregados. No se ejecuta código del modelo. Las alternativas fuera de F/SPY o 60/1440 minutos son recomendaciones, no ampliaciones automáticas del universo o del motor.

La familia declarativa es instrumento + temporalidad + patrón. Se bloquea comportamiento exacto ya investigado aun cambiando nombre/costos/herramientas/sesión; un cambio solo de riesgo o del EMA fast inerte de MEAN_REVERSION no constituye hipótesis nueva. En la misma familia se exige referencia a la especificación previa más cercana y lista exacta de cambios. Como política conservadora de investigación, variaciones inferiores al 20% en todos los parámetros cambiados se rechazan para contener búsquedas repetitivas. No es un umbral de equivalencia estadística ni prueba de novedad causal. El slow de MR sí puede cambiar warmup y no se trata como inerte. Una hipótesis nueva material necesita justificación estructurada y todas las validaciones económicas independientes, sin excepción de límites operativos.

El ciclo es memoria → problema/hipótesis → candidato → simulador → validación → conclusión persistente → nueva consulta de memoria dentro del presupuesto. Eventos RESEARCH_MEMORY_CONSULTED, RESEARCH_HYPOTHESIS_PLANNED y RESEARCH_CONCLUSION_RECORDED vinculan call/version/snapshot. Los rechazos específicos alimentan el intento siguiente y el circuit breaker existente; reiniciar no elimina fallos ni resultados anteriores. `DEFER_RESEARCH` con candidato null permite terminar tras una respuesta sin crear candidato ni reservar backtests cuando faltan datos o una hipótesis justificada. Las conclusiones registran fracaso del objetivo observado bajo ese escenario, no refutación causal general cuando falta evidencia independiente. No hay reentrenamiento automático.

Se conservan los filtros de muestra, intervalos, expectativa/PF netos, drawdown, sensibilidad a costos, walk-forward y resultado definitivo. Datos ya examinados 2021–2023 no se presentan como OOS independiente. La prueba final no se abre y una tasa de acierto alta no concede aprobación.

El presupuesto existente permanece US$1, máximo 3 llamadas, 3 candidatos, 45 backtests, 120.000 tokens, 300 segundos y 2 fallos consecutivos. La implementación y pruebas usan proveedores simulados; no se inicia investigación real. El ID research-openai-003 se ofrece únicamente para ejecución posterior autorizada:

```powershell
$env:PYTHONPATH = 'python'
.venv/Scripts/python.exe -m trading_agent.ai_strategy_researcher run --root . --provider openai --session research-openai-003
```

Este comando obtiene OPENAI_API_KEY de la terminal y el modelo `gpt-6.1-sol` de la configuración protegida existente. No imprime la clave, no modifica presupuestos, no renueva autorizaciones Paper y no transmite órdenes. Si el modelo decide aplazar, termina sin backtests. [Auditoría de memoria y verificación](../../artifacts/test-results/ai-strategy-research/research-memory/report.md).
