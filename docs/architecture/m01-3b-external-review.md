# M01.3B B1 — paquete manual de auditoría

Preparado conforme a la preferencia del usuario. No se invocaron CLIs de revisión
externa ni se envió código a revisores. Revisión adversarial interna con otro
agente de contexto separado; no equivale a auditoría independiente.

Comparar rama codex/m01-3b-hosted-supabase-pilot con base
c15c49ac07bf2eec2c72d8987c1db52b18a04795. Leer [preparación](m01-3b-preparation.md),
[ADR pendiente](m01-3b-session-renewal-adr.md), [B2](m01-3b-hosted-validation.md)
y [evidencia](m01-3b-evidence.json). Identidad final en artefacto de CI/entrega.

Contrato adversarial para revisión manual:

> Busca defectos reproducibles: agotamiento de una fuente que afecte a otra,
> reservas de cuentas/globales por tráfico rechazado, cuotas bajo concurrencia,
> logout separado, aliases de routing, cabeceras IP falsificadas, cookie obsoleta
> versus sesión activa y caída de almacenamiento/proveedor. Examina la composición
> hosted, listener loopback HTTPS, entorno explícito, certificados y configuración.
> No atribuyas al hostname prueba de entorno de desarrollo ni a GET user prueba
> universal de sesión remota activa. No conviertas pruebas simuladas en alojadas.
> Reporta severidad, archivo/línea, repro y corrección mínima. No abras servicios,
> brokers, bases operativas o proyectos reales durante la revisión del código.

Confirmar las146 regresiones intactas, nombres/ensamblados TRX y pruebas nuevas;
SDK exacto, locked restore, NuGet, Release/advertencias estrictas y límites de
aislamiento del observer. Revisar hashes de801 archivos base preservados y los
tres únicos archivos modificados de Web.Auth; once SQL, Vue, Core y APIs intactos.
El observer no es sandbox de OS y tooling queda fuera del conteo de conexiones.

Reproducir Suite A con ./build/auth-pilot/local-test.ps1: usa un cluster nuevo,
no el PostgreSQL habitual. B2 no se ejecuta con ese comando ni por push.
La confirmación del proyecto y los pendientes de infraestructura están documentados.

Para el auxiliar B2, revisar además `build/auth-pilot/HostedRunner/` y
`run-hosted.ps1`: entrada local de credenciales, cancelación/deadline, salida
redactada, cero reintentos automáticos, cluster nuevo marcado, grants solo en
base ficticia y cleanup acotado. La revisión interna del auxiliar usó tres
ciclos; se corrigieron cleanup remoto/factor propio, cancelación, resultado
inconcluso de dependencias y el estado al vencer el plazo. No se presenta como
auditoría independiente. La compilación/redactor locales no prueban MFA real.

Comprobar que los intentos fallidos no se cuenten como JWT/MFA/sesión/revocación
aprobados; HTTP400 sin cuerpo no distingue por sí solo la causa. Los booleanos
de un JWT decodificado son diagnóstico no confiable, nunca evidencia de firma.
Mantener pendiente HTTPS del BFF hasta disponer del certificado compatible,
según la elección del usuario. No solicitar passwords, TOTP, PFX o claves por chat.
Los tests B2 no se ejecutan en CI ni reciben sus secretos.
