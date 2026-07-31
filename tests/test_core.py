"""Tests for the domain-agnostic core (Action / ActionPlan / Policy /
validate_actions). No trading concepts here on purpose — this proves the core
stands on its own."""

import pytest

from agentrails import (
    Action,
    ActionPlan,
    Policy,
    PolicyContext,
    PolicyError,
    validate_actions,
)


def plan(actions, scope="s1", **o):
    base = dict(scope_id=scope, generated_for="run-1", dry_run=True, actions=actions)
    base.update(o)
    return ActionPlan(**base)


def policy(**o):
    base = dict(scope_id="s1", allowed_targets={"a", "b"}, max_actions_per_run=5)
    base.update(o)
    return Policy(**base)


def test_clean_plan_passes():
    p = plan([Action("send", "a", cost=10)])
    assert validate_actions(p, policy()) is None


def test_scope_mismatch_rejected():
    p = plan([Action("send", "a", cost=10)], scope="other")
    with pytest.raises(PolicyError, match="Aborting"):
        validate_actions(p, policy())


def test_target_not_allowed():
    p = plan([Action("send", "zzz", cost=10)])
    with pytest.raises(PolicyError) as e:
        validate_actions(p, policy())
    assert e.value.code == "not_allowed"


def test_empty_allowlist_denies_all():
    p = plan([Action("send", "a", cost=10)])
    with pytest.raises(PolicyError, match="deny-by-default"):
        validate_actions(p, policy(allowed_targets=set()))


def test_too_many_actions():
    p = plan([Action("send", "a", cost=1) for _ in range(6)])
    with pytest.raises(PolicyError, match="max_actions_per_run"):
        validate_actions(p, policy(max_actions_per_run=5))


def test_below_min_cost():
    p = plan([Action("send", "a", cost=0.5)])
    with pytest.raises(PolicyError, match="below min_cost"):
        validate_actions(p, policy(min_cost=1.0))


def test_above_max_cost():
    p = plan([Action("send", "a", cost=100)])
    with pytest.raises(PolicyError, match="exceeds max_cost"):
        validate_actions(p, policy(max_cost=50))


def test_irreversible_blocked_when_configured():
    p = plan([Action("delete", "a", cost=1, reversible=False)])
    with pytest.raises(PolicyError) as e:
        validate_actions(p, policy(allow_irreversible=False))
    assert e.value.code == "irreversible_blocked"


def test_irreversible_allowed_by_default():
    p = plan([Action("delete", "a", cost=1, reversible=False)])
    assert validate_actions(p, policy()) is None  # allow_irreversible defaults True


def test_human_approval_threshold_sets_flag():
    p = plan([Action("send", "a", cost=200)])
    with pytest.raises(PolicyError) as e:
        validate_actions(p, policy(human_approval_threshold=100))
    assert e.value.requires_human_approval is True
    assert e.value.code == "needs_approval"


def test_budget_from_policy():
    p = plan([Action("send", "a", cost=60), Action("send", "b", cost=60)])
    with pytest.raises(PolicyError, match="budget"):
        validate_actions(p, policy(budget=100))


def test_budget_from_context_is_min():
    # policy budget 500 but context says only 100 available -> effective 100
    p = plan([Action("send", "a", cost=150)])
    ctx = PolicyContext(scope_id="s1", available_budget=100)
    with pytest.raises(PolicyError, match="budget"):
        validate_actions(p, policy(budget=500), ctx)


def test_concentration_limit():
    # 80 of 100 total to target "a" = 80% > 40%
    p = plan([Action("send", "a", cost=80), Action("send", "b", cost=20)])
    with pytest.raises(PolicyError, match="concentration"):
        validate_actions(p, policy(max_target_concentration=0.40))


def test_shadow_mode_collects_all():
    p = plan([Action("send", "zzz", cost=0.1), Action("send", "yyy", cost=0.1)])
    errors = validate_actions(p, policy(min_cost=1.0, shadow_mode=True))
    assert isinstance(errors, list)
    assert len(errors) >= 2


def test_feedback_prompt():
    err = PolicyError("target zzz not allowed", code="not_allowed")
    assert "target zzz not allowed" in err.to_feedback_prompt()
