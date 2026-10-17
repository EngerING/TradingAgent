# R20 V2 — configuración económica, fase 2

Estado: implementado exclusivamente en laboratorio. No habilita Shadow forward,
Paper, Live, runners ni cohortes. Continúa el plan maestro del 13/oct/2026.

## Contrato y dimensionamiento

El documento `contract_version=2` contiene capital lógico inicial USD, asignación
USD por operación, multiplicador objetivo sobre esa asignación, riesgo por precio
en %, pérdida diaria en %, máximo de posiciones y entorno solicitado. Los tres
primeros campos muestran el ejemplo pedido 100/20/20; los tres límites quedan
vacíos al entrar. No se recupera ni activa un perfil automáticamente.

Decimales como strings, finitos y positivos; multiplicador >=1, porcentajes <=100,
posiciones entero positivo. Shadow/Paper son intenciones de configuración; Live
no es un valor admitido. El capital inicial no sustituye el equity contable ni
resetea una cuenta existente: una discrepancia bloquea el escenario.

Con A la asignación, m el multiplicador y E0 el capital inicial:

- Objetivo teórico `T=A*m`; referencia ilustrativa `T/E0`.
- Equity elegible `Ee=max(0,Eecon-Cpend)`, limitado por el techo explícito si existe.
  Eecon ya incluye la contabilidad neta del núcleo; Cpend es la reserva pendiente
  separada que recibe el solver existente, no un segundo descuento de fees abiertos.
- Apalancamiento agregado actual mostrado `Nexistente/Ee`; sin Ee válido: UNKNOWN.
- Asignación admisible `Aef=min(A,Ee)`; presupuesto por precio `R=Ee*r/100`.
- Techo inicial de cantidad `min(R/d, Aef*m/P, liquidez)`; d es distancia al SL.
- Se recorre la rejilla de cantidades desde arriba, redondeada hacia abajo. La
  mayor cantidad que satisface **todas** las restricciones existentes es q*. Si
  no se puede resolver dentro del límite del solver, se rechaza.
- Restricción adicional de asignación: `margen_inicial(q)+costos_RT(q)<=Aef`.
  US$20 no representa una pérdida deseada ni una promesa de margen del bróker.
- Permanecen las restricciones de riesgo, capital libre, margen, exposición dura,
  cap agregado independiente, holgura/estrés LONG/SHORT, posiciones, reservas y
  pérdida diaria. El multiplicador solicitado nunca cambia el cap agregado.
- En el modelo actual de target 2R: `neto_TP=2*q*d-C_RT(q)>0` es necesario;
  pérdida al SL incorpora `q*d+C_RT` y los costos adicionales del escenario SL.
  Gaps/estrés se verifican aparte. No se interpreta target positivo como ventaja
  estadística o permiso de ejecución.

Se añadió `AllocationRequest` opcional al **solver existente**, sin segundo motor.
Sin ese argumento se conserva la ruta anterior y su material de hash. Los perfiles
económicos previos no se reinterpretan: el documento nuevo mantiene su propio hash,
y la previsualización produce un perfil efímero del solver sólo con políticas
completas. Nunca persiste ese perfil ni activa el ledger.

## Persistencia y permisos

`r20_v2_config.preparations` es append-only. Save crea un documento inmutable;
Validate agrega un evento que referencia exactamente ese documento. Identifica
scope, versión, autor, UTC, vigencia hasta medianoche America/Santo_Domingo,
hash del documento/contexto/evento y hash anterior. La caducidad se deriva al leer.
GUARDADO/VALIDO son estados estructurales, siempre NOT_ACTIVATED.

CAS y lock transaccional por scope serializan dos escrituras. Una requestId repetida
con el mismo contenido/autor devuelve su recibo; con otro contenido se rechaza.
La función SQL vuelve a validar valores y deniega entorno nulo. Updates/deletes y
writes directos de roles aplicativos están prohibidos. Se verifica la cadena al leer.

Guard de instalación: nombre UUID de pruebas, puerto 55432, usuario trading_test y
system_identifier 7692346685552779632. TestStore permanece intacto. Orden de setup:
contabilidad → configuración anterior → admisión → preparación; las suites antiguas
de admisión vuelven a aplicar sus grants mínimos, por lo que preparar la UI debe
ocurrir después. Esto no justifica ampliar grants ni ejecutar setup en Paper.

Endpoints en el host ConfigurationLab existente:

| Ruta `/api/r20-v2/preparation` | Autoridad / resultado |
|---|---|
| GET | Sesión de lectura o administrador; historial y estados. |
| POST `/preview` | Sesión autenticada; cálculo sin persistencia. |
| POST `/save`, `/validate` | Administrador; validación backend, CAS e idempotencia. |
| POST `/start`, `/stop`, `/switch`, `/activate` | Administrador recibe 409; lector 403. Nunca ejecutan. |

El rol procede de la sesión del servidor, no de JSON/DOM. Se mantienen origen/host
loopback, cookie HttpOnly/SameSite, CSP, límites de cuerpo, concurrencia y login.
Las credenciales por rol del laboratorio no acreditan identidad individual de
producción. Las rutas antiguas se mantienen por compatibilidad de pruebas; no
conceden autoridad al bróker. El contexto actual bloquea su activación económica.

## UI y fronteras

Se utiliza R20ConfigurationPage y se conserva R20ShadowMonitor. Los resultados
monetarios proceden del backend. Una edición invalida la vista previa anterior;
UNKNOWN es null, nunca cero/PASS. Un fallo de lectura conserva evidencia STALE y
deshabilita escrituras hasta refrescar. Se puede cargar cualquier versión histórica.

Los indicadores de seguridad identifican un snapshot histórico con fecha, no una
conexión IBKR actual. Las capturas muestran pruebas sintéticas, sin fills ni actividad
operativa. Start/Stop/Cambiar entorno permanecen deshabilitados y también denegados
en servidor. Guardar o validar Paper no cambia el entorno efectivo (null).

No se despliega sobre 5080. El build aislado se sirve en 5182 sólo durante pruebas.
La futura integración requiere identidades individuales, store/schema autorizados,
contexto contable reconciliado y política explícita de costos/margen. Fase 3 debe
resolver fuentes auténticas, recuperación, Stop/singleton, propósito técnico y
permiso Shadow separado antes de solicitar un Run supervisado.

Evidencia y uso local: [informe de fase 2](../../artifacts/aggressive-growth-r20-20261010/r20-v2-phase2-20261014/report.md).
