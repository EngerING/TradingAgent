# M01.3B — rechazo JWT inicial y diagnósticos cerrados

2026-10-21, America/La_Paz. OFFLINE / NO_TRADE. Base de esta corrección:
`5d97406661e8b8432378bb3c5644ad23cd46b512`. No se repite el piloto alojado,
no se cambia la contraseña, no se consulta ni modifica el factor TOTP pendiente.

## Evidencia y frontera demostrada

El resultado local redactado del último intento registra SETTINGS200,
PASSWORD200 y JWKS200, `flow_stage=PASSWORD_AND_JWT`, `status=AUTH_Invalid`,
`auth_diagnostic=Unspecified`. No registra intento USER ni MFA. En el auxiliar,
`PasswordAsync → CredentialAsync → JwtVerifier.ValidateAsync` precede a
`CheckUserAsync`; descargar JWKS implica que se llegó al resolvedor de claves.
El error se sitúa desde esa resolución hasta la terminación del validador.
HTTP200 acredita una respuesta HTTP, no una clave compatible ni firma válida.

El observador anterior al validador decodificó un JWT **no confiable**: informó
ES256, typ JWT, kid presente, issuer/audience compatibles, UUID de subject y
sesión, AAL1, role authenticated, anonymous false, iat/exp numéricos,
`iat_is_future=true`, expiración futura, duración declarada no superior a 1 h,
ref ausente, nbf ausente y amr presente. No acreditó firma, correspondencia de
kid/JWKS, unicidad, rangos numéricos, estructura interna de amr ni tiempos en el
instante posterior de validación. No se conservaron JWT ni valores de claims.

**Causa histórica exacta: no demostrable con la evidencia conservada.**
La hipótesis de reloj merece comprobarse: el control explícito `issued > now`
rechaza un iat firmado futuro, pero el booleano se calculó antes y no registra
el desplazamiento ni demuestra que la firma fuera válida. No se ajusta el reloj
del sistema, no se añade skew, no se reintenta y no se modifica el proyecto.

**Defecto demostrado: pérdida de la condición de rechazo.** Los fallos de firma,
claims y formato devolvían el mismo `Invalid / Unspecified`. Dos fixtures con el
mismo payload futuro, uno firmado correctamente y otro con firma alterada,
reprodujeron esa ambigüedad antes de modificar el producto. No constituyen una
reproducción del JWT real, que no está disponible.

## Clasificación y cambio mínimo

| Área | Evidencia actual / diagnóstico nuevo |
|---|---|
| alg, typ, kid, hints remotos | El acceso a JWKS descarta un rechazo previo en esas comprobaciones para este intento; ahora tienen códigos separados. |
| JWKS y firma | HTTP200 no los valida; perfil, falta de kid, transporte y firma tienen categorías distintas. |
| issuer / audience | Comparación no confiable compatible; el resultado de IdentityModel se clasifica por excepción tipada. |
| sub / session_id / AAL / role / is_anonymous / ref | La forma no confiable no prueba aceptación; cada comprobación firmada tiene código cerrado. |
| iat / exp / nbf / lifetime | Futuro, caducidad, ausencia, formato y duración se distinguen; cero tolerancia y máximo1h intactos. |
| amr | Presencia no acredita array, longitud, método ni timestamp; categorías separadas para formato y tiempo. |

Una incompatibilidad de contrato sería un claim/header/JWKS fuera del perfil
cerrado actual. Un problema de configuración sería issuer/audience/clave no
correspondiente; un problema de reloj podría producir iat futuro, nbf futuro o
expiración. Ninguno queda confirmado por el resultado histórico. La pérdida de
diagnóstico sí es un defecto de implementación reproducido.

El cambio agrega categorías `AuthDiagnostic` y asigna la primera condición que
rechaza. Los errores de IdentityModel se traducen por tipo, sin mensaje,
valores, excepción interna ni JWT. Los errores de parseo se asocian al campo o
etapa en curso. El auxiliar ya conserva solamente `Diagnostic.ToString()`;
no necesita ampliar la respuesta HTTP del BFF ni registrar datos adicionales.
Los clientes siguen recibiendo errores genéricos. Un fallo desconocido de la
biblioteca conserva una categoría genérica cerrada; no se interpreta su texto.

No se cambian decisiones de aceptación, claves/algoritmos, orden de controles,
lecturas de reloj, límites, refresh/caché JWKS, AAL2 ni permisos SQL. El validador
continúa rechazando tokens cuyo iat esté en el futuro. El test de frontera con
reloj fijo comprueba rechazo a 29 s y aceptación a 30 s para iat+30s, sin conceder
evidencia MFA a AAL1. No se implementa una corrección especulativa de login.

## Verificación y preservación

Las 39 regresiones iniciales fallaron antes del cambio y pasaron después:
firma versus iat futuro, frontera temporal exacta, headers, hints, kid, JWKS,
firma, issuer, audience, sub/sesión, AAL/role/anonymous/ref, expiración, duración,
amr, duplicados y estructura. La revisión interna añadió 5 casos HTTP JWKS
(400/401/403/422/503), reproducidos en rojo antes de categorizarlos, conservando
AuthFailure y los diagnósticos previos. Total 44 casos nuevos. Se mantienen los
nombres de las 222 pruebas previas.
La evidencia final de ejecución y hashes se registra en
[m01-3b-jwt-diagnostic-evidence.json](m01-3b-jwt-diagnostic-evidence.json) y en los
artefactos de CI vinculados al commit/árbol exactos. El verde offline no acredita
MFA alojado ni compatibilidad del JWT histórico.

Frente a M01.3A hay 8 archivos base autorizados con cambios: los 6 ya declarados
y ahora JwtVerifier/JwksCache para diagnóstico. Por tanto 796 de 804 archivos base
deben conservarse; esos dos validadores dejan de presentarse como bytes intactos.
Se preservan 24 objetos protegidos, las 11 migraciones operativas y los proyectos
financieros, Vue, Core V3.9 y Market Analyst. El guard exige estos límites.
No se altera main. SDK/paquetes/proyectos antiguos no se actualizan.

## Auditoría manual y pendientes

Revisión adversarial interna de contexto separado; no equivale a auditoría
independiente. Se conserva la elección previa del usuario de paquete manual
externo, sin ejecutar CLIs ni enviar código a terceros. Revisar el diff desde
5d97406 y contrastar cada guard original con el nuevo, especialmente orden de
rechazo, reloj, excepciones tipadas, fallback JWKS, ausencia de valores en errores
y preservación de 222 casos. Repro offline: `./build/auth-pilot/local-test.ps1`.

No ejecutar `run-hosted.ps1` como parte de esta revisión. La próxima prueba real
requerirá autorización posterior y el auxiliar recompilado; solamente entonces
un código específico permitirá atribuir el rechazo actual. Se mantienen pendientes
JWT/MFA/sesión/revocación alojados y HTTPS BFF. El intento histórico pudo crear
una sesión Auth al aceptar la contraseña; no se confirmó logout remoto porque
la validación falló antes de obtener AccessCredential. No se afirma revocación.

Fuentes de la traducción tipada: [TokenValidationResult.Exception](https://learn.microsoft.com/en-us/dotnet/api/microsoft.identitymodel.tokens.tokenvalidationresult.exception)
y [Validators de IdentityModel 8.23.0](https://github.com/AzureAD/azure-activedirectory-identitymodel-extensions-for-dotnet/blob/8.23.0/src/Microsoft.IdentityModel.Tokens/Validators.cs).
No se cambió la versión instalada.
