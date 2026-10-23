# M03-A.1 — Correcciones finales de auditoría

Estado: **OFFLINE / NO_TRADE**. PR #15 permanece Draft; sin merge ni M03-B.
Base auditada: `8faa5869d50e0f8753d2745e7d4524fd06caa4cc`.

## Causas y corrección

La proyección recalculaba la validación Core pero procesaba los diagnósticos
HISTORY_REQUEST_PLANNED y HISTORY_BATCH sin comprobar accepted. Un evento
rechazado por secuencia o reloj podía registrar un plan o publicar barras.
Ahora se coteja el veredicto recalculado con el durable antes de proyectarlo.
Un diagnóstico histórico rechazado elimina el plan y las barras de su timeframe,
conservando HISTORY_EVENT_REJECTED y los motivos Core en la calidad observable.
Un batch posterior genéricamente aceptado no puede utilizar un plan rechazado:
queda HISTORY_REQUEST_UNVERIFIED, sin barras. Consumer conserva estos motivos,
BARS_UNAVAILABLE, procedencia de fixture e incertidumbre del feed histórico.
El evento original y su rechazo siguen disponibles en el journal.

rotate() se encontraba fuera de la frontera de fallo de almacenamiento usada en
append(). Un fallo de publicación durante la rotación podía dejar el journal y
el bloqueo abiertos. La salida del supervisor centraliza ahora el cierre cuando
Health es STORAGE_FAILURE, borra latest y libera el bloqueo incluso ante una
excepción inesperada; esta última se propaga después de la limpieza. Archive.close
libera el bloqueo en finally aunque falle el cierre del journal. Además, run()
devuelve el Health definitivo: un fallo al invalidar durante una salida anticipada
no puede quedar oculto bajo STOPPED.

No se modifica el protocolo, el journal Core, permisos, cuotas, calendarios,
transporte real ni mecanismos financieros. No se introduce autoridad operativa.

## Regresiones y sensibilidad

El archivo nuevo test_m03a_audit_fixes.py añade nueve casos:

- Plan rechazado por secuencia y por discontinuidad de reloj, seguido de batch
  genéricamente aceptado; comprobación de Archive y Consumer.
- Batch rechazado por secuencia y por discontinuidad de reloj; sin barras nuevas,
  con los motivos originales conservados hasta Consumer.
- Publicación fallida en primera rotación por OSError o ContractError.
- Publicación fallida en segunda rotación, después de publicar una quote.
- Invalidación final fallida durante una salida anticipada STOPPED.
- RuntimeError inesperado en publicación: propagación, STORAGE_FAILURE y cierre.

Los casos de almacenamiento verifican el cierre de lectores, ausencia de quote
vigente, cierre del journal y del bloqueo y apertura de otro escritor cuya
aprobación de fixture se comprueba, antes de cerrar el contexto original.
Los ocho primeros casos fallaron antes de corregir el producto (8 fallos,
16.593 s); el noveno reprodujo por separado el escape inesperado (1 fallo,
0.080 s). Todos usaron fixtures, sin violaciones de las barreras offline.

La inversión temporal del control accepted detectó cuatro fallos en ocho casos.
Se restauraron los bytes exactos y se comprobó SHA-256. Este experimento demuestra
sensibilidad puntual; no es una puntuación global de mutation testing.

## Verificación reproducible

Desde la raíz, en Windows con las dependencias ya fijadas por el workflow:

```powershell
.venv/Scripts/python.exe -B python/tests/core_v39_offline_check.py
.venv/Scripts/python.exe -B python/tests/market_analyst_offline_check.py
.venv/Scripts/python.exe -B python/tests/m03a_offline_check.py
.venv/Scripts/python.exe -B build/market-data/concurrency-check.py
.venv/Scripts/python.exe -B build/market-data/verify-results.py
.venv/Scripts/python.exe -B build/market-data/preservation.py
```

verify-results exige los 63 IDs M03-A de la base auditada, al menos 72 casos
M03-A distintos, Core 394, Market Analyst 38 y tres pruebas de procesos Windows:
**507 casos**, cero fallos y cero omisiones como mínimo. Las suites históricas,
las pruebas concurrentes y el workflow no se editan. Solo sube el mínimo M03-A;
no se debilitan barreras. preservation mantiene sus dos bases anteriores y añade
una lista exacta para esta corrección frente a 8faa5869.

El workflow Windows existente conserva logs, IDs, resultados, identidad Git,
preservación y pruebas concurrentes en m03a-offline-evidence durante 14 días.
El estado de la ejecución final y sus enlaces se informan en PR #15 y la entrega;
este documento no declara por anticipado el resultado de una ejecución remota.

## Preservación y límites

[La evidencia local](m03a1-audit-fixes-evidence.json) registra hashes protegidos,
resultados y límites. La comparación SHA-256 parte de los 981 archivos rastreados
de la base y de los tres documentos/scripts preexistentes sin seguimiento.
Solo cambian tres módulos M03-A y tres archivos de comprobación; se añaden el
archivo de regresiones y estos dos documentos. No cambia ningún test anterior.

Graphify se consultó con broker paper quote market data tws (presupuesto 700):
grafo histórico de 424 nodos/1039 enlaces, 136 encontrados, 24 mostrados y 112
truncados. No contiene M03-A; sus resultados se contrastaron con las fuentes.
No se reconstruyó el grafo. La revisión adversarial con otro agente es interna;
no sustituye la auditoría independiente.

No hubo captura TWS/IBKR, conexión financiera, Supabase, proveedor IA, migración,
servicio operativo, despliegue ni integración. Las pruebas de concurrencia usan
procesos locales y SQLite temporal con fixtures. El resultado no certifica
rendimiento de mercado real, seguridad ante un propietario hostil del host ni
compatibilidad con TWS auténtico. La lectura auténtica sigue requiriendo sus
aprobaciones y preflight externos. **No se inicia M03-B.**
