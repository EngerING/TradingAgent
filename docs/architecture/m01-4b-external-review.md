# Paquete manual de auditoría M01.4B-B1

No se ha enviado código a terceros. Revisar el diff contra
`efd13f6be8c3c720e24cd9921c2cf7f5b1db7bd5` y la identidad commit/tree de los artefactos.
El usuario seleccionó revisión externa manual. Esta es una guía de auditoría, no aprobación.

Contrato: React HTTPS mismo origen -> BFF real -> Auth HTTP fixture ES256/JWKS ->
PostgreSQL app_security desechable. OFFLINE / NO_TRADE, sin provider alojado/IBKR.

Intentar refutar estas propiedades mediante código y pruebas:
1. No hay ruta HTTP que elimine factores ni un retry destructivo implícito.
2. ReserveEnrollment precede I/O, limita memoria e impide otro login simultáneo.
3. Inventario/identidad se revalidan antes y después de enrollment/verify.
4. BFF no acepta AAL1 como sesión, UI no acredita éxito antes de GET session/SQL.
5. CSRF, Origin, cookies __Host y TLS conservan sus controles sin bypass.
6. Logout/cancelación/respuestas perdidas no dejan éxito visual ni promesa falsa de revocación.
7. QR re-encode no ejecuta SVG proveedor; secretos solo memoria de enrollment.
8. Los callbacks recuperación/invitación quedan bloqueados, sin aceptar altas o grants.
9. CI realmente usa Kestrel+HTTPfixture+SQL, valida nombres y cuenta353 casos distintos.
10. Artefactos no contienen claves privadas, JWT, cookies, contraseñas ni secretos MFA reales.
11. Toda ruta financiera/SQL/Vue y assets visuales protegidos conserva su objeto Git.

Revisar en especial Atomicidad API proveedor vs reserva de un proceso, carreras de
sesión/enrollment, verificación post-MFA, resultado de cleanup/aislamiento y validez
TLS de Chromium. Si detecta una debilidad, aportar un caso reproducible antes de
cambiar controles. No ejecutar el piloto alojado ni conectar servicios financieros.

Reproducir por los comandos de m01-4b-react-bff.md y consultar CI/pinned dependencies.
No sumar dos veces las29 unitarias React que se ejecutan en ambos workflows.
El JWT alojado histórico sigue sin causa verificada; iat_is_future es solo una hipótesis
no autenticada. No conceder skew, HS256 o éxito sintético para resolverlo.
