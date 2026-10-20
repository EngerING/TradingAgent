# M01 — auditoría de autenticación actual

Fecha: 2026-10-20, America/La_Paz. **OFFLINE / NO_TRADE**.
Alcance: inspección de fuentes, contraste documental y diseño. No se aprueba la
seguridad operativa ni se implementa Supabase. La revisión fue realizada dentro
de Codex; no sustituye una auditoría independiente.

## Estado inspeccionado y límites

Entrada: rama `codex/market-analyst-v1`, HEAD
`b1643b2ba31e1430ce3384b83bff471adb5de17a`, sincronizada según la referencia
remota local. Sin cambios tracked; únicamente estos documentos sin seguimiento:
`docs/architecture/core-v3-phase0-audit.md` y
`docs/manual/TradingAgent_Manual_Tecnico_Integral.pdf`.

Respecto a la referencia Core V3.9
`f67fa92086d10b9562df214f4e869344bf0753d8`, existen cuatro commits de Market
Analyst V1: 12 archivos añadidos, 1568 líneas, cero modificaciones/eliminaciones
de la base. Se conserva esa rama. M01 parte de su HEAD en la rama documental
`codex/m01-auth-audit-supabase`.

Todos los archivos existentes se consideran de solo lectura en M01. En particular:
Core V3.1–V3.9 completo, Market Analyst V1, RiskEngine, Execution Guard,
transportes/adaptadores IBKR, políticas, los once SQL existentes, contratos,
journals, frontend Vue y las autenticaciones actuales. No se leen secretos ni
archivos de `.local`, datos de cuentas o bases operativas. Tampoco se inspeccionan
credenciales del entorno. La imagen de login es referencia visual, no autorización
para registrar usuarios, Google OAuth, operaciones ni conexiones.

## Método y dependencias

Se consultó Graphify antes de ampliar la lectura: 424 nodos/1039 links.
Vocabulario real: `postgres token risk`. BFS depth2, presupuesto1600:168 nodos,
45 mostrados y123 truncados. Orienta a PostgresStore y pruebas de persistencia;
no cubre el dashboard, React futuro ni Supabase. Sus líneas son históricas y no
se usan como líneas actuales. `reflect --if-stale` y las lecciones se consultaron.
Las conclusiones siguientes provienen de las fuentes actuales, no de inferir
ausencias del grafo. No se reconstruyó el grafo ni se ejecutó extracción remota.

Skills consultadas en esta conversación: ingeniería senior y sistemas financieros,
Graphify, diseño de API, seguridad, frontend, TDD/pruebas, Git, Supabase y sus
prácticas PostgreSQL. Se leyó `frontend/AGENTS.md`; no se implementaron cambios UI.

Dependencias observadas:

- API ASP.NET Core → cookies/Data Protection, PostgresStore y DashboardStore,
  DashboardSource, SolChatService, PaperFeedService y broadcaster SignalR.
- DashboardSource → PostgreSQL, proyección Python mediante proceso y comprobaciones
  de existencia de evidencia local. No se invocó durante la auditoría.
- Vue/TypeScript/Pinia → API de mismo origen, cookie HttpOnly y SignalR. El estado
  `authenticated` es presentación; no prueba permisos en el servidor.
- ConfigurationLab → cookie propia, ConfigAdmin y bridge a Python/R20 de pruebas.
  Es otro host, no un endpoint de la API principal ni un rol financiero.
- Proyecto .NET actual: net9.0, definido en Directory.Build.props:3. No se cambian
  framework, paquetes, lockfiles, NuGetAudit ni configuración de compilación.

## Inventario de mecanismos

| Mecanismo | Evidencia actual | Alcance y límite |
|---|---|---|
| Bearer administrativo compartido | Program.cs:69–74,100–103 | SHA-256 y comparación constante; mínimo32 caracteres; sin usuario individual, exp ni revocación por sesión. Sirve para REST local, no autentica por sí solo el Hub Dashboard. |
| Código de dashboard separado | DashboardEndpoints.cs:45–57 | Nunca puede ser idéntico al token admin; comparación constante y límite512; identidad compartida `local-operator`, scope `dashboard-readonly`. |
| Cookie Dashboard | DashboardEndpoints.cs:24–33 | `TradingAgent.ReadOnly`, HttpOnly, Strict, Secure=SameAsRequest; ticket8h absoluto sin sliding; Data Protection persistido y DPAPI en Windows. No se abrieron las claves. |
| Login/consulta/logout | DashboardEndpoints.cs:46–60 | POST intercambia código por cookie; GET consulta scope; DELETE borra cookie del navegador. No almacén de sesiones ni validación de revocación propia. |
| Frontera HTTP | Program.cs:75–104; DashboardEndpoints.cs:35–40 | Kestrel loopback5080; IP remota loopback; Host127.0.0.1 con puerto5080/5173; Origin ausente o dos orígenes exactos. No CORS abierto. |
| Recursos de UI | Program.cs:102; DashboardEndpoints.cs:61–73 | Cookie con scope o bearer admin en REST; sin roles/ACL de aplicación por usuario o cuenta. Confirmar comandos devuelve403. |
| SignalR | DashboardRealtime.cs:7–8,26–44; DashboardEndpoints.cs:74 | Esquema Dashboard; Hub sin métodos mutadores; cierre al expirar; difusiones globales `Clients.All`. |
| ConfigLab | ConfigurationLab/Program.cs:15–63 | Host127.0.0.1:5182; tokens distintos reader/admin; cookie `TradingAgent.R20.ConfigurationLab`, Strict,60min, claves efímeras; login limitado20/15min. |
| ConfigAdmin | ConfigurationLab/Program.cs:36,64–82,109–115 | Rol firmado por servidor, no tomado del body; escribe configuración de laboratorio mediante bridge. No equivale a Administrator del producto. |
| Autoridad financiera | Program.cs:10–15; LegacyOperationRetirement.cs:8–19; Core/PaperExecutionPreparation.cs:49 | Live bloqueado; tres creaciones legacy retiradas; permisos financieros separados. La identidad de login no levanta estas barreras. |

Las rutas completas, métodos, escrituras, riesgos y tratamiento propuesto están
en [m01-auth-endpoints.csv](m01-auth-endpoints.csv). La tabla incluye rutas
expandidas de ambos hosts, transportes del Hub y recursos estáticos. No se añaden
endpoints con esta documentación. `PublicUi` admite recursos de SPA y la ruta de
sesión, pero no vuelve públicos `/policy`, `/simulation`, `/safety`, `/research`,
`/experiences`, `/api` o `/hubs`. El middleware de retiro se ejecuta después de
la frontera de autenticación: un no autenticado obtiene401; un admin obtiene410
en las tres creaciones retiradas. Las declaraciones MapPost no bastan para
afirmar que esas tres operaciones siguen disponibles.

## Hallazgos con impacto y evidencia

Severidad referida al alcance descrito; «bloqueador multiusuario» no significa
que se haya demostrado explotación remota en el laboratorio actual.

| ID | Clasificación | Archivo y línea actuales | Hallazgo / condición / recomendación |
|---|---|---|---|
| A01 | Limitación intencional; alta al exponer a varios usuarios | DashboardEndpoints.cs:56; Program.cs:100–103; DashboardStore.cs:17–58 | Principal compartido y consultas globales sin ACL. Todos los lectores ven la misma proyección configurada. Antes de admitir identidades distintas: permisos y filtros por cuenta/recurso en SQL, antes de proyectar o cachear. No es un bypass demostrado del token admin. |
| A02 | Bloqueador multiusuario, alta | DashboardRealtime.cs:37,44; DashboardEndpoints.cs:71 | Clients.All difunde datos/eventos a todos los clientes autorizados. Deben ser grupos calculados por servidor, con control por recurso, versión de permisos y expulsión al revocar. El Hub no expone métodos de órdenes. |
| A03 | Defecto de UX por inspección; media | frontend/src/api.ts:17,23; frontend/src/App.vue:21; DashboardEndpoints.cs:60 | Logout responde Ok sin JSON; el cliente siempre ejecuta response.json(). Puede rechazar antes de cambiar authenticated/limpiar datos; el stream ya fue detenido. Diseñar204 y cliente que admita body vacío, con limpieza local en finally. No se modifica aquí. |
| A04 | Limitación de sesión actual; media | DashboardEndpoints.cs:24–33,60 | Borrar cookie no invalida una copia robada del ticket; rotar el código tampoco revalida tickets ya emitidos. No se encontró ITicketStore/OnValidatePrincipal con revocación durable. Ventana máxima nominal8h. Nuevo BFF debe controlar sesiones en servidor. |
| A05 | Limitación actual; media | frontend/src/realtime.ts:71–80; stores.ts:8,30–55; App.vue:19–23 | 401/desconexión se manejan como indisponibilidad/reconexión; no hay transición central de sesión vencida ni purga completa de stores. La UI conserva datos antiguos. Separar401/403/503 y limpiar cachés de usuario; no afirmar que reintentar otorga permisos. |
| A06 | Límite intencional insuficiente en producción | DashboardEndpoints.cs:45–54 | Contador global de fallos en memoria, bloqueo de1min tras5 errores. Un cliente puede afectar a todos; reinicio borra el estado. Usar límites compartidos por origen/identidad normalizada y controles del IdP; no reemplazar por CAPTCHA sin necesidad. |
| A07 | Bloqueador de producción; alta | Program.cs:54–58,69; PostgresStore.cs:21–35 | Migración automática salvo valor exacto `false`, anterior a comprobar token admin. Ejecuta todos los SQL embebidos con la conexión de runtime. Tiene transacción, checksum y advisory lock, pero mezcla DDL y servicio. Sustituir en una fase aprobada por migrador separado y startup VerifySchema. |
| A08 | Frontera de permisos incompleta; media | DashboardEndpoints.cs:70–71; SolChat.cs:123–152; DashboardService.cs:12–14; migration007:17–18 | El acceso «solo lectura» también permite chat: inserta auditoría y puede consumir OpenAI si el host configura clave y presupuesto. No concede órdenes. Separar consulta local, escritura de auditoría y permiso/presupuesto de análisis externo; mantener externo apagado. |
| A09 | Bloqueador multiusuario; alta | DashboardService.cs:14; SolChat.cs:123; DashboardStore.cs:60–64; DashboardEndpoints.cs:71 | SolSession es común al proceso y la respuesta idempotente se busca por sesión/requestId, sin usuario ni hash del body. Además, analysisCompleted publica requestId a Clients.All. Por inspección existe un camino para reutilizar una respuesta con un ID conocido entre lectores del mismo proceso; no se explotó en runtime. En M02: claves por actor/sesión/recurso/hash, ACL, notificaciones privadas y presupuesto durable. |
| A10 | Limitación de despliegue, no bypass probado | DashboardEndpoints.cs:26,36–39; Program.cs:91–97 | HTTP local, cookie no Secure forzosa, origen ausente permitido y sin antiforgery explícito para JSON. Strict, Host y Origin exactos son controles efectivos del alcance local. Para BFF público: HTTPS, cookie Secure, antiforgery y política de origen propia; no quitar restricciones actuales para «hacer funcionar» el proxy. |
| A11 | Riesgo de exposición de errores | Program.cs:106–109 | Algunas excepciones devuelven e.Message al cliente. No se demuestra fuga de un secreto específico; nueva API debe devolver códigos fijos y correlación, conservar detalle saneado solo en servidor. |
| A12 | Funcionalidad no desarrollada | migraciones001–011; API csproj; frontend/package.json | No hay integración Supabase/JWKS/MFA, usuarios individuales ni permisos de plataforma. No convertir `authenticated`, email, rol de Supabase o preferencia Paper/Live en esos permisos. |

**Escalada administrativa:** no se encontró en las rutas inspeccionadas un camino
que convierta el código/cookie de lectura en bearer admin, ConfigAdmin o permiso
de órdenes. Hay credenciales separadas y denegaciones explícitas. El riesgo
principal de una adaptación ingenua es dar a todo JWT válido las facultades del
middleware admin actual, o reenviar desde un BFF un bearer admin compartido.
Ninguna de esas soluciones está propuesta. Los hallazgos no acreditan ausencia
universal de vulnerabilidades fuera del alcance ni integridad de un host comprometido.

## PostgreSQL existente y reutilización

Se inspeccionaron las once migraciones: estados/capital y evidencia genérica001,
retención explícita002, observaciones003, paper_lab004, diagnóstico005,
research_shadow006, dashboard_chat007, paper_exploratory008, research_kronos009,
price_risk010 y aggressive_growth011. No contienen tablas de identidad/roles de
plataforma. Los roles SQL de laboratorio son identidades de servicio, no usuarios
humanos; no deben poblar user_roles automáticamente.

Se preservan todos sus checksums, triggers de inmutabilidad, tablas, funciones y
grants. En001:20–26 se rechaza UPDATE/DELETE de evidencia;007:13–18 reutiliza
inmutabilidad y concede SELECT/INSERT a paper_lab_app. DashboardStore restringe
host/puerto/usuario SQL y usa transacción read-only para snapshot (:12–21), pero
eso no implementa autorización entre usuarios. No se comprobó pg_roles, permisos
efectivos, estado de triggers ni datos de una instancia viva: no hubo conexión DB.

## Pruebas existentes y estado de ejecución

Inspeccionadas, no ejecutadas:

- DashboardTests.cs:80–81 prueba helpers de Host/Origin y límites de cookie;
  :103–124 prueba denegación de mutaciones, tokens separados y cookies;
  :126–138 prueba presupuesto cero/idempotencia y SignalR autenticado.
  Las pruebas HTTP marcadas DatabaseFact necesitan DB desechable y pueden
  arrancar Program/hosted services: no se invocan en M01.
- LegacyRetirementTests.cs:16–54 prueba el middleware con host en memoria,
  incluyendo410 de creaciones y continuidad de settlement/stop. No es prueba
  de permisos completa ni autorización financiera para esas rutas.
- frontend/src/__tests__/dashboard.test.ts:14–43 cubre contratos, escape HTML,
  comandos bloqueados,401 y secuencias. realtime-lifecycle.test.ts cubre
  desconexión/reanudación. No se encontró cobertura dedicada del logout con body
  vacío, invalidación de sesiones copiadas, MFA, JWT/JWKS o usuarios cruzados.
- Los E2E r20-configuration/phase2/phase3/readiness cubren lector/admin, origen
  y ausencia de rutas de ejecución del laboratorio. No se arrancó ese host.

M01 no ejecuta dotnet test/build, npm test/build/E2E ni wrappers cuantitativos:
no cambió código y no se inicia el host, sus migraciones, proyección Python,
PaperFeed ni proveedores. Los468 resultados de Market Analyst son evidencia
histórica de la entrega anterior; no son nuevas pruebas de Supabase ni de M01.
Sí se realizan comprobaciones estáticas de Git, hashes, enlaces y cobertura de
la matriz. Cualquier reproducción aislada adicional se identifica en la evidencia.

Reproducción aislada ejecutada con Node: `new Response(null,{status:200}).json()`
rechaza con SyntaxError. No realiza HTTP, no arranca el frontend y solo confirma
la precondición del parser de A03; el logout completo no se probó en navegador.

## Entrega y decisión pendiente

La propuesta completa está en [m01-supabase-auth-design.md](m01-supabase-auth-design.md):
diagrama de identidad y autorización, JWT/JWKS, BFF, esquema adicional PostgreSQL,
roles SQL, React, amenazas, pruebas, transición y reversión. El inventario
[m01-auth-audit-evidence.json](m01-auth-audit-evidence.json) registra los hashes y
las comprobaciones, diferenciando propuesta de ejecución real.

**No se reemplaza la autenticación ni se migra PostgreSQL. No se crean proyectos,
usuarios ni secretos. No hay push, merge, servicios, PaperAuto, Live, Google,
Telegram ni conexión IBKR.** Se entrega diseño para revisión y se espera la
aprobación explícita del usuario antes de implementar cualquiera de esas capas.
