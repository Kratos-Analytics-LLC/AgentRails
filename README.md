# AgentRails

Safety rails, a dry-run harness and an audit ledger for AI agents that take
**real, consequential actions** — placing an order, spending an API budget,
sending a message, running a command, changing infrastructure.

More people are wiring Claude (or another agent) directly to tools that *do
things*, with almost nothing between "the agent decided" and "the action
happened." AgentRails is that missing layer: a small, dependency-free Python
library that sits between an agent's proposed actions and their execution.

**What it is:** a pure, unit-testable policy engine plus an audit ledger and a
circuit breaker. **What it is not:** an agent, a strategy, or a decision-maker.
It does not decide *what* to do. It decides what is *allowed* to be done, and it
writes down everything that happens.

## The pattern

AgentRails grew out of a live trading autopilot, but trading was only the
*domain where the problem showed up*, not the problem. The reusable part is the
pattern behind every high-stakes agent action:

> **declarative policy → validate the proposed action → dry-run → auditable
> ledger → circuit breaker after repeated failures.**

Nothing about that is financial. It applies to any consequential action an
autonomous agent might take. The lesson from running one in production: the
safety logic has to be a **pure function you can unit-test in milliseconds**,
completely separate from the code that actually acts — and it has to be
re-checked against the *final* plan right before execution, not just trusted
because the planner "should" have gotten it right.

## Install

```bash
pip install -e .          # from a checkout, editable install
pip install -e ".[dev]"   # + pytest for running the test suite
pip install -e ".[mcp]"   # + the MCP server dependency (see below)
```

Requires Python 3.10+. (Not yet published to PyPI — this is a v0.1 scaffold.)

## Quick example (generic core)

The core knows nothing about trading, money, or any domain. You describe the
actions your agent wants to take, a policy says which are allowed, and a pure
validator decides:

```python
from agentrails import Action, ActionPlan, Policy, PolicyError, validate_actions

policy = Policy(
    scope_id="research-agent",
    allowed_targets={"anthropic", "openai"},  # deny-by-default
    dry_run=True,
    max_cost=1.00,             # per-action ceiling
    max_actions_per_run=20,
    budget=5.00,               # cap on the whole run
    human_approval_threshold=2.00,
)

# This came from YOUR agent, not from AgentRails.
plan = ActionPlan(
    scope_id="research-agent",
    generated_for="2026-07-18",
    dry_run=True,
    actions=[Action("call", target="anthropic", cost=0.40, reason="planning")],
)

try:
    validate_actions(plan, policy)
except PolicyError as e:
    print(f"Blocked: {e}")
    print(e.to_feedback_prompt())  # hand back to the planner to revise & retry
else:
    print("OK — allowed by policy.")
```

## The generic guardrails

`Policy` fails closed by default: an empty `allowed_targets` denies every action
and `dry_run` defaults to True, so an untouched policy can only ever simulate.
`validate_actions` enforces:

- **`allowed_targets`** — allowlist of what may be acted on (symbols, providers,
  recipients, commands, resources). Deny-by-default.
- **`min_cost` / `max_cost`** — per-action size bounds on whatever "cost" means
  in your domain (dollars, recipients, tokens, files touched).
- **`max_actions_per_run`** — cap on how many actions one plan may contain.
- **`budget`** — the whole run's total cost can't exceed this (and, via
  `PolicyContext`, can't exceed what's *actually* available right now).
- **`human_approval_threshold`** — actions above this raise a `PolicyError`
  flagged `requires_human_approval=True`, so your agent can pause for a person
  instead of executing.
- **`max_target_concentration`** — rejects a plan that pushes more than a set
  share of the run onto a single target.
- **`allow_irreversible`** — set False to block destructive/irreversible actions
  (delete, transfer, irreversible send) that carry `reversible=False`.
- **`shadow_mode`** — instead of raising on the first violation, collect and
  return *all* violations without stopping. Use it to observe what the policy
  *would* have blocked before you enforce it.

When a plan is rejected, `PolicyError.to_feedback_prompt()` returns a structured
message you can hand back to an LLM planner so it revises and retries against the
same constraints.

Two cross-cutting pieces sit alongside the validator:

- **`Ledger`** — an append-only CSV audit trail: every action ever proposed,
  dry-run, executed, rejected or skipped is a line in a file you can open in
  Excel, not a claim in a chat transcript. `agentrails report ledger.csv` turns
  it into a summary (proposed vs. blocked vs. executed, top targets); add
  `--json` for machine output.
- **`CircuitBreaker`** — a file-backed pause switch that survives process
  restarts, so a scheduled agent that starts cold still remembers it's tripped
  after a bad run.

## Reference adapters

An **adapter** maps a concrete domain onto the four core primitives
(`Action` / `ActionPlan` / `Policy` / `PolicyContext`). Three ship today, on
purpose from very different domains, to prove the core is genuinely generic and
not just trading with new labels:

### `agentrails.adapters.trading`

Caps a broker trade plan (Robinhood, Alpaca, IBKR, ...). Cost axis = dollars per
order. Its `GuardrailConfig` / `TradePlan` / `validate_plan` API is the original,
still-canonical trading validator; it also enforces two genuinely
trading-specific rules the generic core doesn't know about — a mandatory
stop-loss and "can't sell what you don't hold." See
`examples/weekly_run_example.py`.

### `agentrails.adapters.api_spend`

Caps how much an autonomous agent can spend calling paid APIs (LLM providers,
search, ...). Cost axis = dollars per call. `ApiCall` / `ApiCallPlan` /
`SpendPolicy` / `SpendState` map onto the same core, and `validate_api_spend()`
enforces provider allowlist, per-call ceiling, calls-per-run, per-run **and**
daily budget, human-approval threshold and provider concentration — all from the
generic core — plus one API-specific rule (an optional per-*model* allowlist)
kept in the adapter. See `examples/api_spend_example.py`.

### `agentrails.adapters.shell`

Gates command execution — the scariest thing people wire agents to, and the
adapter that exercises the core's **irreversibility** primitive. Here "cost" is
barely used; the star is `reversible=False`. `CommandRequest` / `CommandPlan` /
`ShellPolicy` map onto the core (executable allowlist, commands-per-run), and
`validate_commands()` adds two command-specific rules: a **destructive-command
heuristic** that flags `rm -rf`, `dd`, `git push --force`, `DROP TABLE`, fork
bombs (blocked unless `allow_destructive=True`), and a **shell-operator guard**
that rejects `;`, `|`, `` ` ``, `$( )` and redirects so a second command can't be
smuggled past the allowlist. It's a tripwire, not a sandbox — pair it with real
OS-level isolation. See `examples/shell_guard_example.py`.

## Write your own adapter

The recipe is always the same: translate your domain into core primitives, let
`validate_actions` do the generic work, and keep whatever rule is genuinely
domain-specific in your own thin validator. A whole adapter is ~30 lines:

```python
from dataclasses import dataclass, field
from agentrails import Action, ActionPlan, Policy, PolicyContext, validate_actions

@dataclass
class EmailPolicy:
    scope_id: str
    allowed_domains: set[str] = field(default_factory=set)
    max_recipients_per_send: int | None = None   # -> Policy.max_cost
    daily_recipient_cap: int | None = None        # -> PolicyContext.available_budget

def email_to_action(msg) -> Action:
    # cost axis here isn't money — it's how many people this reaches
    return Action("send", target=msg.domain, cost=len(msg.recipients))

def policy_to_core(p: EmailPolicy) -> Policy:
    return Policy(
        scope_id=p.scope_id,
        allowed_targets=set(p.allowed_domains),
        max_cost=p.max_recipients_per_send,
        budget=p.daily_recipient_cap,
    )
```

That `cost = len(recipients)` line is the whole point: "cost" is any axis your
policy limits, not just dollars. The three shipped adapters are worked examples
of this exact recipe.

## Declarative policies

Keep the rules in a config file, reviewed like code and diffable, instead of
buried in Python. JSON works out of the box; YAML needs `pip install
agentrails[yaml]`, so the library stays dependency-free by default.

```python
from agentrails import load_policy, validate_actions

policy = load_policy("policy.json")   # or policy.yaml / policy.yml
validate_actions(plan, policy)
```

```json
{ "scope_id": "research-agent", "allowed_targets": ["anthropic", "openai"],
  "dry_run": false, "max_cost": 1.0, "budget": 5.0, "human_approval_threshold": 2.0 }
```

Loading **fails closed on typos**: an unknown key (`budjet`, `max_costt`) raises
rather than being silently ignored, so a misspelled limit can't quietly leave you
unprotected. `save_policy` / `policy_to_dict` do the reverse (sets serialize as
sorted lists for stable diffs).

## One-line integration

`@guarded` wraps your executor so the whole pass — circuit breaker → policy
validation → audit ledger → execute — happens on every call, with the body only
running if the plan is allowed:

```python
from agentrails import guarded, load_policy, Ledger, CircuitBreaker

@guarded(load_policy("policy.json"), ledger=Ledger("audit.csv"), breaker=CircuitBreaker("cb.json"))
def call_apis(plan):
    ...  # only runs if the plan passes; skipped entirely in dry-run

call_apis(plan)   # raises PolicyError / CircuitBreakerTripped instead of acting
```

Prefer to stay explicit? `Guard(policy, ledger=…, breaker=…)` exposes
`authorize(plan)` (raise-or-pass) and `run(plan, execute)` (the full flow) as
plain methods. See `examples/guarded_tool_example.py` — it's runnable as-is.

## Optional MCP gateway

`src/agentrails/mcp_server.py` is a reference [FastMCP](https://github.com/modelcontextprotocol)
server exposing two tools an agent can call before it acts:

- **`evaluate_actions`** — the generic one: propose any actions (API calls,
  messages, commands, ...), AgentRails runs the full pass (circuit breaker →
  `validate_actions` → ledger) and returns a success, a human-approval hold, or
  the feedback prompt above.
- **`evaluate_and_place_trade`** — the trading adapter's tool, kept as a worked
  example of a domain-specific gateway on top of the same pass.

It ships with mock demo config and requires the optional `mcp` dependency
(`pip install -e ".[mcp]"`) only to *serve*; the module still imports without it
(a shim stands in for FastMCP) so the evaluation logic stays unit-testable. It's
an example wiring, not a hosted service — nothing in it talks to a real broker or
any other live system.

## What's deliberately NOT in scope

- **No agent, no strategy, no decision logic.** *What* to do is the one part that
  should stay yours — your valuation model, your retrieval logic, your ops
  runbook. AgentRails' job starts the moment you have a proposed plan.
- **No SDK/tool client.** AgentRails never makes the call itself: you call your
  broker MCP / API client / shell, AgentRails tells you whether you're allowed
  to. That's what keeps it domain- and vendor-agnostic.
- **No hosted dashboard, no held credentials.** Nothing here talks to the
  network. Your keys, your accounts, your machine.

## Secrets

AgentRails itself never touches the network and holds no credentials. When you
wire it to a broker, an API provider or a notifier (Telegram, etc.), keep those
keys in environment variables or a local `.env` file — never in code or in the
repo. `.env` is gitignored; copy `.env.example` to `.env` and fill in your own
values.

## Legal

This is developer tooling for people automating their **own** actions with their
**own** credentials. It enforces the boundaries *you* configure; it does not
eliminate the risk of the underlying action.

The **trading** adapter specifically: it is not investment advice, not a signal
service, and not a recommendation to buy or sell anything. If you're building
something that places trades on behalf of *other people's* accounts for
compensation, that's regulated activity in most jurisdictions (investment
adviser / broker-dealer registration in the US, equivalents elsewhere) — talk to
a securities attorney before you monetize in that direction. Automating your own
account carries the same market risk as any other trading; nothing here removes
it.

## Status

v0.1 — the generic core (allowlist, size and budget limits, human-approval
threshold, concentration, irreversibility, shadow mode), the ledger, the circuit
breaker, declarative policies (JSON/YAML), the `@guarded` wrapper, the
`agentrails report` CLI, a reference MCP gateway, and three reference adapters
(**trading**, **api_spend**, **shell**) are implemented and tested (129 passing
tests, CI on Python 3.10–3.13). See `SECURITY.md` for the trust boundary. Not yet
published to PyPI. Built and maintained by Kratos Analytics LLC.
