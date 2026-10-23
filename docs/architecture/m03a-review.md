# M03-A — paquete manual de auditoría independiente

Base `363e40985fbd3533992c70dfbe2aa05f6774ba9f`, rama
`feature/m03a-tws-market-data-only`, PR a develop. **SIN ÓRDENES / NO_TRADE**.
Esta revisión manual no se envió a terceros y no constituye aprobación independiente.

Revisar `m03a-market-data-collector.md`, `m03a-evidence.json`, el diff completo y
los artefactos del workflow M03-A. Las fuentes protegidas deben tener el mismo
objeto Git que la base; build/market-data/preservation.py rechaza modificaciones,
eliminaciones o adiciones fuera de su allowlist. La única edición previa permitida
es el dispatcher build/react-bff/preservation.mjs, para admitir esta fase sin
omitir los checks React/backend ni relajar su contenido. Los tres archivos locales
preexistentes no forman parte del PR.

Preguntas adversariales para el auditor:

1. ¿Puede algún camino emitir un opcode distinto de71/17/49/9/59/1/2/20/25?
   Revisar herencia IBKRReader, encoders y limpieza tras permiso vencido.
2. ¿Se verifica el conjunto completo de cuentas, contrato, entorno, perfil157,
   read-only externo y DataPermit antes de suscribirse? ¿Se declara la ausencia
   de prueba criptográfica del proveedor y de automatismo para read-only/Paper/Live?
3. ¿Permanece una quote visible tras GAP, desconexión, cierre, reinicio, tipo
   cambiado, fuente desconocida, lados viejos o calendario caducado?
4. ¿Una barra incompleta al solicitarse puede convertirse falsamente en definitiva
   al recibirse tarde? ¿Se excluyen conflictos, cortes de sesión y cobertura desconocida?
5. ¿Los checkpoints detectan pérdida de un prefijo conocido sin rechazar avances
   legítimos? ¿Se documenta el límite sin ancla externa y los saltos de rotación?
6. ¿Hay publicación antes de commit, una recreación silenciosa de archivos,
   un escritor concurrente, cuotas evadibles o reintentos de histórico sin pacing?
7. ¿Puede una fixture reclamar origen auténtico? ¿Están las autorizaciones y sus
   claves fuera de Git y cuentas/errores fuera de logs? ¿El entrypoint es inerte?
8. ¿Quedan intactos Core, Market Analyst, Vue, SQL, motores financieros y main?

Pruebas offline: ejecutar los tres wrappers documentados. M03-A produce un informe
de IDs distintos, fallos/omisiones y barreras en tmp/m03a/tests.json. CI instala
solo tooling público fijado por hashes y extrae el SDK oficial como oráculo,
sin ejecutar connect/run ni código de producto del SDK. No hay TWS ni DB reales.

Pendientes supervisados: disponibilidad real del endpoint, compatibilidad wire
auténtica157 y calendario recibido, identidad y read-only atestados por el host,
Paper y Live de datos por separado, entitlements, bytes reales/recepción, pacing
compartido con otros clientes, carga/disco/rotación y prueba externa de cero órdenes.
La autoridad de host y su custodia aún deben provisionarse fuera de esta entrega.
No se autorizan merge, despliegue, activación de trading ni M03-B.
