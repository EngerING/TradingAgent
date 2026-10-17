# Forex: filtro economico y orquestacion aislada, fase 1

Alcance aprobado en chat el 2026-10-17: filtro determinista previo al diseno,
revalidacion antes del registro y persistencia separada. Sin OpenAI, IBKR,
frontend, migraciones PostgreSQL, activaciones ni cambios en R20 o `.local`.

## Modulos y orden

1. `python/trading_agent/forex_research/economics.py`: contexto y escenario
   EUR/USD explicitos; costos completos, vigencia, cantidad, riesgo, exposicion
   y margen. Calculo Decimal. Datos desconocidos o invalidos bloquean.
2. `journal.py`: SQLite exclusivo bajo
   `artifacts/research/forex-economic-phase1/`; idempotencia y eventos inmutables.
   Rechazos son diagnosticos; solo los aceptados contienen una candidata.
3. `runner.py`: preflight -> solicitud estructurada -> respuesta simulada ->
   validacion de contratos existentes -> revalidacion -> registro. Una solicitud
   no se repite tras interrupcion incierta. No existe transporte de red.

Se crea un paquete hermano: agregar archivos al investigador antiguo cambiaria
su `tool_hash`, y agregar `r20_*.py` alteraria el manifiesto R20 V2.
Los archivos existentes se conservan byte por byte.

## Contrato y limites

El contexto es un corte proporcionado por el llamador, rotulado
`SYNTHETIC_TEST_ONLY` o `CALLER_SUPPLIED_UNVERIFIED`; no autentica datos IBKR.
Equity, riesgo restante, exposicion restante, margen libre, liquidez, costos,
cantidad minima/paso y beneficio neto minimo son explicitos. No hay defaults
economicos ni conversion de UNKNOWN a cero. La cotizacion vence en 30 segundos;
la politica de costos tambien tiene vigencia propia. Las cifras son cadenas
decimales finitas, no floats ni booleanos.

El escenario contiene direccion, cantidad, entrada, stop, objetivo y referencia
a evidencia; nunca lo decide una respuesta de modelo. El filtro exige objetivo
neto positivo y superior o igual al minimo explicito. Riesgo al stop incluye
costos de ida/vuelta y una reserva monetaria de gap explicita. Esto es un filtro
de factibilidad condicional, no una estimacion de esperanza matematica ni una
garantia de perdida maxima. No calcula mantenimiento ni stress de cartera.

El bundle Forex V2 se reutiliza como hipotesis tecnica, preservando su capital
experimental inicial de USD100. La equity actual puede variar en el contexto,
sin reescribir ese contrato ni decidir automaticamente riesgo/apalancamiento.
Un sobre versionado liga bundle, contexto, escenario y evaluacion mediante hashes.
El escenario de SL/TP es un supuesto externo de investigacion: esta fase no
implementa ese bracket en un simulador y no certifica coherencia economica de las
reglas de salida. Estados de aceptacion dicen `ECONOMIC_SCENARIO_ONLY`;
backtest, expectativa, ejecucion y rentabilidad permanecen sin validar.

Solo hay un disenador simulado incorporado. Se prepara el formato que podria
consumir Sol en una integracion futura; no se importa transporte, claves ni
configuracion real de proveedores. Tokens y costo API reales son cero.
No existe excepcion `TECHNICAL_VALIDATION` en este filtro.

## Criterios y comprobacion

Unittest: costos/limites desconocidos, beneficio agotado por comisiones, LONG y
SHORT, doble cargo, capital variable, caducidad, tampering, datos de modelo no
confiables, idempotencia, concurrencia, recuperacion incierta y persistencia
despues de reabrir SQLite. Pruebas en directorios temporales, sin cuentas reales.

Desde PowerShell en la raiz, con PYTHONPATH apuntando a `python`:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'python'
python -B -m unittest discover -s python/tests -p 'test_forex_research*.py' -v
```

No ejecutar el wrapper global `verify.ps1` en esta fase: incluye build, demo y
pruebas que pueden usar servicios locales. Elegir regresiones puras verificadas.
Los hashes detectan alteraciones; no autentican al productor ni protegen contra
un administrador capaz de reescribir la base. Retirar legacy, conectar datos o
proveedores, backtesting y elegir riesgo autonomo quedan para fases posteriores.
