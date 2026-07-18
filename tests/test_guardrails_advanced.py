"""Tests for the advanced guardrails added on top of the core checks:
stop-loss requirement, position concentration, human-approval threshold and
shadow mode. These complement tests/test_guardrails.py (core rules).
"""

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


def make_account(**overrides) -> AccountState:
    base = dict(account_id="acc-1", buying_power=1000, positions={"VOO": 400})
    base.update(overrides)
    return AccountState(**base)


def make_plan(orders, **overrides):
    base = dict(account_id="acc-1", generated_for="2026-07-16", dry_run=True, orders=orders)
    base.update(overrides)
    return TradePlan(**base)


def base_config(**overrides) -> GuardrailConfig:
    base = dict(
        account_id="acc-1",
        allowed_symbols={"VOO", "QQQ"},
        allow_sells=False,
        dry_run=True,
        min_order_usd=1,
        max_order_usd=None,
        max_orders_per_run=5,
    )
    base.update(overrides)
    return GuardrailConfig(**base)


# --------------------------------------------------------------------------- #
# require_stop_loss_for_buys
# --------------------------------------------------------------------------- #

def test_buy_without_stop_loss_rejected_when_required():
    cfg = base_config(require_stop_loss_for_buys=True)
    plan = make_plan([PlannedOrder("VOO", OrderSide.BUY, 50)])  # no stop_loss_price
    with pytest.raises(GuardrailError, match="stop_loss_price"):
        validate_plan(plan, cfg, make_account())


def test_buy_with_stop_loss_passes_when_required():
    cfg = base_config(require_stop_loss_for_buys=True)
    plan = make_plan([PlannedOrder("VOO", OrderSide.BUY, 50, stop_loss_price=45)])
    validate_plan(plan, cfg, make_account())  # should not raise


def test_stop_loss_not_required_by_default():
    cfg = base_config()  # require_stop_loss_for_buys defaults False
    plan = make_plan([PlannedOrder("VOO", OrderSide.BUY, 50)])
    validate_plan(plan, cfg, make_account())  # should not raise


# --------------------------------------------------------------------------- #
# human_approval_threshold_usd
# --------------------------------------------------------------------------- #

def test_order_above_human_threshold_flags_approval():
    cfg = base_config(human_approval_threshold_usd=100.0)
    plan = make_plan([PlannedOrder("VOO", OrderSide.BUY, 150)])
    with pytest.raises(GuardrailError) as excinfo:
        validate_plan(plan, cfg, make_account())
    assert excinfo.value.requires_human_approval is True


def test_order_below_human_threshold_passes():
    cfg = base_config(human_approval_threshold_usd=100.0)
    plan = make_plan([PlannedOrder("VOO", OrderSide.BUY, 50)])
    validate_plan(plan, cfg, make_account())  # should not raise


def test_normal_violation_does_not_flag_human_approval():
    cfg = base_config()  # no threshold
    plan = make_plan([PlannedOrder("TSLA", OrderSide.BUY, 50)])  # not whitelisted
    with pytest.raises(GuardrailError) as excinfo:
        validate_plan(plan, cfg, make_account())
    assert excinfo.value.requires_human_approval is False


# --------------------------------------------------------------------------- #
# max_position_concentration
# --------------------------------------------------------------------------- #

def test_concentration_exceeded_rejected():
    # account: 1000 cash + 400 VOO. Buy 200 more VOO -> post: 600 VOO,
    # equity 1400, concentration 600/1400 = 42.9% > 40%.
    cfg = base_config(max_position_concentration=0.40)
    plan = make_plan([PlannedOrder("VOO", OrderSide.BUY, 200)])
    with pytest.raises(GuardrailError, match="concentration"):
        validate_plan(plan, cfg, make_account())


def test_concentration_within_limit_passes():
    # Buy only 50 -> post: 450 VOO, equity 1400, concentration 32.1% < 40%.
    cfg = base_config(max_position_concentration=0.40)
    plan = make_plan([PlannedOrder("VOO", OrderSide.BUY, 50)])
    validate_plan(plan, cfg, make_account())  # should not raise


def test_concentration_not_checked_when_none():
    cfg = base_config(max_position_concentration=None)
    plan = make_plan([PlannedOrder("VOO", OrderSide.BUY, 200)])
    validate_plan(plan, cfg, make_account())  # should not raise


# --------------------------------------------------------------------------- #
# shadow_mode
# --------------------------------------------------------------------------- #

def test_shadow_mode_collects_instead_of_raising():
    cfg = base_config(require_stop_loss_for_buys=True, shadow_mode=True)
    # TSLA not whitelisted AND no stop loss; VOO no stop loss -> several violations
    plan = make_plan([
        PlannedOrder("TSLA", OrderSide.BUY, 50),
        PlannedOrder("VOO", OrderSide.BUY, 50),
    ])
    errors = validate_plan(plan, cfg, make_account())
    assert isinstance(errors, list)
    assert len(errors) >= 2
    assert all(isinstance(e, GuardrailError) for e in errors)


def test_shadow_mode_returns_none_when_clean():
    cfg = base_config(shadow_mode=True)
    plan = make_plan([PlannedOrder("VOO", OrderSide.BUY, 50)])
    assert validate_plan(plan, cfg, make_account()) is None


def test_shadow_mode_does_not_raise():
    cfg = base_config(shadow_mode=True)
    plan = make_plan([PlannedOrder("TSLA", OrderSide.BUY, 50)])
    # would raise in normal mode; in shadow mode it must return a list
    result = validate_plan(plan, cfg, make_account())
    assert isinstance(result, list) and len(result) >= 1


# --------------------------------------------------------------------------- #
# GuardrailError helpers
# --------------------------------------------------------------------------- #

def test_feedback_prompt_contains_reason():
    err = GuardrailError("VOO: not in allowed_symbols whitelist.")
    prompt = err.to_feedback_prompt()
    assert "VOO: not in allowed_symbols whitelist." in prompt
    assert "revise" in prompt.lower()


def test_requires_human_approval_defaults_false():
    assert GuardrailError("x").requires_human_approval is False
