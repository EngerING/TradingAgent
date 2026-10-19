# Core V3.9 — datos de mercado y Shadow observacional

Fecha de alcance: 2026-10-19, America/La_Paz. Base auditada por el usuario:
`542f250cd77c727832835d162596771430aa823a`, rama
`codex/core-v3-8-historical-data-integrity`, 345 pruebas aceptadas.
Rama nueva: `codex/core-v3-9-market-shadow`. Estado: **NO_TRADE**.
V3.9 requiere auditoría independiente; este documento no la aprueba.

## Diseño y amenazas expuestos antes de implementar

Paquete hermano `python/trading_agent/core_v3/market_observation/`.
Todos los cambios serán adiciones. Ningún dato real se convierte a
SyntheticDataset ni se conecta a V3.6/V3.7. No se modifica V3.1–V3.8.

| Componente nuevo | Frontera |
|---|---|
| contracts.py | Eventos originales acotados, identidad EUR/USD, quotes, calidad y políticas inmutables. |
| validation.py | Fold causal de identidad, tipo confirmado, secuencia, precios, recepción y lagunas. |
| journal.py | SQLite propia, eventos inmutables, hashchain/head y recuperación transaccional. |
| authorization.py | Verificación de aprobación externa de lectura ligada a endpoint, sesión, política y vigencia. |
| ibkr_protocol.py | Gramática estrecha de mensajes permitidos; sin SDK general. |
| ibkr_adapter.py | Perfil socket deshabilitado por defecto y transcript de pruebas identificado. |
| collector.py | Puerto simulado, persistir antes de exponer, límites y cancelación de suscripción. |
| shadow.py | Hipótesis declarativas de quotes, versión/hash, prefijos causales y observaciones posteriores. |

El transporte histórico `tws.py` hereda de EClient y bloquea mutadores. No se
importará: la nueva frontera no tendrá esa herencia ni dependencias de órdenes.
Perfil inicial de wire legacy negociado 157, comprobado contra el SDK local
10.50.2 por inspección, aún no recertificado contra TWS auténtico. Solo mensajes
START_API, hora, cuentas gestionadas para comparación opaca, detalles del
contrato, tipo de datos, suscripción de quotes y su cancelación. No hay método
genérico para enviar una operación por nombre ni acceso al SDK de órdenes.
Un perfil incompatible falla; no hace fallback al cliente histórico.

La aprobación de datos es independiente de cualquier permiso de trading.
Deshabilitado por defecto; el host confiable debe aportar evidencia externa de
sesión, modo Paper/Live, endpoint, TWS de solo lectura y permisos, ligada mediante
autenticación local a la aprobación. No hay autoridad real provisionada ni se
crea una aprobación auténtica en esta entrega. Un puerto o prefijo de cuenta no
prueba el entorno. Se comprueba además la sesión conectada y el contrato.

El perfil watchlist tickPrice no aporta timestamp de origen BID/ASK: queda null.
La recepción UTC y monotónica se conserva por lado. Callback marketDataType
confirma LIVE/FROZEN/DELAYED/DELAYED_FROZEN; solicitar LIVE no lo acredita.
UNKNOWN o ticks incompatibles nunca se presentan como LIVE. Los transcripts
y adaptadores simulados permanecen SYNTHETIC_TEST_FIXTURE, incluso al recorrer
el parser de conexión. No se inventan volúmenes, tamaños ni liquidez.

Cada evento de mercado se conserva antes de publicar una observación validada.
El journal tiene identidad de origen/entorno, clave de recepción, eventos
append-only, cadena/hash de bytes y head transaccional. Un hash no autentica
IBKR. Corrupción, conflicto y reordenamiento no se reparan silenciosamente.
Reinicio/desconexión exige laguna explícita y vacía las cachés de ambos lados.
Si falla persistencia se detiene el consumo y se cierra/cancela la suscripción.
No se promete recuperar ticks perdidos durante una desconexión ni secuencias
globales que IBKR no suministra.

Shadow usa hipótesis propias de quotes con identidad/versión y reglas cerradas;
no afirma ejecutar el AST OHLC histórico sin sus barras. Registra LONG/SHORT/
NO_TRADE hipotéticos, evento/prefijo disponible y condiciones posteriores.
Sin fills, P&L, cartera, simulación económica ni promoción. Shadow sobre datos
auténticos requiere habilitación independiente; también queda apagado.

| Amenaza | Decisión y límite |
|---|---|
| Cliente SDK expone mutadores | No importarlo; encoder con lista permitida y pruebas de cada opcode. |
| Booleano/JSON se convierte en autorización | Firma local del host, ámbito DATA_ONLY, binding, política y expiración. Host comprometido queda fuera del aislamiento Python. |
| Cuenta/puerto confundido con Paper/Live | Atestación externa separada y comparación exacta de identidad conectada. |
| Delayed/frozen o precio viejo como LIVE | Tipo confirmado por solicitud, épocas y frescura por lado. |
| Lookahead/reloj inventado | Dos relojes, source_at opcional, cutoff explícito y prefijo causal. |
| Disconexión o fallo de escritura | Commit antes de publicar; detener, reabrir y registrar GAP. |
| Duplicados/reordenamiento | Claves idempotentes, conflictos explícitos y secuencia verificada. |
| Disco/memoria ilimitados | Límites por eventos, bytes, páginas SQLite, solicitudes, duración y reconexiones. |
| Secretos en errores | Códigos fijos; identidad opaca; mensajes sensibles redactados con digest. |
| Datos reales reetiquetados como sintéticos | Tipos hermanos y ninguna dependencia/conversión hacia motores sintéticos. |

Se aplican senior-software-engineer, Graphify, TDD incremental y revisión
adversarial interna. El usuario solicitó preparar también un artefacto para
revisión externa manual. No se ejecutarán CLIs externas para ello.

Pruebas previstas: cotizaciones y relojes adversos, tipo de feed, identidad,
reconexión, duplicados/orden, fallos de commit, recuperación, cuotas, comandos
denegados, Paper/Live, causalidad Shadow, replay sin red y separación de tipos.
Wrapper nuevo sobre las barreras anteriores intactas. Las 345 regresiones
anteriores se ejecutarán junto a las nuevas. Ninguna prueba abrirá TWS/IBKR.

La conexión auténtica, las autorizaciones operativas, Paper/Live, migraciones,
servicios, frontend, modelos, V3.10, push y merge quedan fuera de esta entrega.
