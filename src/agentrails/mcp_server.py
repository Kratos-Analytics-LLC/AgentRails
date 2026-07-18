"""Reference MCP gateway for AgentRails.

Exposes a single `evaluate_and_place_trade` tool that an agent calls with a
proposed set of orders. The gateway does the full safety pass:

    1. Circuit breaker — if the account is paused after a bad run, refuse.
    2. validate_plan — enforce every configured guardrail.
    3. Ledger — record what happened (rejected / dry-run / placed) so there is
       an auditable trail, not just a claim in a chat transcript.

This is an EXAMPLE wiring, not a hosted service. It uses mock demo account/
config and never talks to a real broker. See MASTER_PLAN.md for how to turn it
into a paper-trading (then live) gateway.
"""

from typing import List

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    import sys
    print("The 'mcp' package is required. Install it with `pip install agentrails[mcp]`.")
    sys.exit(1)

from agentrails.models import TradePlan, PlannedOrder, OrderSide, AccountState
from agentrails.guardrails import GuardrailConfig, validate_plan, GuardrailError
from agentrails.ledger import Ledger
from agentrails.circuit_breaker import CircuitBreaker

# Initialize FastMCP Server
mcp = FastMCP("AgentRails_Gateway")

# --------------------------------------------------------------------------- #
# Audit trail + account-level circuit breaker.
# Both write under reports/ (gitignored). In production point these at durable
# storage outside the instance.
# --------------------------------------------------------------------------- #
LEDGER = Ledger("reports/mcp_ledger.csv")
BREAKER = CircuitBreaker(
    "reports/mcp_circuit_breaker.json",
    max_consecutive_losses=5,
    max_drawdown_pct=0.35,
    cooldown_hours=4.0,
)

# A mock account state and config for demonstration purposes.
# PHASE 2 (see MASTER_PLAN.md): replace DEMO_ACCOUNT with the REAL account state
# fetched from your broker (buying power + positions) before going to paper/live,
# or the cash and concentration checks validate against fictional numbers.
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
