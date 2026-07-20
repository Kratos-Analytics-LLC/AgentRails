"""Proves trading is a genuine instance of the generic core: a buy-only trade
plan that violates a domain-agnostic guardrail is flagged both by the trading
validator (`validate_plan`) and by the generic engine (`validate_actions`) on
the mapped objects. Sells, stop-loss and position-based concentration are
trading-specific and validated only by `validate_plan`, so they are out of scope
here by design."""

import pytest

from agentrails import (
    AccountState,
    GuardrailConfig,
    GuardrailError,
    OrderSide,
    PlannedOrder,
    PolicyError,
    TradePlan,
    validate_actions,
    validate_plan,
)
from agentrails.adapters.trading import (
    account_to_context,
    config_to_policy,
    order_to_action,
    plan_to_action_plan,
)


def make_config(**o):
    base = dict(
        account_id="acc-1",
        allowed_symbols={"VOO", "QQQ"},
        allow_sells=False,
        dry_run=True,
        min_order_usd=5,
        max_order_usd=200,
        max_orders_per_run=3,
        weekly_cap_usd=500,
    )
    base.update(o)
    return GuardrailConfig(**base)


def make_account(**o):
    base = dict(account_id="acc-1", buying_power=1000, positions={"VOO": 300})
    base.update(o)
    return AccountState(**base)


def make_plan(orders):
    return TradePlan(account_id="acc-1", generated_for="2026-07-16", dry_run=True, orders=orders)


def both_reject(plan, cfg, acct):
    """Assert validate_plan raises AND the mapped core also raises."""
    with pytest.raises(GuardrailError):
        validate_plan(plan, cfg, acct)
    with pytest.raises(PolicyError):
        validate_actions(
            plan_to_action_plan(plan), config_to_policy(cfg), account_to_context(acct, cfg)
        )


def both_pass(plan, cfg, acct):
    validate_plan(plan, cfg, acct)  # no raise
    assert (
        validate_actions(
            plan_to_action_plan(plan), config_to_policy(cfg), account_to_context(acct, cfg)
        )
        is None
    )


def test_mapping_field_by_field():
    order = PlannedOrder("VOO", OrderSide.BUY, 90, reason="dca", stop_loss_price=80)
    action = order_to_action(order)
    assert action.target == "VOO"
    assert action.cost == 90
    assert action.action_type == "buy"
    assert action.metadata["stop_loss_price"] == 80


def test_clean_buy_plan_passes_both():
    both_pass(make_plan([PlannedOrder("VOO", OrderSide.BUY, 100)]), make_config(), make_account())


def test_whitelist_violation_flagged_by_both():
    both_reject(make_plan([PlannedOrder("TSLA", OrderSide.BUY, 100)]), make_config(), make_account())


def test_max_order_violation_flagged_by_both():
    both_reject(make_plan([PlannedOrder("VOO", OrderSide.BUY, 999)]), make_config(), make_account())


def test_too_many_orders_flagged_by_both():
    orders = [PlannedOrder("VOO", OrderSide.BUY, 10) for _ in range(4)]
    both_reject(make_plan(orders), make_config(), make_account())


def test_budget_violation_flagged_by_both():
    orders = [PlannedOrder("VOO", OrderSide.BUY, 200), PlannedOrder("QQQ", OrderSide.BUY, 200)]
    both_reject(make_plan(orders), make_config(weekly_cap_usd=300), make_account())


def test_human_approval_flag_matches():
    cfg = make_config(max_order_usd=None, human_approval_threshold_usd=100)
    plan = make_plan([PlannedOrder("VOO", OrderSide.BUY, 150)])
    with pytest.raises(GuardrailError) as e1:
        validate_plan(plan, cfg, make_account())
    with pytest.raises(PolicyError) as e2:
        validate_actions(plan_to_action_plan(plan), config_to_policy(cfg), account_to_context(make_account(), cfg))
    assert e1.value.requires_human_approval is True
    assert e2.value.requires_human_approval is True
