# M01.3A — paquete manual de auditoría independiente

Preparado según la preferencia de revisión manual del usuario. No se ejecutaron
CLIs externas ni se envió código a terceros. La revisión interna tuvo contexto
separado y tres ciclos; no equivale a la auditoría independiente.

Base: f4130ea9671da9b0990ac62bff40a9aa83f60e4d. Rama: codex/m01-3-supabase-auth.
Repositorio: https://github.com/EngerING/TradingAgent . El commit/árbol exactos
están en identity.json del artefacto y en la entrega final; verificar concordancia.

Contrato para el revisor:

> Busca fallos reproducibles y supuestos falsos. No confirmes conclusiones del
> autor. Examina firma y claims JWT, bounded JWKS, URL/pooling/cookies HTTP,
> bindings MFA, timestamps firmados, preauth versus sesión, concurrent logout,
> cancelación y respuesta demorada, SQL grants exactos, CSRF, errores y secretos.
> Clasifica severidad, archivo/línea, repro, impacto y corrección mínima.
> Diferencia usuario remoto, sesión robada, host/verificador confiable y owner SQL.
> No atribuyas a GET user prueba de auth.sessions ni a tests simulados pruebas
> contra Supabase alojado. No ejecutes servicios operativos o acciones financieras.

Leer [arquitectura](m01-3-supabase-auth.md), [ADR](m01-3-session-adr.md),
[evidencia](m01-3-supabase-auth-evidence.json) y [piloto pendiente](m01-3-development-pilot.md).
Después revisar Identity.Supabase, Web.Auth, tests Auth y build/auth/workflow.
Comparar diff completo contra la base: todos los764 archivos anteriores deben
conservar sus blobs. Las migraciones y contratos M01.2 no cambian.

Reproducir exclusivamente con ./build/auth/local-test.ps1 o el service efímero de
CI. El fixture enlazado de M01.2 sigue comprobando marcador antes de DDL. No usar
.local, credenciales reales ni PostgreSQL habitual. Validar64+61+21 resultados,
cero fallos/omitidos, nombres de casos y ensamblados, versiones, NuGet e identidad.
El observer cuenta solo sockets del ciclo de tests; tooling y descargas se excluyen.

Preguntas específicas:

- ¿Puede AAL1 o un JWT anterior de otro usuario/session_id crear sesión SQL?
- ¿Puede un challenge consumido o ajeno reutilizarse, o una inscripción huérfana
  bloquear acceso sin ruta segura de recuperación? ¿Se preserva MFA verificado?
- ¿Logout con solo preauth revoca una sesión completada cuya cookie aún no llegó?
  ¿El puente de cancelación puede vencer antes que la sesión del piloto?
- ¿Las cuotas por cuenta siguen existiendo al cambiar cookies? Mutar ese control
  debe hacer fallar el test antes de que el límite global lo oculte.
- ¿Tokens, claves o secretos TOTP aparecen en logs, ToString, cookies, SQL o TRX?
  Distinguir el secreto de enrolamiento que necesariamente recibe su propio usuario.
- ¿Puede un rol del proveedor conceder autoridad interna o financiera, o un
  Administrator leer un recurso sin grant exacto Paper/Live?
- ¿Se informa503 ante dependencia caída y se elimina capacidad local al cerrar?
- ¿Está cerrado el host a Supabase real y a acciones sensibles no demostradas?
- ¿La CI conserva workflows/82 pruebas anteriores, sin reducir umbrales o guards?

Pendientes explícitos: sesión remota activa no demostrada; Supabase real no
probado; refresh no soportado; memoria se pierde al reiniciar; cuotas de un proceso;
no sandbox contra host/owner; commit ambiguo sin reintento; ningún despliegue o
conexión operativa. Aprobar M01.3A no debe autorizar M01.3B ni M01.4 automáticamente.
