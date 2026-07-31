# Graph Report - .  (2026-07-24)

## Corpus Check
- Corpus is ~18,857 words - fits in a single context window. You may not need a graph.

## Summary
- 496 nodes · 1374 edges · 21 communities (19 shown, 2 thin omitted)
- Extraction: 79% EXTRACTED · 21% INFERRED · 0% AMBIGUOUS · INFERRED: 284 edges (avg confidence: 0.78)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- tests
- tests
- src/agentrails/adapters
- src/agentrails
- tests
- src/agentrails
- src/agentrails
- tests
- src/agentrails
- tests
- CHANGELOG.md
- tests
- README.md
- SECURITY.md
- MASTER_PLAN.md
- CHANGELOG.md
- .github/workflows
- SECURITY.md
- CHANGELOG.md
- src/agentrails/adapters
- pyproject.toml

## God Nodes (most connected - your core abstractions)
1. `validate_actions()` - 42 edges
2. `PolicyError` - 41 edges
3. `PlannedOrder` - 41 edges
4. `validate_plan()` - 38 edges
5. `Action` - 35 edges
6. `CircuitBreaker` - 31 edges
7. `GuardrailError` - 31 edges
8. `Policy` - 28 edges
9. `ActionPlan` - 27 edges
10. `Ledger` - 22 edges

## Surprising Connections (you probably didn't know these)
- `Scope statement: 'No es un sandbox' - enforces the declared plan, does not isolate or intercept out-of-band actions` --semantically_similar_to--> `AgentRails is a safety layer, not a sandbox`  [INFERRED] [semantically similar]
  MASTER_PLAN.md → SECURITY.md
- `Pattern: politica declarativa -> validar accion propuesta -> dry-run -> registro auditable -> circuit breaker tras fallos` --semantically_similar_to--> `Pattern: declarative policy -> validate the proposed action -> dry-run -> auditable ledger -> circuit breaker after repeated failures`  [INFERRED] [semantically similar]
  MASTER_PLAN.md → README.md
- `129 tests en verde` --semantically_similar_to--> `Status: v0.1 (129 passing tests, CI on Python 3.10-3.13, not yet published to PyPI)`  [INFERRED] [semantically similar]
  MASTER_PLAN.md → README.md
- `Design rule: the core does the generic work; the adapter keeps what's genuinely domain-specific (stop-loss / can't-sell-what-you-don't-hold in trading; model allowlist in api_spend)` --semantically_similar_to--> `Write your own adapter recipe (EmailPolicy example, ~30 lines)`  [INFERRED] [semantically similar]
  MASTER_PLAN.md → README.md
- `Legal disclaimer: tool for automating one's own actions with one's own credentials; not investment advice; enforces configured limits but does not eliminate underlying risk` --semantically_similar_to--> `Legal: trading adapter is not investment advice; placing trades for others is regulated activity`  [INFERRED] [semantically similar]
  MASTER_PLAN.md → README.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Core primitives (Action, ActionPlan, Policy, PolicyContext) generalize the trading/api_spend concepts per the master-plan mapping table** — master_plan_core_primitives_table, changelog_generic_core, readme_action, readme_policy, readme_actionplan, readme_policycontext [INFERRED 0.85]
- **Three reference adapters (trading, api_spend, shell) from very different domains ship together to prove the core is genuinely generic, not just trading with new labels** — readme_adapters_trading, readme_adapters_api_spend, readme_adapters_shell [EXTRACTED 1.00]
- **The @guarded/Guard pass chains circuit breaker, policy validation, audit ledger and execution into one governed pipeline** — readme_guard_class, readme_circuitbreaker, readme_validate_actions, readme_ledger [EXTRACTED 1.00]

## Communities (21 total, 2 thin omitted)

### Community 0 - "tests"
Cohesion: 0.09
Nodes (58): Enum, run_scenario(), order_to_action(), Trading as a reference adapter over the generic core.  This shows how the histor, GuardrailConfig, GuardrailError, RuntimeError, The core of AgentRails: a pure, deterministic second barrier between a generated (+50 more)

### Community 1 - "tests"
Cohesion: 0.11
Nodes (51): build_plan_with_your_agent(), call_paid_api(), load_spend_state(), Reference integration: putting a spend cap around an autonomous agent that calls, Stand-in for your agent's actual API call. Replace with the real client     (Ant, Where you track today's spend so a cold, scheduled run still respects the     da, The one function AgentRails deliberately does NOT provide: your agent's     own, run() (+43 more)

### Community 2 - "src/agentrails/adapters"
Cohesion: 0.10
Nodes (49): build_plan_with_your_agent(), Reference integration: putting a safety gate in front of an agent that runs shel, Stand-in for your agent's actual executor (subprocess.run, a container     exec,, The one function AgentRails deliberately does NOT provide: your agent     decide, run(), run_command(), _basename(), command_to_action() (+41 more)

### Community 3 - "src/agentrails"
Cohesion: 0.11
Nodes (31): Example script demonstrating AgentRails blocking "jailbreaks" and  structurally, _dump_yaml(), load_policy(), _parse_yaml(), policy_from_dict(), policy_to_dict(), Any, Path (+23 more)

### Community 4 - "tests"
Cohesion: 0.14
Nodes (28): main(), Reference integration: the low-friction path — a declarative policy file plus th, ActionPlan, A concrete batch of actions for one scope, one run. Produced by the     agent's, Guard, guarded(), Any, A Policy plus an optional Ledger and CircuitBreaker, wired together. (+20 more)

### Community 5 - "src/agentrails"
Cohesion: 0.10
Nodes (19): CircuitBreaker, CircuitBreakerState, Path, Scope-level circuit breaker: pause an agent after a run goes bad, independent of, Track a value over time and trip if it drops too far from its peak., Trading view of `record_result`: a non-negative P&L is a success., Trading view of `update_value`., Auto-resets after `cooldown_hours` — a pause-then-resume breaker, not a (+11 more)

### Community 6 - "src/agentrails"
Cohesion: 0.11
Nodes (20): build_plan_with_your_strategy(), call_mcp_tool(), Reference integration: how a scheduled Claude agent task (or any cron/ launchd j, Stand-in for your agent's actual MCP call. Replace with the real     thing — get, This is the one function AgentRails deliberately does NOT provide.     Your valu, run(), Ledger, LedgerEntry (+12 more)

### Community 7 - "tests"
Cohesion: 0.22
Nodes (27): Action, PolicyError, RuntimeError, Validate an ActionPlan against a Policy.      Default mode: raises PolicyError o, Raised (or collected, in shadow mode) when an action violates a policy.      `co, A structured message you can hand back to an LLM planner so it can         revis, One thing an agent wants to do.      `cost` is the magnitude on whatever axis th, validate_actions() (+19 more)

### Community 8 - "src/agentrails"
Cohesion: 0.17
Nodes (21): ArgumentParser, Namespace, build_parser(), cmd_report(), main(), _print_report(), Any, Path (+13 more)

### Community 9 - "tests"
Cohesion: 0.17
Nodes (16): evaluate_actions(), evaluate_and_place_trade(), _get_breaker(), _get_ledger(), __getattr__(), Reference MCP gateway for AgentRails.  Exposes two tools an agent can call befor, Evaluate a proposed set of agent actions against the AgentRails safety     polic, Evaluates a proposed trade plan against the AgentRails safety guardrails.     If (+8 more)

### Community 10 - "CHANGELOG.md"
Cohesion: 0.15
Nodes (19): Action, adapters.api_spend (paid-API budget), adapters.trading (broker orders), agentrails.config: load_policy/save_policy (JSON/YAML, fails closed on unknown keys), agentrails.core (generic core), Policy, PolicyContext, Design rule: the core does the generic work; the adapter keeps what's genuinely domain-specific (stop-loss / can't-sell-what-you-don't-hold in trading; model allowlist in api_spend) (+11 more)

### Community 11 - "tests"
Cohesion: 0.33
Nodes (16): account_to_context(), config_to_policy(), plan_to_action_plan(), both_pass(), both_reject(), make_account(), make_config(), make_plan() (+8 more)

### Community 12 - "README.md"
Cohesion: 0.18
Nodes (13): ActionPlan, MCP gateway tool: evaluate_actions, agentrails.mcp_server module, Rationale: agentrails.mcp_server no longer creates reports/ on disk merely by being imported; LEDGER/BREAKER built lazily on first use, still accessible via module-level __getattr__, validate_actions, Rationale: MCP gateway tested via FastMCP shim so optional 'mcp' package isn't needed in CI, ActionPlan, MCP tool: evaluate_actions (+5 more)

### Community 13 - "SECURITY.md"
Cohesion: 0.18
Nodes (11): CircuitBreaker, Rationale: CircuitBreaker base API generalized (record_failure/record_success/update_value); a failure now trips on the spot; trading aliases (record_trade_result/update_equity) retained, legacy state files still load, Rationale: CircuitBreaker.is_tripped() fails closed instead of crashing on a 'tripped' state file with no tripped_at (hand-edited or partially written); starts cooldown clock and stays paused instead of raising on datetime.fromisoformat(None), Scope statement: 'No es un sandbox' - enforces the declared plan, does not isolate or intercept out-of-band actions, CircuitBreaker (file-backed pause switch), Limit: not a sandbox - does not isolate, contain, or intercept execution once a command passes policy, Limit: only sees what it's given - a side effect not routed through AgentRails is completely unguarded, Pause switch: circuit breaker halts new actions after failure streak or drawdown, survives restarts (+3 more)

### Community 14 - "MASTER_PLAN.md"
Cohesion: 0.22
Nodes (10): Rationale: README reoriented as 'a safety layer for AI agents'; package description and keywords generalized away from trading, AgentRails project (safety layer for AI agents, reenfoque), Legal disclaimer: tool for automating one's own actions with one's own credentials; not investment advice; enforces configured limits but does not eliminate underlying risk, Scope statement: 'No es un bot de trading' - trading is only the reference example, Phase 0: Endurecer lo existente, Phase 3: Documentacion y posicionamiento, Pattern: politica declarativa -> validar accion propuesta -> dry-run -> registro auditable -> circuit breaker tras fallos, AgentRails (+2 more)

### Community 15 - "CHANGELOG.md"
Cohesion: 0.28
Nodes (9): CLI: agentrails report <ledger.csv> (--json), Ledger, Rationale: Ledger schema made generic (target/action_type/cost via record_action/record_action_plan), trading record/record_plan kept as adapter aliases, added failed/shadow statuses, 129 tests en verde, Phase 4: Des-tradingizar el nucleo transversal, CLI: agentrails report, Ledger (append-only CSV audit trail), Status: v0.1 (129 passing tests, CI on Python 3.10-3.13, not yet published to PyPI) (+1 more)

### Community 16 - ".github/workflows"
Cohesion: 0.29
Nodes (8): SECURITY.md (trust boundary documentation), pip install -e ".[dev,yaml]" (optional YAML policy loader), pytest test runner, Python version matrix (3.10-3.13), CI Workflow, Phase 7: Publicar (CI, seguridad, reporting, release), Release a PyPI v0.1.0 (python -m build, twine upload), GitHub Actions Trusted Publishing (tag v0.1.0)

### Community 17 - "SECURITY.md"
Cohesion: 0.29
Nodes (7): adapters.shell (command execution, irreversibility + shell-operator guard), Phase 5: Tercer adaptador - ejecucion de comandos/shell, agentrails.adapters.shell (CommandRequest, CommandPlan, ShellPolicy, validate_commands - destructive-command heuristic + shell-operator guard), Secrets via environment variables / .env (gitignored), Limit: garbage in, limited protection - wrong cost estimate, mislabeled reversible flag, or scope_id mismatch weakens the check, Limit: heuristics are tripwires, not guarantees - destructive-command/shell-operator detection can be defeated by unusual quoting, renamed binaries, or allowed interpreters, Limit: holds no credentials and makes no network calls - securing keys/environment is on the user

### Community 18 - "CHANGELOG.md"
Cohesion: 0.40
Nodes (6): CircuitBreakerTripped exception, agentrails.guard: Guard and @guarded decorator, Rationale: Guard/@guarded under shadow-mode no longer silently discards violations; validate_actions returns (not raises) in shadow mode, so authorize now logs would-be rejections as 'shadow' instead of ignoring them, keeping observation auditable, Phase 6: Politicas declarativas + integracion ergonomica, Guard class (authorize, run), @guarded decorator

## Ambiguous Edges - Review These
- `agentrails.core (generic core)` → `SECURITY.md (trust boundary documentation)`  [AMBIGUOUS]
  CHANGELOG.md · relation: conceptually_related_to
- `Future ideas beyond current plan: fourth adapter (email/message sending), per-adapter declarative policies, CLI 'shadow' mode (what would have been blocked)` → `Write your own adapter recipe (EmailPolicy example, ~30 lines)`  [AMBIGUOUS]
  MASTER_PLAN.md · relation: conceptually_related_to

## Knowledge Gaps
- **7 isolated node(s):** `agentrails`, `CircuitBreakerTripped exception`, `Phase 0: Endurecer lo existente`, `GitHub Actions Trusted Publishing (tag v0.1.0)`, `PolicyError (to_feedback_prompt)` (+2 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `agentrails.core (generic core)` and `SECURITY.md (trust boundary documentation)`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `Future ideas beyond current plan: fourth adapter (email/message sending), per-adapter declarative policies, CLI 'shadow' mode (what would have been blocked)` and `Write your own adapter recipe (EmailPolicy example, ~30 lines)`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `CircuitBreaker` connect `src/agentrails` to `tests`, `tests`, `src/agentrails`, `tests`?**
  _High betweenness centrality (0.081) - this node is a cross-community bridge._
- **Why does `PolicyError` connect `tests` to `tests`, `tests`, `src/agentrails/adapters`, `src/agentrails`, `tests`, `tests`, `tests`?**
  _High betweenness centrality (0.074) - this node is a cross-community bridge._
- **Why does `validate_actions()` connect `tests` to `tests`, `src/agentrails/adapters`, `src/agentrails`, `tests`, `tests`, `tests`?**
  _High betweenness centrality (0.067) - this node is a cross-community bridge._
- **Are the 26 inferred relationships involving `validate_actions()` (e.g. with `both_pass()` and `both_reject()`) actually correct?**
  _`validate_actions()` has 26 INFERRED edges - model-reasoned connections that need verification._
- **Are the 28 inferred relationships involving `PolicyError` (e.g. with `CircuitBreakerTripped` and `Guard`) actually correct?**
  _`PolicyError` has 28 INFERRED edges - model-reasoned connections that need verification._