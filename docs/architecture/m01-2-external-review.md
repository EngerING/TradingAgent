# M01.2 — paquete manual para auditoría independiente

Elegido por el usuario. No se envió código a terceros ni se ejecutaron CLIs de
otros modelos. La revisión interna no sustituye esta auditoría.

Repositorio: https://github.com/EngerING/TradingAgent
Rama: `codex/m01-2-postgres-security`.
Base obligatoria: `6fb5068e8ab77658530874856bdabb05b9af2316`.
El commit/árbol ejecutados están en identity.json del artefacto Actions y en la
entrega final. Rechazar evidencia cuyo HEAD difiera del código revisado.

Contrato para el revisor:

> Busca violaciones reproducibles, no confirmes las conclusiones del autor.
> Revisa únicamente M01.2 y su diff aditivo. Comprueba identidad inmutable,
> rol Y grant exacto, entornos separados, ausencia de autoridad financiera,
> credenciales SQL separadas, funciones privilegiadas cerradas, sesiones opacas,
> frescura y revocación concurrente, atomicidad de auditoría, migrador explícito
> e integridad del ledger. Clasifica severidad, archivo/línea, reproducción,
> consecuencia y corrección mínima. Distingue usuario remoto, credencial runtime,
> issuer confiable, administración y owner PostgreSQL. No atribuyas al código
> protección contra un owner malicioso ni autenticación Supabase implementada.

Material a revisar:

1. [Arquitectura](m01-2-postgres-security.md) y [evidencia](m01-2-postgres-security-evidence.json).
2. Contracts, SecurityDatabase, Repositories y SecurityAuditReader en
   src/TradingAgent.Identity.Persistence.
3. V001/V002, MigrationRunner y Program en src/TradingAgent.Identity.Migrations;
   comparar SHA-256 con build/identity/schema-manifest.json.
4. Los61 casos y fixture real en tests/TradingAgent.Identity.Tests, incluyendo
   pruebas de bloqueo, revocación y rollback. Verificar que las pruebas no ocultan
   privilegios del runtime usando la conexión owner para la operación bajo test.
5. Workflow nuevo, scripts de verificación y manifiestos61+21. Comparar artefactos
   TRX, logs, inventarios y isolation.json con sus contadores reales.

Reproducción segura: usar exclusivamente un cluster nuevo y desechable. En
Windows, desde la raíz, local-test.ps1 genera y detiene el suyo. En CI el service
container se destruye al terminar. No utilizar credenciales, puertos, .local,
cuentas, journals ni bases operativas. Ningún paso requiere IBKR o servicios Web.

Preguntas de auditoría:

- ¿Puede runtime emitir sesiones, modificar grants, cambiar roles o leer tablas
  privadas mediante ACL/PUBLIC, parámetros, SET ROLE, search_path o funciones?
- ¿Puede un administrador Paper activar autoridad Live latente mediante cambios
  globales, o un Administrator acceder sin grant exacto?
- ¿Una expiración durante un lock se comprueba con reloj posterior al lock?
- ¿Una revocación confirmada antes de la decisión invalida versiones y sesiones?
- ¿Fallar auditoría/commit o perder conexión deja una concesión parcial?
- ¿La referencia recuperable aparece en tablas, logs, ToString o JSON públicos?
- ¿Los nombres/contadores TRX y ensamblados demuestran todos los casos esperados?
- ¿Los729 archivos base, once migraciones, BFF, Vue y componentes financieros
  conservan sus blobs y hashes?

Registrar también límites: solo destinos desechables; sin verificador real;
owner y host confiables; decisiones temporales sin promesa de revocación de
lecturas futuras; commit ambiguo sin reintento automático; sin backups
operacionales ni certificación de PostgreSQL real. Un workflow verde no otorga
aprobación. Mantener **OFFLINE / NO_TRADE** y no iniciar M01.3.
