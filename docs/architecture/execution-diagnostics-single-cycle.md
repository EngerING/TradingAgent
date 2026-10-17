# Un único ciclo ExecutionDiagnostics — preparación 2026-10-05

Preparado, sin ejecutar contra IBKR. StrategyPaper permanece bloqueado, ninguna estrategia se promueve a `PAPER_EXPERIMENTAL`, exposición StrategyPaper 1× sin cambios, emergencia activa y autorización anterior vencida. Live permanece bloqueado.

Se aplicó `senior-software-engineer` y se consultó Graphify antes de leer el transporte/journal. El grafo anterior no contiene todo el laboratorio actual; sus referencias se contrastaron con código y pruebas dirigidas.

## Alcance protegido

| Control | Valor |
| --- | --- |
| Instrumento | EUR/USD CASH IDEALPRO, conId 12087792 |
| Entorno/cliente | PAPER_TRADING, puerto 7497, clientId 82 |
| Intentos de diagnóstico | Uno por cuenta/journal, incluso entre sesiones y reinicios |
| Cantidad máxima | 100 EUR; no representa una asignación StrategyPaper |
| Nominal máximo | US$150, comprobado con ask y precio de entrada redondeado |
| Presupuesto independiente | US$10, reservado completo antes de enviar |
| Autorización | Máximo 30 minutos; identidad completa y proceso TWS vinculados |
| Cierre | Preparación inmediata tras conciliar el primer fill; envío de cierre como máximo 60 segundos después de ese fill |

Si el timestamp de ejecución no puede interpretarse inequívocamente, queda `null`; el plazo usa conservadoramente la hora anterior de envío. El primer fill fija un plazo persistente, que otros parciales no amplían. Las consultas previas al cierre comparten ese plazo. Si vence, se suspende sin SELL nuevo, sin reintento y conservando protección conocida. No se garantiza cierre ejecutado dentro de 60 segundos.

El stop usa bid menos 0.001 USD/EUR, el target entrada más 0.0015, en incrementos de 0.00005. La estimación de riesgo suma distancia entrada-stop (incluido spread/redondeo), US$4 de comisión ida/vuelta, 0.00045 USD/EUR de slippage y 0.00005 USD/EUR de gap presupuestado. Se rechaza si supera US$10. Estos son supuestos conservadores, no comisiones recibidas ni garantía frente a un gap real. No se dimensiona con el patrimonio ficticio de IBKR.

## BUY, SELL y protección

La intención, reserva y tres IDs se guardan antes del envío. BUY LMT es el padre; TP SELL LMT y stop SELL STP conservan parentId, orderRef y OCA tipo 2. La transmisión es false/false/true, siguiendo la [documentación oficial de brackets](https://www.interactivebrokers.com/docs/general/order-types/complex-orders/bracket-orders) y [campos de Order/OCA](https://www.interactivebrokers.com/docs/tws-api/ref/order).

El cierre modifica únicamente el TP existente. Requiere inventario BUY propio positivo, identidad/contrato/cliente/IDs coincidentes, padre terminal y snapshot estricto reciente. La cantidad pendiente de vender debe igualar exactamente BUY ejecutado menos SELL ejecutado. Si el TP ya tuvo un parcial, su total modificado incluye ese parcial; no aumenta el inventario vendible. No existe ruta para SELL independiente ni apertura short.

Cada mutación valida nuevamente autorización, revisión del journal, intención persistida, rol, cantidad, precio, transmisión, parent/OCA, conexión y cotización. Las rutas de Protobuf crudas y cancelación global siguen bloqueadas. Se puede cancelar una vez el remanente del padre; nunca se cancela el stop para cerrar. Timeouts de bracket, cancelación o cierre no permiten retransmisión automática.

Un parcial BUY reconocido solo puede cerrarse tras confirmar cancelación/finalización del padre y protección exacta del inventario ejecutado. Un parcial incierto, protección no confirmada, cambio de identidad, desconexión, ejecución ajena, posición/orden no reconocida o estado UNKNOWN suspende. Los fills ajenos quedan registrados y un Review plano no puede borrar esa incertidumbre.

## EUR desconocido y conciliación final

La excepción existente requiere aceptación protegida, identidad/proceso Paper vinculados, consultas completas, órdenes/posiciones conflictivas ausentes, journal y reservas conciliados. EUR_ROW_ABSENT conserva `UNKNOWN/null`; no representa EUR=0. Solo permite el inicio de la intención autorizada y no puede reutilizarse después del primer fill.

Después del fill se exige conciliación estricta de saldo EUR e inventario propio, comisiones y órdenes. Para concluir: moneda de comisión USD conocida, todos los fills con comisión recibida, ninguna comisión sin correlacionar/no disponible, EUR explícitamente cero, consultas completas, sin posiciones no cero y sin órdenes abiertas. Hasta entonces se conserva la reserva US$10 y no se crea una experiencia terminada. Una comisión explícita cero es un dato válido; ausencia nunca se interpreta como cero.

El journal PostgreSQL impide borrar el intento, cambiar sus parámetros, reescribir fills/comisiones, reiniciar banderas de envío o añadir un segundo diagnóstico, incluso con una autorización nueva. Las experiencias concluidas siguen siendo inmutables. No consume ni reinicia US$100/US$20 de StrategyPaper.

## Evidencia

El runner exportará `artifacts/paper-lab/execution-diagnostic.json` con observaciones del journal, también si termina suspendido. No se ha creado un informe de ejecución ficticio. Incluye cantidades solicitadas/ejecutadas, precios y referencias por fill, comisiones/monedas, margen agregado antes/después, cotizaciones/spread/slippage por lado, latencias de recepción y del broker cuando se conocen, contratos/odd lot, errores sanitizados, posiciones antes/después, órdenes finales y P&L bruto/neto.

Datos ausentes permanecen `null`. Un fill Paper pequeño no certifica ruteo o condiciones Live de odd lot. El margen es una observación agregada de cuenta; no prueba una tasa causal por operación. Hasta ejecutar el único ciclo siguen pendientes aceptación real del bracket/OCA, fills, comisiones, restricciones/tarifas efectivas y comportamiento de tamaños pequeños en esta cuenta Paper.

## Comandos existentes, solo después de aprobación local

Ejecutar desde la raíz del proyecto. No se han ejecutado estos pasos durante la preparación. `Review` es el paso que levanta la emergencia únicamente tras las comprobaciones y confirmaciones protegidas.

```powershell
.\scripts\paper-lab.ps1 -Action Revoke
.\scripts\paper-lab.ps1 -Action AuthorizeEurAbsence -Mode ExecutionDiagnostics -ExceptionMinutes 30
.\scripts\paper-lab.ps1 -Action Review -AllowAbsentEurDiagnostic
.\scripts\paper-lab.ps1 -Action Authorize -Mode ExecutionDiagnostics -RiskProfile PAPER_CONSERVATIVE -DiagnosticLossBudget 10 -MaxExperiments 1 -MaxQuantity 100 -MaxNotionalUsd 150 -MaxHoldSeconds 60 -SessionMinutes 30 -AllowAbsentEurDiagnostic
.\scripts\paper-lab.ps1 -Action Status
.\scripts\paper-lab.ps1 -Action Run
```

El orden es obligatorio: el mecanismo existente exige revocar la sesión anterior y revisar la excepción antes de crear una autorización nueva. La autorización vencida solo conserva identidad/alcance para revisión; nunca autoriza la entrada. La excepción también vence en 30 minutos, por lo que debe iniciarse Run antes de que venza cualquiera de las dos vigencias. Run vuelve a verificar identidad, cuenta, órdenes/posiciones, journal, cotización LIVE reciente y mercado abierto; un bloqueo se informa y detiene el ciclo.

Los prompts existentes exigen cuenta completa oculta y confirmaciones expresas de Paper, incertidumbre EUR, revisión de emergencia, Read-Only API desmarcado y permiso Forex. Los scripts no cambian TWS. No hay `-Continuous`, perfil experimental StrategyPaper ni segundo ciclo en estos comandos.

## Verificación

Build C# ejecutado: cero errores y advertencias. Regresiones completas: **485 pruebas aprobadas, cero fallos y cero omitidas**: C# **199/199** y Python **286/286**. Incluyen 40 pruebas nuevas para esta preparación: cinco de invariantes SQL y 35 del ciclo diagnóstico. Se habilitó PostgreSQL desechable para todas las pruebas de integración.

`Status` de solo lectura confirmó autorización vencida, emergencia activa, ExecutionDiagnostics, una operación máxima, presupuesto US$10, cantidad máxima 100 EUR, sin excepción EUR registrada y Live deshabilitado. Los hashes SHA-256 de la autorización DPAPI y del archivo de emergencia antes/después coinciden: no se renovó autorización ni se levantó emergencia.

La suite nueva cubre SDK oficial interceptado (sin red), cierre del hijo propio, parciales, cancelación, comisión tardía, plazo persistente, timeouts sin reenvío, reinicios, incertidumbres, conciliación estricta y evidencia. La integración SQL recupera un ciclo sintético con comisión tardía desde el journal real en una base desechable. Ninguna prueba envía órdenes a IBKR ni modifica la autorización/emergencia operativa.

Informes: `artifacts/test-results/execution-diagnostics-single.trx`, `artifacts/test-results/execution-diagnostics-single-python.txt` y `artifacts/paper-lab/execution-diagnostics-readiness.json`.
