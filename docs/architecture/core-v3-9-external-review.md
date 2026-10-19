# Core V3.9 — paquete de revisión externa manual

Solicitado por el usuario el2026-10-19. No se ejecutó una revisión externa ni se
envió código a terceros. Este documento es un encargo concreto para revisión
manual. Estado: **NO_TRADE; NO APROBADO INDEPENDIENTEMENTE**.

Base auditada:542f250cd77c727832835d162596771430aa823a.
Rama:codex/core-v3-9-market-shadow. Implementación revisable:64720cb más el
commit documental de cierre informado al entregar. Consulte también el
[informe completo](core-v3-9-market-data-shadow.md) y el
[inventario](core-v3-9-backend-inventory.json).

Evidencia final registrada:394 pruebas pasadas en266.313s (345 anteriores+49
nuevas), exit_code=0 y ambos contadores offline0. El inventario contiene473
archivos; los456 hashes backend base coinciden. V3.9 sigue pendiente de su
auditoría. La ejecución de pruebas no constituye aprobación de conexión.

Al entregar se prepara también un ZIP local con este documento, informe,
inventario, los17 archivos nuevos de código/tests, diff aplicable sobre la base
y un manifiesto de SHA-256. Se informa su ruta en el cierre. No incluye código
histórico, credenciales, bases, documentos untracked ni datos reales. Para
ejecutar la suite se necesita un checkout de la base más el diff y el entorno
documentado; el ZIP no instala dependencias.

## Material y límites

Revisar solamente el diff aditivo de V3.9:

```powershell
git diff --name-status 542f250..HEAD
git diff 542f250..HEAD -- python/trading_agent/core_v3/market_observation python/tests/test_core_v39_*.py python/tests/core_v39_offline_check.py
.venv/Scripts/python.exe -B python/tests/core_v39_offline_check.py 'test_core_v39_*.py'
.venv/Scripts/python.exe -B python/tests/core_v39_offline_check.py
```

No acceder a.local, credenciales, TWS/IB Gateway ni iniciar servicios, modelos,
órdenes o pruebas con conexiones reales. El wrapper impide sockets, procesos,
almacenamiento privado y SQLite fuera del temporal. No flexibilizarlo para la
revisión. Las claves HMAC y cuentas de los tests son fixtures públicos.

## Preguntas de auditoría

1. ¿Puede un opcode fuera de1,2,9,17,49,59,71 salir del lector? Revisar encoder,
   accesibilidad del adaptador, imports transitivos y comparación offline SDK.
   Opcode2 cancela datos, no órdenes. ¿El perfil157 y sus layouts rechazan lo
   desconocido sin fallback? Su compatibilidad real sigue sin recertificar.
2. ¿La autorización externa liga scope, endpoint, clientId, sesión, entorno,
   política y cuentas? Revisar default apagado, expiración durante recv,
   revocación, cambio de cuenta y limpieza sin abrir nuevas suscripciones.
   HMAC verifica al host poseedor de la clave, no al proveedor ni a un cliente
   JSON. No hay autoridad auténtica provisionada en este repositorio.
3. ¿Se conserva el frame rechazado antes de poder publicar una quote? Revisar
   base64/hash/longitud, redacción de errores/cuentas, desconexiones y permisos.
   Un cuerpo que excede el máximo no se lee: el informe declara ese límite.
4. ¿Se mezclan tipos, épocas, sesiones o relojes? Revisar ausencia de source_at,
   edadesUTC+monotónicas, deriva acumulada, precios/crosses/minTick, cambio de
   tipo y errores de farm aunque TCP no se cierre. ¿Algún delayed/frozen se
   presenta como LIVE?
5. ¿COMMIT precede publicación? Revisar idempotencia/conflictos, rollback,
   reapertura, triggers, hashchain/head, corrupción, cuotas, sidecars e identidad
   del archivo. ¿Un SQLite ajeno se modifica antes de rechazarse? La detección
   de restaurar una copia válida necesita un checkpoint externo conservado.
6. ¿El reinicio tras secuencias7,6 crea un GAP sin colisionar? ¿Hay algún camino
   de recuperación que conserve una pareja de una conexión anterior?
7. ¿Shadow usa solo el prefijo disponible y genera en un instante posterior a
   recepción/validación? Revisar edades recalculadas en generated_at, condiciones
   posteriores separadas, incertidumbre fuente y scope propio sobre datos reales.
   No se ejecuta el AST OHLC ni se calculan fills o rentabilidad.
8. ¿Los límites son verificables y los fallos explícitos? Se promete acotación
   de estructuras/bytes, no RSS, HFT ni cuota física portable. Revisar presupuesto
   de cancelación, timeout, bucles de reconexión y journal lleno.
9. ¿Se preservaron V3.1–V3.8 y las345 regresiones? Contrastar diffM/D/R vacío,
   hashes de456 archivos backend y los dos documentos originales untracked.
10. ¿Existe un camino hacia SyntheticDataset, órdenes, dinero operativo o
    afirmaciones económicas/estadísticas? Todos los resultados raíz deben seguir
    NO_TRADE y sin autoridad. No autorizar automáticamente V3.10 ni capturas reales.

## Reproducciones ya incorporadas

La revisión interna encontró seis casos y produjo tests dedicados: deriva
monotónica acumulada; frame inválido sin custodia; mutación de SQLite ajeno;
expiración durante recepción; reinicio después de7,6; y quote vieja al adelantar
generated_at. Compruébense las regresiones en test_core_v39_security.py y
test_core_v39_transport.py, además de las suites de journal/quotes/Shadow.
El experimento de mutación de LIVE/FROZEN detectó el cambio y se restauró.
Esto no reemplaza su revisión independiente.

Entregar hallazgos con gravedad, ruta/línea, entrada reproducible, garantía
afectada, resultado observado/esperado y corrección verificable. Separar defectos
de implementación de limitaciones ya declaradas. Resolver hallazgos no constituye
autorización para activar datos reales, Paper o Live.
