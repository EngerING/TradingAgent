# Implementación R20

Especificación autorizada: solicitud adjunta; contrato/auditoría en
`docs/architecture/aggressive-growth-r20.md` antes de código.

1. Auditoría Graphify/riesgo/incidente/runtime/UI y hashes previos.
2. Pruebas RED y dominio R20 causal/Decimal + baseline (agente Python).
3. Pruebas RED y journal PostgreSQL independiente (principal), migración aditiva.
4. Runner Shadow único con fuente auténtica y comandos de estado/parada (agente Python).
5. Proyección/SignalR/Sol local (principal), Vue separado (agente frontend).
6. Revisión independiente de diseño e implementación; reconciliar hallazgos.
7. Suites históricas y nuevas; build; migración local; pruebas navegador.
8. Preregistro e inicio único Shadow; verificar evidencia persistida y hashes.

Dependencias: 1 → 2/3/5-UI; 2+3 → 4; 3+4 → 5; 2–5 → 6/7; 6+7 → 8.
No órdenes Paper/Live ni grants. Parada persistente, recuperación ante escritura incierta.
