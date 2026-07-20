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

## Estado actual (2026-07-18)

Fases 0 a 6 **completadas**. El núcleo genérico existe, tiene tres adaptadores de
dominios muy distintos (finanzas / gasto de API / sistemas), el
gateway/ledger/breaker ya son genéricos, las políticas son declarativas (JSON/
YAML) con integración de una línea (`@guarded`), y el README vende la capa
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

**124 tests en verde.** Cargar la política es declarativo y envolver una tool es
una línea.

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

Con el núcleo, los tres adaptadores y la ergonomía de adopción ya cerrados, solo
queda **publicar**.

### Fase 7 — Publicar: empaquetado, CI, reporting y postura de seguridad *(siguiente)*

Para una herramienta pública MIT que se vende como *seguridad*, esto es lo mínimo
creíble.

- **Release:** publicar en PyPI; GitHub Actions corriendo los tests en 3.10–3.12;
  `CHANGELOG`.
- **Reporting:** CLI `agentrails report` que lee el ledger y muestra propuesto vs.
  bloqueado vs. ejecutado, gasto en el tiempo, objetivos más bloqueados.
- **`SECURITY.md` honesto:** qué protege y qué NO. AgentRails valida el *plan
  declarado*; **no es un sandbox** y no puede detener a un agente que nunca lo
  llame. Ese límite de confianza, dicho claro, es diferenciador — no un defecto
  que ocultar.

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

Con la ergonomía de adopción cerrada (Fase 6), arrancar la **Fase 7**: publicar.
Lo mínimo creíble para una herramienta pública de *seguridad* — CI en GitHub
Actions (3.10–3.12), `SECURITY.md` honesto sobre el límite de confianza, un CLI
`agentrails report` sobre el ledger, y el release a PyPI.

> Herramienta para automatizar acciones propias con credenciales propias. No es
> consejo de inversión ni de ningún tipo. AgentRails hace cumplir los límites que
> tú configuras; no elimina el riesgo de la acción subyacente.
