# ADR — duración normal y renovación: propuesta, no implementada

Estado: pendiente de aprobación posterior. M01.3B B1/B2 mantienen el lease de
M01.3A: máximo5min desde password, no mayor que JWT/SQL/preauth original.
No se retiene refresh token ni se activa una sesión durable. Reinicio obliga
a repetir password y MFA. Los slots SQL de tokens continúan NULL.

Una duración normal requiere una decisión independiente sobre:

- Duración absoluta/inactiva, persistencia y renovación después de MFA.
- Rotación de refresh de un solo uso y serialización por sesión, junto con
  tratamiento explícito del resultado incierto si el proveedor consumió el
  token y se perdió la respuesta. No reintentar una mutación a ciegas.
- Vault cifrado en servidor, clave externa al mismo almacén, identidad de
  servicio, rotación/versiones, protección contra rollback y borrado/revocación.
- Semántica demostrada de revocación remota, cambios de contraseña, otros
  dispositivos y propagación de claves. GET user no se promueve automáticamente
  a prueba de sesión activa y renovar no equivale a autorizar una operación.
- Recuperación, backups, DataProtection persistente, continuidad de CSRF,
  concurrencia entre instancias y observabilidad sin tokens/identidades privadas.
- Análisis de amenazas, compatibilidad alojada y presupuesto/costo operativo.

La alternativa actual es una ventana corta sin refresh, que limita exposición
pero reduce usabilidad y no demuestra revocación remota inmediata. Es adecuada
solo para este piloto de identidad sin capacidades financieras. No se añadió
ningún esquema SQL ni se cambió M01.2 para anticipar el vault.
