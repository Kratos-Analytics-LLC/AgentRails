# AgentRails

Guardrails, dry-run harness and audit ledger for AI agents that place **real
orders through a broker MCP** — Robinhood, Alpaca, Interactive Brokers, or
whatever comes next.

More people are wiring Claude (or another agent) directly to a brokerage
account. Almost none of that wiring has a safety layer between "the agent
decided to buy" and "the order actually went out." AgentRails is that layer.

**What it is:** a small, dependency-free Python library.
**What it is not:** a trading strategy, a signal service, or investment
advice. It does not decide what to buy. It decides what is *allowed* to be
bought, and it writes down everything that happens.

## Why this exists

This grew out of a real weekly autopilot that deploys cash into a live
brokerage account via a scheduled Claude task. The lesson from running that
in production: the risk logic has to be a pure function you can unit-test in
milliseconds, completely separate from the code that actually talks to the
broker — and it has to be re-checked against the *final* plan right before
execution, not just trusted because the planner "should" have gotten it
right.

That separation is the whole library:

1. **You** generate a `TradePlan` however you want (valuation model,
   momentum rules, a fixed DCA schedule, whatever you trust).
2. **AgentRails** validates that plan against a `GuardrailConfig` you
   control — whitelist, per-order limits, weekly cap, sells on/off, max
   orders per run, per-position concentration, a mandatory stop-loss rule,
   and a human-approval threshold — and raises before anything reaches your
   execution code.
3. **AgentRails** logs every order (dry-run, placed, rejected, skipped) to
   an append-only CSV ledger, and offers an account-level circuit breaker
   that pauses new entries after a losing streak or a drawdown.

## Install

```bash
pip install -e .          # from a checkout, editable install
pip install -e ".[dev]"   # + pytest for running the test suite
pip install -e ".[mcp]"   # + the MCP server dependency (see below)
```

(Not yet published to PyPI — this is a v0.1 scaffold.)

## Quick example

```python
from agentrails import (
    AccountState, GuardrailConfig, GuardrailError,
    OrderSide, PlannedOrder, TradePlan, validate_plan, Ledger,
)

config = GuardrailConfig(
    account_id="00000000",
    allowed_symbols={"VOO", "QQQ"},
    allow_sells=False,
    dry_run=True,
    max_order_usd=150,
    weekly_cap_usd=100,
)

account = AccountState(account_id="00000000", buying_power=100, positions={"VOO": 400})

# This came from YOUR strategy code, not from AgentRails.
plan = TradePlan(
    account_id="00000000",
    generated_for="2026-07-16",
    dry_run=True,
    orders=[PlannedOrder("QQQ", OrderSide.BUY, 90, reason="weekly DCA")],
)

try:
    validate_plan(plan, config, account)
except GuardrailError as e:
    print(f"Blocked: {e}")
else:
    Ledger("ledger.csv").record_plan(plan, status="dry_run")
    print(f"OK: {plan.orders_total} would be deployed.")
```

See `examples/weekly_run_example.py` for the full pattern of wiring this
into a scheduled agent run against a broker MCP (read account → build plan
→ validate → dry-run or execute → log).

## Guardrail options

`GuardrailConfig` fails closed by default: `allow_sells=False` and
`dry_run=True`, so an untouched config can only ever simulate buys. The
checks `validate_plan` enforces:

- **`allowed_symbols`** — buy whitelist; buys are deny-by-default.
- **`allow_sells`** — sells are rejected unless enabled, and a sell is
  rejected if the account doesn't actually hold the position.
- **`min_order_usd` / `max_order_usd`** — per-order size bounds.
- **`max_orders_per_run`** — cap on the number of orders in one plan.
- **`reserve_cash_usd` / `weekly_cap_usd`** — net new spend can never
  exceed what's spendable once the cash reserve and weekly cap are honored.
- **`require_stop_loss_for_buys`** — every buy must carry a
  `stop_loss_price`, or it is rejected.
- **`max_position_concentration`** — rejects a plan that would push any
  single position above the configured fraction of post-trade equity.
- **`human_approval_threshold_usd`** — orders above this raise a
  `GuardrailError` flagged `requires_human_approval=True`, so your agent can
  pause and wait for a person instead of executing.
- **`shadow_mode`** — instead of raising on the first violation,
  `validate_plan` collects and returns *all* violations without stopping
  execution. Use it to observe what the guardrails *would* have blocked
  before you enforce them.

When a plan is rejected, `GuardrailError.to_feedback_prompt()` returns a
structured message you can hand back to an LLM planner so it can revise and
retry against the same constraints.

## Optional MCP gateway

`src/agentrails/mcp_server.py` is a reference [FastMCP](https://github.com/modelcontextprotocol)
server exposing a single `evaluate_and_place_trade` tool: an agent proposes
orders, AgentRails validates them, and the tool returns either a success, a
human-approval hold, or the feedback prompt above. It ships with mock demo
config and requires the optional `mcp` dependency (`pip install -e ".[mcp]"`).
It's an example of one wiring pattern, not a hosted service — nothing in it
talks to a real broker.

## What's deliberately NOT in scope

- **No broker SDK/MCP client.** Different brokers expose completely
  different tools (and some, like Robinhood's MCP, only exist inside an
  agent session, not as a standalone SDK). AgentRails stays broker-agnostic
  by never making the call itself — you call your MCP tool, AgentRails
  tells you whether you're allowed to.
- **No allocation/valuation logic.** What to buy is the one part of this
  that should stay yours, tuned to your own research and risk tolerance.
- **No hosted dashboard, no held credentials.** Nothing here talks to the
  network. Your API keys, your account, your machine.

## Legal

This is developer tooling for people automating their **own** brokerage
account with their **own** credentials. It is not investment advice, not a
signal service, and not a recommendation to buy or sell anything. If you're
building something that places trades on behalf of *other people's*
accounts for compensation, that's regulated activity in most jurisdictions
(investment adviser / broker-dealer registration in the US, equivalents
elsewhere) — talk to a securities attorney before you monetize in that
direction. Using AgentRails to automate your own account carries the same
market risk as any other automated or manual trading; nothing here
eliminates that risk, it only enforces the boundaries you configure.

## Status

v0.1 — core guardrails (whitelist, size and cash limits, stop-loss,
concentration, human-approval threshold, shadow mode), ledger, circuit
breaker and a reference MCP gateway are implemented and tested. No published
package yet, no broker-specific adapters yet (by design — see above). Built
and maintained by Kratos Analytics LLC.
