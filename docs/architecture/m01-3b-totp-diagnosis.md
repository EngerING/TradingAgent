# M01.3B — diagnóstico de enrollment y recuperación confirmada

Fecha: 2026-10-21, America/La_Paz. Rama
`codex/m01-3b-hosted-supabase-pilot`; entrada de esta corrección:
`0a8337aaa4990725d1b7d00e9e837fd5740ce9dd`.
OFFLINE / NO_TRADE. El piloto alojado **no se vuelve a ejecutar** en esta entrega.
No se elimina ni modifica el factor real; la recuperación queda preparada para
una confirmación humana posterior, concreta y local.

## Dónde se interrumpió

| Paso | Evidencia disponible | Conclusión |
|---|---|---|
| Password | HTTP200 en intento3; los dos400 iniciales fueron confirmados por el usuario | Credenciales corregidas; no seguir diagnosticando password como fallo actual. |
| JWT | `password_user_and_signed_aal1_jwt=PASS` y JWKS200 en resultado local | Firma ES256 y claims AAL1 validados por código de producto. |
| User | GET user200 y comparación de subject dentro de CheckUserAsync | Identidad inicial aceptada. |
| PostgreSQL | `aal1_cannot_create_sql_session=PASS` | La identidad AAL1 no obtuvo una sesión SQL. Los fixtures de bootstrap son exclusivamente desechables. |
| Enrollment | El usuario confirmó POST factors200 y un TOTP unverified; no existe `real_totp_enrollment=PASS` | El proveedor creó el factor, pero EnrollAsync no devolvió TotpEnrollment. |
| Challenge / Verify | El código los invoca solamente después de que EnrollAsync devuelva | No se alcanzaron. No hubo entrada TOTP, AAL2 ni prueba de revocación real. |

`HostedRun.createdFactor` se asignaba después del retorno completo de
`EnrollAsync`. Si fallaba el transporte o el parser después de crear el factor,
esa referencia seguía null y el finally solo podía cerrar la sesión remota.
`PilotForm` capturaba AuthException como `AUTH_Unavailable`; no era un error del
formulario ni del autenticador. La clave HTTP compartida MFA/logout acabó204
por el logout de limpieza y no demuestra que enrollment se interpretara bien.

La respuesta original **no se conservó**, por protección de secretos. No se
conoce su tamaño, tipo de contenido ni la rama exacta que produjo Unavailable.
Por tanto, no se afirma que el cuerpo original superase64KiB, que faltase uri,
que el proveedor incumpliese el contrato o que existiese un fallo criptográfico.
El diagnóstico exacto demostrable es la frontera transporte/parser de
Enrollment, antes de Challenge; la causa concreta del incidente sigue acotada,
pero no identificada de forma única.

## Defecto reproducido y corrección

El contrato primario incluye id, type=totp y totp con secret, uri y qr_code.
El [servidor oficial](https://github.com/supabase/auth/blob/master/internal/api/mfa.go)
persiste el factor antes de devolver esos campos y genera un SVG. El cliente
conserva solo los campos tipados necesarios; nunca renderiza ese SVG.
La [referencia de enrollment](https://supabase.com/docs/reference/javascript/auth-mfa-enroll)
distingue crear el factor no verificado de verificarlo después.

El transporte aplicaba64KiB también al SVG descartado. Dos regresiones con una
respuesta válida y96KiB de contenido SVG fallaron antes de la corrección: una
con Content-Length y otra con un stream sin longitud declarada. Las pruebas
ejecutan AuthTransport y SupabaseAuthClient reales sobre un handler en memoria,
sin Supabase, sockets externos, usuario real ni secretos privados.

Ahora solo la respuesta del **POST exacto /auth/v1/factors** admite hasta256KiB.
Se verifica la longitud declarada y los bytes efectivamente recibidos. GET de
factors, token, user, JWKS y verify mantienen64KiB. Se conservan deadline3s,
profundidad16, detección de duplicados, tipo JSON, origen HTTPS cerrado y rechazo
de redirecciones. No cambian JWT/ES256, frescura MFA, emisión de sesión ni SQL.
id/type/secret/uri inválidos siguen rechazados; no se inventa uri ni se omite su
validación. Un body sobre256KiB continúa fallando sin reintento.

AuthException incorpora un diagnóstico de enum cerrado, sin mensajes del
proveedor: tamaño, Content-Type, JSON, deadline, transporte o contrato de
enrollment. El auxiliar registra la etapa causal separada de la limpieza. Así
una eventual ejecución posterior podrá distinguir estas ramas sin guardar el
cuerpo, el token, el email, el secreto, el código OTP ni una captura.

También se reprodujeron tres fallos de discovery: estado desconocido tratado
como no verificado, ID vacío y duplicado. Ahora esos casos fallan cerrados.
Solo el estado literal `unverified` puede ser candidato a recuperación.

## Recuperación preparada; todavía no ejecutada

1. Un login nuevo valida JWT AAL1 y GET user, antes de cualquier elevación MFA.
2. Debe existir un único candidato TOTP propio, no verificado, con ID exacto.
   Ambigüedad, identidad distinta, JWT inválido o AAL2 detienen la recuperación.
3. Un diálogo local muestra subject y factor concretos, explica por qué no se
   puede recuperar el secreto descartado y propone eliminar únicamente ese
   factor para reinscribir. Cancelar es la opción por defecto.
4. La confirmación exige marcar uso exclusivo de la cuenta ficticia, sin otra
   verificación MFA concurrente. No es un booleano de JSON ni una autorización
   persistente; vence en dos minutos y respeta cancelación.
5. Se revalida firma/identidad/sesión y se consulta otra vez el mismo candidato.
   El DELETE propio lleva la vigencia restante como cancelación enlazada; se
   vuelve a comprobar el plazo tras la última lectura, antes de enviarlo.
6. Se comprueba la ausencia posterior del ID. No hay selección alternativa,
   bucles de borrado ni reintentos automáticos. Solo entonces se permite una
   inscripción nueva, cuya verificación sigue exigiendo TOTP y JWT AAL2 firmado.

La API remota no ofrece DELETE condicional por estado. Los GET previos no
constituyen un bloqueo atómico frente a otros clientes; el guard del proveedor
para AAL1 tampoco prueba que su sesión mutable nunca haya cambiado. Por eso la
recuperación está restringida al piloto local, a una sesión password nueva y a
la cuenta ficticia en uso exclusivo confirmado. Si no se puede asegurar esa
condición, se cancela y se conserva el factor para revisión humana. No se
promete una garantía de concurrencia que el proveedor no documenta.

Si falla una inscripción nueva, el finally ya no elimina automáticamente un
factor. Lo deja pendiente de inspección/confirmación local y ejecuta solo logout
acotado. Nunca se retira un factor por el mero hecho de que Verify haya fallado:
su estado real puede haber cambiado. No se usan claves administrativas.

## Regresiones y preservación

32 casos nuevos: límites declarados/stream, límites intactos fuera de enrollment,
contratos inválidos/duplicados, discovery ambiguo, consentimiento denegado,
identidad/factor ajeno, JWT inválido/AAL2, múltiples candidatos, cancelación,
vigencia y cambios de estado. Una regresión adicional reprodujo DELETE después
de vencer la confirmación durante la última lectura; ahora se impide enviarlo.
Otra cambia el estado tras esa lectura y comprueba el rechazo del proveedor
simulado; no se presenta como prueba de atomicidad del cliente.

Se mantienen los44 casos B1 y las146 regresiones anteriores: el manifiesto
espera76+64+61+21=222 casos distintos, cero fallos/omitidas. Los resultados finales,
TRX, build y auditoría NuGet se registran en la evidencia de entrega.

La corrección autorizada modifica AuthTransport, SupabaseAuthClient y el tipo
AuthException junto al auxiliar, pruebas y CI de esta rama. JwtVerifier, JwksCache,
sus locks/dependencias, Core V3.9, Market Analyst, PostgreSQL operativo/migraciones,
frontend y proyectos financieros históricos permanecen intactos. Los hashes
se vuelven a contrastar con la base; no se reutiliza una afirmación obsoleta de
que toda la carpeta Supabase continúa sin cambios.
