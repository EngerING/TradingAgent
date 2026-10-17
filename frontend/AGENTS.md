# Frontend de TradingAgent

Para cambios de UI/UX usa `$senior-software-engineer` y consulta Graphify antes de leer componentes. Si el índice no cubre Vue, decláralo y realiza búsquedas dirigidas.

Skills instaladas en `C:/Users/Enyer Payano/.codex/skills/`:

- `$tradingagent-ui-ux`: jerarquía, sistema visual, estados, responsive y accesibilidad.
- `$vue3-fintech-frontend`: implementación Vue/TypeScript, stores, SignalR y pruebas.
- `$trading-data-visualization`: gráficos financieros, forecast, calibración y procedencia.
- `$tradingagent-product-design`: revisión de páginas y flujos completos.

Úsalas juntas para rediseños de UI/UX; carga sólo las pertinentes para cambios acotados. No las ejecutes para tareas exclusivamente backend. Copias mantenibles en `docs/skills/`.

Conserva null/UNKNOWN, clasifica por separado Paper/Shadow/forecast y no infieras permisos de conexión/contrato. La UI no concede autorizaciones, modifica controles protegidos ni transmite órdenes. No detengas los observadores por un build de frontend. Sol renderiza contratos estructurados; jamás JavaScript del modelo.

Verifica con `npm run build`, `npm test` y `npm run test:e2e`; el navegador de pruebas usa sesión de lectura, presupuesto OpenAI cero y el backend local. No captures ni imprimas códigos de acceso en screenshots/logs. Captura escritorio/móvil y revisa teclado, contraste y desconexión.

La aplicación operacional utiliza rutas por dominio en `src/modules/`, Home en `modules/dashboard/`, navegación y temas en `src/app/`, y estado de presentación/feed en `src/stores/`. Conserva dark emerald/cyan y light, Sol drawer/bottom sheet y la separación Paper/Shadow. No vuelvas a crear una página gigante con todas las rutas ni simules botones de inicio/pausa del servidor. Arquitectura, evidencia y comandos: [trading-operational-web-app.md](../docs/architecture/trading-operational-web-app.md).
