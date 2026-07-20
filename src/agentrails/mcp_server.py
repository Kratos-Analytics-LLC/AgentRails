"""Reference MCP gateway for AgentRails.

Exposes two tools an agent can call before it acts:

    evaluate_actions          — GENERIC: evaluate any proposed agent actions
                                (API calls, messages, commands, ...) against a
                                domain-agnostic safety Policy. Built on
                                `agentrails.core.validate_actions`.
    evaluate_and_place_trade  — TRADING: the reference adapter tool, kept as a
                                worked example of a domain-specific gateway on
                                top of the same safety pass.

Both run the same three-step pass:

    1. Circuit breaker — if the scope is paused after a bad run, refuse.
    2. validate — enforce every configured guardrail / policy limit.
    3. Ledger — record what happened (rejected / dry-run / placed / skipped) so
       there is an auditable trail, not just a claim in a chat transcript.

This is an EXAMPLE wiring, not a hosted service. It uses mock demo config and
never talks to a real broker or any other live system.
"""

from __future__ import annotations

from typing import List

try:
    from mcp.server.fastmcp import FastMCP

    _HAS_MCP = True
except ImportError:
    _HAS_MCP = False

    class FastMCP:  # minimal shim used only when the optional `mcp` dep is absent
        """Fallback so this module still imports (and its evaluation logic can be
        unit-tested) without the optional `mcp` package. Actually serving the
        gateway requires `pip install agentrails[mcp]`."""

        def __init__(self, name: str):
            self.name = name

        def tool(self, *args, **kwargs):
            def _decorator(fn):
                return fn

            return _decorator

        def run(self):
            raise SystemExit(
                "The 'mcp' package is required to run the gateway. "
                "Install it with `pip install agentrails[mcp]`."
            )


from agentrails.circuit_breaker import CircuitBreaker
from agentrails.core import Action, ActionPlan, Policy, PolicyError, validate_actions
from agentrails.guardrails import GuardrailConfig, GuardrailError, validate_plan
from agentrails.ledger import Ledger
from agentrails.models import AccountState, OrderSide, PlannedOrder, TradePlan

# Initialize FastMCP Server
mcp = FastMCP("AgentRails_Gateway")

# --------------------------------------------------------------------------- #
# Audit trail + scope-level circuit breaker.
# Both write under reports/ (gitignored). In production point these at durable
# storage outside the instance.
# --------------------------------------------------------------------------- #
LEDGER = Ledger("reports/mcp_ledger.csv")
BREAKER = CircuitBreaker(
    "reports/mcp_circuit_breaker.json",
    max_consecutive_failures=5,
    max_drawdown_pct=0.35,
    cooldown_hours=4.0,
)


# --------------------------------------------------------------------------- #
# GENERIC tool — the point of AgentRails: guard ANY agent action.
# --------------------------------------------------------------------------- #

# Demo policy. Fails closed and, unlike the trading demo, blocks irreversible
# actions by default so a destructive command/delete is denied unless explicitly
# allowed. Replace with a policy loaded from your own config.
DEMO_POLICY = Policy(
    scope_id="agent-session",
    allowed_targets={"anthropic", "openai", "search-api"},
    dry_run=True,
    max_cost=1.00,  # hard per-action ceiling
    # Approval band sits *below* the ceiling: actions over 0.50 (but <= 1.00) are
    # allowed only with human sign-off. Keep this < max_cost or the band is empty.
    human_approval_threshold=0.50,
    max_actions_per_run=20,
    budget=5.00,
    # max_target_concentration is intentionally left off here: with a single
    # target it always trips (100% > any share), which would reject the simplest
    # plans. Concentration shines with multi-target plans — see the adapters.
    allow_irreversible=False,
)


@mcp.tool()
def evaluate_actions(actions: List[dict]) -> str:
    """Evaluate a proposed set of agent actions against the AgentRails safety
    policy. Domain-agnostic: the actions can be API calls, messages, commands,
    infra changes — anything with a target and a cost. If the plan passes it
    would be executed by YOUR code (simulated here); if it fails it returns a
    structured feedback prompt the LLM can use to self-correct.

    Args:
        actions: A list of dicts. Each must have: action_type (str),
                 target (str), cost (float); optionally reversible (bool,
                 default True) and reason (str).
    """
    parsed: list[Action] = []
    for a in actions:
        if "target" not in a:
            return "Invalid action: missing 'target'."
        parsed.append(
            Action(
                action_type=str(a.get("action_type", "action")),
                target=str(a["target"]),
                cost=float(a.get("cost", 0.0)),
                reversible=bool(a.get("reversible", True)),
                reason=str(a.get("reason", "")),
            )
        )

    plan = ActionPlan(
        scope_id=DEMO_POLICY.scope_id,
        generated_for="mcp-session-001",
        dry_run=DEMO_POLICY.dry_run,
        actions=parsed,
    )

    # 1. Circuit breaker.
    if BREAKER.is_tripped():
        LEDGER.record_action_plan(plan, status="skipped")
        return (
            f"Circuit breaker is TRIPPED ({BREAKER.state.reason}); no new actions "
            "accepted until it resets. This is a safety pause after a bad run, "
            "not an error in your plan."
        )

    # 2. Policy.
    try:
        validate_actions(plan, DEMO_POLICY)
    except PolicyError as e:
        LEDGER.record_action_plan(plan, status="rejected")
        if e.requires_human_approval:
            return (
                "Action plan requires HUMAN APPROVAL.\n"
                f"Reason: {e.message}\n"
                "A notification has been sent to the user. You must wait for their approval."
            )
        return e.to_feedback_prompt()

    # 3. Passed. In a real gateway YOUR code executes each action here, then feeds
    #    any failures to BREAKER. In dry-run we only record the intent.
    status = "dry_run" if DEMO_POLICY.dry_run else "placed"
    LEDGER.record_action_plan(plan, status=status)
    return (
        f"SUCCESS: Passed all safety checks. Recorded {len(plan.actions)} "
        f"actions ({status}) for a total cost of {plan.cost_total:.2f}."
    )


# --------------------------------------------------------------------------- #
# TRADING tool — reference adapter gateway on top of the same pass.
# Before paper/live, replace DEMO_ACCOUNT with the REAL account state fetched
# from your broker (buying power + positions), or the cash and concentration
# checks validate against fictional numbers.
# --------------------------------------------------------------------------- #
DEMO_ACCOUNT = AccountState(
    account_id="user-account-123",
    buying_power=5000.0,
    positions={"VOO": 2000.0, "QQQ": 1000.0},
)

DEMO_CONFIG = GuardrailConfig(
    account_id="user-account-123",
    allowed_symbols={"VOO", "QQQ", "AAPL", "MSFT"},
    allow_sells=True,
    dry_run=True,
    min_order_usd=5.0,
    max_order_usd=500.0,
    human_approval_threshold_usd=300.0,
    require_stop_loss_for_buys=True,
    max_position_concentration=0.40,  # Max 40% in a single symbol
    shadow_mode=False,
)


@mcp.tool()
def evaluate_and_place_trade(orders: List[dict]) -> str:
    """
    Evaluates a proposed trade plan against the AgentRails safety guardrails.
    If it passes, the trade would be passed on to the broker (simulated here).
    If it fails, it returns a structured feedback prompt for the LLM to self-correct.

    Args:
        orders: A list of dictionaries representing the orders.
                Each dict must have: symbol (str), side ("buy" or "sell"),
                dollar_amount (float), and optionally stop_loss_price (float).
    """

    parsed_orders = []
    for o in orders:
        side_str = o.get("side", "").lower()
        if side_str == "buy":
            side = OrderSide.BUY
        elif side_str == "sell":
            side = OrderSide.SELL
        else:
            return f"Invalid order side: {side_str}"

        parsed_orders.append(
            PlannedOrder(
                symbol=o["symbol"],
                side=side,
                dollar_amount=float(o["dollar_amount"]),
                reason=o.get("reason", ""),
                stop_loss_price=o.get("stop_loss_price"),
            )
        )

    plan = TradePlan(
        account_id=DEMO_CONFIG.account_id,
        generated_for="mcp-session-001",
        dry_run=DEMO_CONFIG.dry_run,
        orders=parsed_orders,
    )

    # 1. Circuit breaker: if the account is paused after a losing streak or a
    #    drawdown, refuse new entries and record the skip.
    if BREAKER.is_tripped():
        LEDGER.record_plan(plan, status="skipped")
        return (
            "Circuit breaker is TRIPPED "
            f"({BREAKER.state.reason}); no new orders accepted until it resets. "
            "This is a safety pause after a bad run, not an error in your plan."
        )

    # Track account equity so the breaker can measure drawdown over time.
    BREAKER.update_equity(
        DEMO_ACCOUNT.buying_power + sum(DEMO_ACCOUNT.positions.values())
    )

    # 2. Guardrails.
    try:
        validate_plan(plan, DEMO_CONFIG, DEMO_ACCOUNT)
    except GuardrailError as e:
        LEDGER.record_plan(plan, status="rejected")
        if e.requires_human_approval:
            return (
                "Trade plan requires HUMAN APPROVAL.\n"
                f"Reason: {e.message}\n"
                "A notification has been sent to the user. You must wait for their approval."
            )
        return e.to_feedback_prompt()

    # 3. Passed. In a real gateway you would place each order via the broker here,
    #    then call BREAKER.record_trade_result(pnl) once fills settle. In dry-run
    #    we only record the intent to the ledger.
    status = "dry_run" if DEMO_CONFIG.dry_run else "placed"
    LEDGER.record_plan(plan, status=status)

    total_val = sum(o.dollar_amount for o in plan.orders)
    return (
        f"SUCCESS: Passed all safety guardrails. Recorded {len(plan.orders)} "
        f"orders ({status}) for a total of ${total_val:.2f}."
    )


if __name__ == "__main__":
    print("Starting AgentRails MCP Security Gateway...")
    mcp.run()
