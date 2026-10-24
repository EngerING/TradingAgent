# M03-A.4 — Histórico Paper fuera de horario y salud del colector

Base exacta: `develop` en `18f5b9ce22587365950137a58ad6eb0b59559f84`.
Entrega propuesta como PR **Draft**, sin merge automático, conexión con TWS,
despliegue ni órdenes. No se altera `main`, Core V3.9, Market Analyst, Vue,
React, servicios financieros, PostgreSQL ni M03-B.

## Motivación y diagnóstico real supervisado

En el host del propietario se registró la cuenta Paper terminada en 3784 con
DPAPI y asteriscos. `watch` publicó `CAPTURE_RUNNING`; el puerto local 7497
respondió a TCP; se observaron tres segmentos y 23 eventos en el último,
pero `view-0/15/60/240.json` reportaron `UNAVAILABLE` y cero barras.
Esto **no certifica** una sesión de mercado ni recepción genuina de barras.
`CAPTURE_RUNNING` se publica antes del handshake y el puerto abierto es solo
disponibilidad TCP. La causa exacta de los eventos no fue auditada en el host.

El lector M03-A detecta `MARKET_CLOSED` con el calendario de `contractDetails`;
al cerrar, cancela la cotización y espera, sin solicitar históricos. El módulo
M03-A.2 sí admite históricos estando cerrado, pero su preparador original exige
una cuenta introducida de nuevo y un permiso manual efímero. M03-A.4 conecta
estos dos mecanismos **solo para Paper y solo dentro del proceso watch**.

## Secuencia segura

1. M03-A.3 inicia `watch` con el perfil Paper DPAPI. No imprime cuenta, clave ni
   cotizaciones. Un monitor lee objetos inmutables de salud del Supervisor,
   nunca SQLite ni el socket desde otro hilo. Publica `CAPTURE_HEALTH` si cambia
   el estado o cada 60 segundos: `healthCode`, `committedEvents`, `segments`,
   `quoteAvailable`, `quality`, `observationAt` y `NO_TRADE`. La información
   representa el último evento y no sustituye la validación del consumidor.
2. Solo si `Supervisor` afirmó `MARKET_CLOSED` a partir del calendario real
   del contrato, al acabar su ciclo acotado de hasta 15 minutos se cierra el
   archive/escritor y el socket anterior. No se ejecuta backfill por reloj,
   calendario supuesto, puerto TCP abierto o `CALENDAR_UNKNOWN`.
3. Se solicita una única recuperación por día UTC, con histórico MIDPOINT
   15m/1h/4h de los últimos 6–7 días hasta el último cuarto de hora UTC
   terminado. El directorio de día se reserva exclusivamente antes del primer
   contacto. Un fallo, crash o resultado parcial **no se reintenta ese día**:
   requiere revisión y no elude pacing. No se recupera un mes completo aquí;
   bloques más antiguos exigen diseño/pacing posterior.
4. La identidad exacta proviene del perfil Paper cifrado M03-A.3. Se crea en
   memoria un par de firmas M03-A.2 ligadas al grant, intervalo y entorno;
   el secreto HMAC no se persiste. El histórico usa `client_id=19032`,
   host `127.0.0.1`, puerto 7497 y verifica de nuevo `managedAccounts`.
   La revocación DPAPI del perfil se reevalúa como máximo cada segundo y
   detiene la aprobación del histórico. El programa original de preparación
   de M03-A.2 sigue intacto para su uso explícito independiente.
5. `HistoricalStore` guarda sus páginas, el journal y el manifest en
   `%LOCALAPPDATA%\TradingAgent\market-data-host\historical\paper\AAAAMMDD`.
   Nunca sobrescribe un día anterior ni convierte datos parciales o históricos
   en cotizaciones actuales. `HISTORICAL_STATUS` imprime solo código, cantidad
   de barras, calidad y estado declarado del calendario.
6. Después del histórico, `watch` retoma el ciclo continuo con un permiso
   nuevo. `Ctrl+C` interrumpe el lector y no concede permiso financiero.

## Barreras y límites

- Solo `PAPER`; no se habilita backfill automático LIVE ni se infiere Live por
  puerto. Live conserva sus capacidades de lectura separadas en M03-A.3.
- Los comandos históricos siguen restringidos a preflight, solicitud y
  cancelación de la **petición propia de históricos**. No hay operaciones
  financieras, cancelación de órdenes ni publicación de decisiones de trading.
- La vigencia de la firma histórica es 30 minutos, recreada en memoria por
  intento. Una recuperación está acotada a cinco minutos, una solicitud
  pendiente y separación conservadora de 20 segundos entre solicitudes.
- La existencia de una cuenta Paper no garantiza permisos de mercado: IBKR
  puede devolver datos parciales, atrasados o rechazar el histórico según sus
  suscripciones, límites y la disponibilidad del contrato/calendario.
- No existe coordinación global con otros programas que usen el mismo TWS.
  No ejecutar el preparador/lector M03-A.2 independiente simultáneamente con
  este modo. El marcador diario impide duplicados entre estos procesos de
  `watch` del mismo perfil, pero no garantiza exclusión frente a terceros.
- Los directorios diarios **no se eliminan** automáticamente; diseñar retención,
  archivado y backup antes de operación prolongada. El host aún requiere una
  tarea/servicio Windows y reconexión real supervisada para funcionar 24/5.
- M03-B sigue sin integrar estos datasets ni evaluar RSI, EMA, MACD, ATR o
  tendencias. Los históricos no son autorización para una estrategia.

## Operación futura en Windows, tras revisión y aprobación

No hay que introducir de nuevo la identidad Paper. El comando anterior se
mantiene, ejecutado en una consola interactiva del propietario con TWS Paper:

```powershell
.\build\m03a3-host\run-host.ps1 -Action watch -Environment PAPER
```

El resultado `CAPTURE_RUNNING` significa únicamente que arrancó el host.
El estado real se ve en `CAPTURE_HEALTH`, `CAPTURE_CYCLE` y
`HISTORICAL_STATUS`. `HISTORICAL_UNAVAILABLE` y `HISTORICAL_PARTIAL` no se
interpretan como éxito. No se garantiza obtener barras con el mercado cerrado
hasta validar TWS auténtico, el perfil 157, permisos y su calendario.

## Pruebas y preservación

Doce pruebas deterministas offline nuevas cubren delimitación causal del
intervalo, firma temporal desde el perfil, Paper y Live segregados,
revocación, prohibición de historia sin `MARKET_CLOSED`, marcador diario,
interrupción y callback invocable, salida sin cuenta ni precio, liberación del writer antes del
histórico y bloqueo ante rechazo de identidad. Se preservan las veinte pruebas
M03-A.3 y suites anteriores de M03-A.2, Core y frontend mediante CI separadas.
El guard `build/m03a4-host/preservation.py` compara los objetos Git contra
el baseline de `develop`, comprueba exactamente cinco adiciones y tres
modificaciones autorizadas y bloquea cambios en módulos financieros y UI.
No hay prueba TWS auténtica, ni despliegue ni merge dentro de esta entrega.

Referencia del proveedor: [IBKR Campus — Historical Bars](https://ibkrcampus.com/docs/tws-api/doc/market-data-historical/historical-bars/requesting-historical-bars).
