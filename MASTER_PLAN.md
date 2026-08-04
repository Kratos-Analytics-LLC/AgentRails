# Plan Maestro: AgentRails como capa de seguridad para agentes

## El reenfoque

AgentRails nació resolviendo un problema de trading, pero el trading es solo el
**dominio donde apareció el problema**, no el problema. Lo valioso y reutilizable
es el patrón:

> **política declarativa → validar la acción propuesta → dry-run → registro
> auditable → circuit breaker tras fallos.**

Ese patrón no tiene nada específico de finanzas. Aplica a **cualquier acción
consecuente que tome un agente autónomo**: mandar correos, hacer compras, ejecutar
código o comandos, gastar presupuesto de API, modificar infraestructura, publicar
contenido, escribir en una base de datos. Hoy más gente cablea agentes (Claude y
otros) directamente a herramientas que ejecutan acciones irreversibles, y casi
nadie pone una capa entre "el agente decidió" y "la acción ocurrió".

**Ese hueco es AgentRails.** El objetivo no es "otro bot de trading" (eso ya
existe en otro lado) sino **la capa de seguridad y gobernanza que cualquier
agente enchufa antes de actuar** — con el trading como el primer adaptador de
referencia, no como el producto.

---

## Estado actual (2026-08-04)

Fases 0 a 7 **completadas**. `v0.1.0` está publicado en PyPI como
[`kratos-agentrails`](https://pypi.org/project/kratos-agentrails/) (el nombre
importable y el comando CLI siguen siendo `agentrails`). El núcleo genérico existe, tiene tres adaptadores de dominios
muy distintos (finanzas / gasto de API / sistemas), el gateway/ledger/breaker ya
son genéricos, las políticas son declarativas (JSON/YAML) con integración de una
línea (`@guarded`), hay CLI + CI + `SECURITY.md`, y el README vende la capa
general, no un bot.

| Fase | Estado | Qué quedó entregado |
|---|---|---|
| 0 — Endurecer lo existente | ✅ | Tests de guardrails; Ledger+CircuitBreaker cableados en el gateway MCP; secretos en `.env`/entorno. |
| 1 — Extraer el núcleo genérico | ✅ | `agentrails.core` (`Action`, `ActionPlan`, `Policy`, `PolicyContext`, `validate_actions`) + adaptador `adapters.trading`. API de trading intacta. |
| 2 — Segundo adaptador no financiero | ✅ | `adapters.api_spend` (gasto de API) completo: modelo + política + validación + ejemplo + 17 tests. |
| 3 — Documentación y posicionamiento | ✅ | README reorientado a "capa de seguridad para agentes" con trading y api_spend como ejemplos; guía "escribe tu propio adaptador" (~30 líneas). |
| 4 — Des-tradingizar el núcleo transversal | ✅ | Gateway MCP con herramienta genérica `evaluate_actions`; `Ledger` con esquema `target`/`action_type`/`cost` (`record_action`); `CircuitBreaker` con `record_failure`/`record_success`/`update_value`. Los nombres de trading (`record`, `record_trade_result`, `update_equity`) quedan como alias del adaptador. |
| 5 — Tercer adaptador: ejecución de comandos/shell | ✅ | `adapters.shell` completo: `CommandRequest`/`CommandPlan`/`ShellPolicy` + `validate_commands`. Estrena `reversible=False` (bloquea `rm -rf`, `git push --force`, `DROP TABLE`, fork bombs) y añade un guard de operadores de shell (`;`, `\|`, `` ` ``, `$( )`). Ejemplo + 19 tests. |
| 6 — Políticas declarativas + integración ergonómica | ✅ | `config.py`: `load_policy`/`save_policy`/`policy_from_dict` (JSON en stdlib, YAML opcional vía `[yaml]`, falla cerrado ante claves desconocidas). `guard.py`: `Guard` + decorador `@guarded` (breaker → validación → ledger → ejecutar). Ejemplo ejecutable + 19 tests. |
| 7 — Publicar (CI, seguridad, reporting, release) | ✅ | CI en GitHub Actions (3.10–3.13); `SECURITY.md` con el límite de confianza; CLI `agentrails report` sobre el ledger (+5 tests); `CHANGELOG.md`; `pyproject` con `[project.scripts]` y build (sdist+wheel). Publicado en PyPI como `kratos-agentrails` v0.1.0 y URLs reales del repo en `pyproject`. |

**133 tests en verde.** El paquete construye, está publicado en PyPI y expone el comando `agentrails`.

---

## El núcleo genérico

Las primitivas quedaron probadas por dos adaptadores. Esta es la traducción que
demuestra que la idea generaliza:

| Trading (adaptador) | api_spend (adaptador) | Núcleo genérico |
|---|---|---|
| símbolo | proveedor | `Action.target` |
| dólares por orden | dólares por llamada | `Action.cost` |
| lista blanca de símbolos | proveedores permitidos | `Policy.allowed_targets` |
| `max_order_usd` | `max_call_usd` | `Policy.max_cost` |
| `weekly_cap_usd` | `per_run_budget_usd` / cap diario | `Policy.budget` / `PolicyContext.available_budget` |
| `max_orders_per_run` | `max_calls_per_run` | `Policy.max_actions_per_run` |
| `max_position_concentration` | `max_provider_concentration` | `Policy.max_target_concentration` |
| umbral de aprobación | umbral de aprobación | `Policy.human_approval_threshold` |
| (n/a) | (n/a) | `allow_irreversible` — estrena la Fase 5 |

Regla del patrón: **el core hace lo genérico; el adaptador guarda lo que es
genuinamente de su dominio** (stop-loss y "no vender lo que no tienes" en trading;
allowlist de *modelos* en api_spend).

---

## Lo que sigue

El plan de las 7 fases está cerrado: `v0.1.0` quedó publicado en PyPI como
`kratos-agentrails` el 2026-08-04 (el nombre `agentrails` a secas no se pudo usar
porque PyPI lo bloqueó por similitud con un proyecto existente). Pendiente
opcional, sin urgencia:

- Tag `v0.1.0` + GitHub Release.
- Badge de CI en el README.

Ideas más allá del plan actual, si el proyecto gana tracción: cuarto adaptador
(envío de correos/mensajes), políticas por-adaptador declarativas (no solo el
`Policy` genérico), y un modo "shadow" agregable en el CLI (qué habría bloqueado).

---

## Decisión de negocio (2026-07-31)

AgentRails se mantiene 100% open-source y MIT, sin plan de monetización directa
(sin capa de pago, sin servicio hospedado). Su función es atraer clientes de
consultoría y demostrar capacidad técnica de Kratos Analytics LLC en desarrollo
de software y sistemas de agentes — el retorno es reputacional, no una línea de
ingreso del paquete en sí. Si el proyecto gana tracción real, un modelo open-core
(capa de pago opcional sobre la librería gratis) queda abierto como opción futura,
pero no es parte del plan actual.

---

## Lo que este proyecto NO es

- **No es un bot de trading.** Esa parte ya está resuelta en otro lado; aquí el
  trading es solo el ejemplo de referencia.
- **No decide qué hacer.** Decide qué está *permitido* hacer y lo deja registrado.
- **No es un servicio alojado ni guarda credenciales.** Nada habla con la red por
  su cuenta; las claves y las cuentas son del usuario, en su máquina.
- **No es un sandbox.** Hace cumplir el plan que el agente le declara; no aísla ni
  intercepta lo que un agente haga por fuera de él (ver Fase 7, `SECURITY.md`).

---

## Siguiente acción inmediata

Ninguna crítica: el plan está completo y `v0.1.0` ya está publicado en PyPI
como `kratos-agentrails`. Queda como housekeeping opcional taggear `v0.1.0` en
git y crear el GitHub Release correspondiente.

> Herramienta para automatizar acciones propias con credenciales propias. No es
> consejo de inversión ni de ningún tipo. AgentRails hace cumplir los límites que
> tú configuras; no elimina el riesgo de la acción subyacente.
