import asyncio
from typing import Any, List
try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    import sys
    print("The 'mcp' package is required. Install it with `pip install agentrails[mcp]`.")
    sys.exit(1)

from agentrails.models import TradePlan, PlannedOrder, OrderSide, AccountState
from agentrails.guardrails import GuardrailConfig, validate_plan, GuardrailError

# Initialize FastMCP Server
mcp = FastMCP("AgentRails_Gateway")

# A mock account state and config for demonstration purposes.
# In a real setup, you would load these from a secure store or the underlying broker.
DEMO_ACCOUNT = AccountState(
    account_id="user-account-123",
    buying_power=5000.0,
    positions={"VOO": 2000.0, "QQQ": 1000.0}
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
    shadow_mode=False
)

@mcp.tool()
def evaluate_and_place_trade(orders: List[dict]) -> str:
    """
    Evaluates a proposed trade plan against the AgentRails safety guardrails.
    If it passes, the trade is passed on to the broker. 
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
                stop_loss_price=o.get("stop_loss_price")
            )
        )
        
    plan = TradePlan(
        account_id=DEMO_CONFIG.account_id,
        generated_for="mcp-session-001",
        dry_run=DEMO_CONFIG.dry_run,
        orders=parsed_orders
    )

    try:
        errors = validate_plan(plan, DEMO_CONFIG, DEMO_ACCOUNT)
        if errors and DEMO_CONFIG.shadow_mode:
            # Shadow mode: just log and proceed
            print(f"[SHADOW MODE] Ignored {len(errors)} guardrail violations.")
    except GuardrailError as e:
        if e.requires_human_approval:
            return (
                "Trade plan requires HUMAN APPROVAL.\n"
                f"Reason: {e.message}\n"
                "A notification has been sent to the user. You must wait for their approval."
            )
        return e.to_feedback_prompt()
        
    # If we got here, it's safe to send to the real broker!
    # (Simulated execution)
    total_val = sum(o.dollar_amount for o in plan.orders)
    return f"SUCCESS: Passed all safety guardrails. Executed {len(plan.orders)} orders for a total of ${total_val:.2f}."


if __name__ == "__main__":
    print("Starting AgentRails MCP Security Gateway...")
    mcp.run()
