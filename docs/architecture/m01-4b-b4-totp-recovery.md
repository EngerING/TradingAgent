# M01.4B-B4 — TOTP real: recuperación sin mutaciones y registro nuevo condicionado

**Alcance:** preparar una recuperación segura del único factor Supabase Auth Dev que está `unverified`, sin retirar ese factor en este hito. **OFFLINE / NO_TRADE.**

## Evidencia inicial
El piloto real registró `JWT_USER_ACCEPTED`, HTTP 200 en contraseña, 0 factores verificados y 1 factor no verificado. El QR original no se presentó en React; el código 123456 pertenece exclusivamente al fixture.

## Implementación
1. React separa el caso de exactamente un factor `unverified` del conflicto ambiguo y muestra `/mfa/recovery`, explicando que el JWT fue admitido pero no existe sesión AAL2. La pantalla no solicita códigos, no recupera secretos y solo ofrece salida segura. No se transmite ningún factor a terceros.
2. El modo alojado permite optar por el registro de un nuevo TOTP **solo cuando el operador ejecuta el launcher con `-EnableFreshEnrollment` y confirma dos ventanas locales**. El runner exige además un opt-in exacto. El modo `LOCAL_STARTUP_CHECKS_ONLY` no puede activar enrollment.
3. Incluso con aprobación de nuevo registro, `PilotRuntime.EnrollAsync` vuelve a consultar Supabase: si existe cualquier factor anterior, verificado o no, lo rechaza sin crear, eliminar ni sustituir. Una reserva local de un solo intento impide doble registro cuando la respuesta del proveedor es incierta.
4. El proceso de QR/challenge/verify original se mantiene. El BFF exige AAL2 y revisión `app_security` para afirmar sesión; la base actual de desarrollo no tiene autorización de usuario y debe permanecer así.
5. No se implementa `DELETE`, `unenroll`, recuperación de contraseñas ni concesiones administrativas. La retirada del factor preexistente es una **decisión futura independiente**.

## Flujo de recuperación pendiente
El propietario del proyecto debe validar que el factor específico pertenece al usuario esperado y está `unverified`, después emitir autorización explícita para retirar **solo ese factor** por el canal administrativo oficial. Nunca borrar por SQL directo ni con service_role en el navegador. Una vez retirado y verificado el inventario como vacío, preparar nuevo piloto local desechable con certificado vigente. La ejecución de registro usa:

```powershell
.\build\react-bff\local-pilot.ps1 -Mode Run -RunId $newPilot -EnableFreshEnrollment
```

Usar el mismo RunId que se preparó y en el que no esté activo ningún PostgreSQL/BFF. El launcher debe solicitar dos consentimientos locales. En Chrome, el usuario introduce sus credenciales de desarrollo, escanea únicamente el QR generado en ese navegador HTTPS y introduce un código vigente de su autenticador **nunca en ChatGPT**. No reusar códigos de la demostración.

**Hasta que el factor anterior no se haya retirado tras la autorización específica, el proceso seguirá mostrando MFA setup needs review.** Este comportamiento es esperado y seguro. Pruebas de CI solo con fixture, sin conexión al Supabase alojado. PR Draft y sin merge hasta aprobación.
