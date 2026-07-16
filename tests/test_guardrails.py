import pytest

from agentrails import (
    AccountState,
    GuardrailConfig,
    GuardrailError,
    OrderSide,
    PlannedOrder,
    TradePlan,
    validate_plan,
)


def make_config(**overrides) -> GuardrailConfig:
    base = dict(
        account_id="acc-1",
        allowed_symbols={"VOO", "QQQ"},
        allow_sells=False,
        dry_run=True,
        min_order_usd=5,
        max_order_usd=200,
        max_orders_per_run=3,
        reserve_cash_usd=0,
        weekly_cap_usd=500,
    )
    base.update(overrides)
    return GuardrailConfig(**base)


def make_account(**overrides) -> AccountState:
    base = dict(account_id="acc-1", buying_power=1000, positions={"VOO": 300})
    base.update(overrides)
    return AccountState(**base)


def make_plan(orders, **overrides):
    base = dict(account_id="acc-1", generated_for="2026-07-16", dry_run=True, orders=orders)
    base.update(overrides)
    return TradePlan(**base)


def test_valid_plan_passes():
    plan = make_plan([PlannedOrder("VOO", OrderSide.BUY, 100)])
    validate_plan(plan, make_config(), make_account())  # should not raise


def test_wrong_account_rejected():
    plan = make_plan([PlannedOrder("VOO", OrderSide.BUY, 100)], account_id="acc-2")
    with pytest.raises(GuardrailError, match="Aborting"):
        validate_plan(plan, make_config(), make_account())


def test_buy_outside_whitelist_rejected():
    plan = make_plan([PlannedOrder("TSLA", OrderSide.BUY, 100)])
    with pytest.raises(GuardrailError, match="whitelist"):
        validate_plan(plan, make_config(), make_account())


def test_sell_rejected_when_allow_sells_false():
    plan = make_plan([PlannedOrder("VOO", OrderSide.SELL, 100)])
    with pytest.raises(GuardrailError, match="allow_sells"):
        validate_plan(plan, make_config(), make_account())


def test_sell_allowed_when_configured_and_held():
    plan = make_plan([PlannedOrder("VOO", OrderSide.SELL, 100)])
    cfg = make_config(allow_sells=True)
    validate_plan(plan, cfg, make_account())  # should not raise


def test_sell_of_unheld_symbol_rejected_even_if_allowed():
    plan = make_plan([PlannedOrder("QQQ", OrderSide.SELL, 100)])
    cfg = make_config(allow_sells=True)
    with pytest.raises(GuardrailError, match="doesn't hold"):
        validate_plan(plan, cfg, make_account())


def test_order_below_minimum_rejected():
    plan = make_plan([PlannedOrder("VOO", OrderSide.BUY, 1)])
    with pytest.raises(GuardrailError, match="below min_order_usd"):
        validate_plan(plan, make_config(), make_account())


def test_order_above_maximum_rejected():
    plan = make_plan([PlannedOrder("VOO", OrderSide.BUY, 999)])
    with pytest.raises(GuardrailError, match="exceeds max_order_usd"):
        validate_plan(plan, make_config(), make_account())


def test_too_many_orders_rejected():
    orders = [PlannedOrder("VOO", OrderSide.BUY, 10) for _ in range(4)]
    plan = make_plan(orders)
    with pytest.raises(GuardrailError, match="max_orders_per_run"):
        validate_plan(plan, make_config(), make_account())


def test_weekly_cap_enforced():
    plan = make_plan([PlannedOrder("VOO", OrderSide.BUY, 200), PlannedOrder("QQQ", OrderSide.BUY, 200)])
    cfg = make_config(max_order_usd=200, weekly_cap_usd=300)
    with pytest.raises(GuardrailError, match="exceeds spendable"):
        validate_plan(plan, cfg, make_account())


def test_reserve_cash_reduces_spendable():
    plan = make_plan([PlannedOrder("VOO", OrderSide.BUY, 200)])
    cfg = make_config(max_order_usd=200, weekly_cap_usd=None, reserve_cash_usd=900)
    with pytest.raises(GuardrailError, match="exceeds spendable"):
        validate_plan(plan, cfg, make_account(buying_power=1000))


def test_empty_whitelist_denies_all_buys_by_default():
    plan = make_plan([PlannedOrder("VOO", OrderSide.BUY, 50)])
    cfg = GuardrailConfig(account_id="acc-1")  # defaults: empty whitelist, dry_run=True
    with pytest.raises(GuardrailError, match="whitelist"):
        validate_plan(plan, cfg, make_account())
