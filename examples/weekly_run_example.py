"""Reference integration: how a scheduled Claude agent task (or any cron/
launchd job that calls out to Claude for the MCP step) would use AgentRails
around a broker MCP.

This file is illustrative, not runnable as-is — `call_mcp_tool` stands in
for whatever your agent framework uses to invoke MCP tools
(get_portfolio, place_equity_order, etc.). The point being demonstrated
is the CONTROL FLOW, which is broker-agnostic:

    1. Read real account state via the broker MCP.
    2. Run YOUR strategy to produce a TradePlan (not shown — bring your own).
    3. validate_plan() — hard stop on any guardrail violation.
    4. Check the circuit breaker — hard stop if tripped.
    5. If dry_run: log to the ledger and stop. Otherwise place each order
       via the broker MCP, one at a time, recording the result.
"""

from __future__ import annotations

from agentrails import (
    AccountState,
    CircuitBreaker,
    GuardrailConfig,
    GuardrailError,
    Ledger,
    TradePlan,
    validate_plan,
)

# ---------------------------------------------------------------------------
# 1. Config lives in one place, reviewed like code (not edited on a whim).
# ---------------------------------------------------------------------------

CONFIG = GuardrailConfig(
    account_id="00000000",
    allowed_symbols={"VOO", "QQQ", "SMH"},
    allow_sells=False,
    dry_run=True,  # flip to False only after you trust the plan output
    min_order_usd=5,
    max_order_usd=150,
    max_orders_per_run=5,
    reserve_cash_usd=0,
    weekly_cap_usd=100,
)

LEDGER = Ledger("reports/trade_ledger.csv")
BREAKER = CircuitBreaker(
    "reports/circuit_breaker.json",
    max_consecutive_losses=5,
    max_drawdown_pct=0.35,
    cooldown_hours=4,
)


def call_mcp_tool(name: str, **kwargs):
    """Stand-in for your agent's actual MCP call. Replace with the real
    thing — get_portfolio / get_equity_positions / review_equity_order /
    place_equity_order for Robinhood, or the equivalent for Alpaca, IBKR,
    etc. AgentRails never calls this itself; that's on purpose."""
    raise NotImplementedError("wire this up to your MCP client")


def build_plan_with_your_strategy(account: AccountState) -> TradePlan:
    """This is the one function AgentRails deliberately does NOT provide.
    Your valuation/momentum/DCA/whatever-you-trust logic goes here and
    returns a TradePlan. AgentRails' job starts the moment you have one."""
    raise NotImplementedError("bring your own strategy")


def run() -> None:
    if BREAKER.is_tripped():
        print(f"Circuit breaker tripped ({BREAKER.state.reason}); skipping this run.")
        return

    portfolio = call_mcp_tool("get_portfolio", account_number=CONFIG.account_id)
    positions = call_mcp_tool("get_equity_positions", account_number=CONFIG.account_id)
    account = AccountState(
        account_id=CONFIG.account_id,
        buying_power=portfolio["buying_power"],
        positions={p["symbol"]: p["market_value"] for p in positions},
    )
    BREAKER.update_equity(account.buying_power + sum(account.positions.values()))

    plan = build_plan_with_your_strategy(account)

    try:
        validate_plan(plan, CONFIG, account)
    except GuardrailError as e:
        LEDGER.record_plan(plan, status="rejected")
        print(f"Guardrail violation, nothing placed: {e}")
        return

    if CONFIG.dry_run:
        LEDGER.record_plan(plan, status="dry_run")
        print(f"Dry run: {len(plan.orders)} orders, ${plan.orders_total} would have been placed.")
        return

    for order in plan.orders:
        call_mcp_tool(
            "review_equity_order",
            account_number=CONFIG.account_id,
            symbol=order.symbol,
            side=order.side.value,
            dollar_amount=f"{order.dollar_amount:.2f}",
        )
        result = call_mcp_tool(
            "place_equity_order",
            account_number=CONFIG.account_id,
            symbol=order.symbol,
            side=order.side.value,
            dollar_amount=f"{order.dollar_amount:.2f}",
        )
        LEDGER.record(
            account_id=CONFIG.account_id,
            run_label=plan.generated_for,
            symbol=order.symbol,
            side=order.side.value,
            dollar_amount=order.dollar_amount,
            status="placed",
            order_id=result.get("id", ""),
            note=order.reason,
        )


if __name__ == "__main__":
    run()
