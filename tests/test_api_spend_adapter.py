"""Proves API spend is a genuine second instance of the generic core: the same
domain-agnostic guardrails that guard a trade plan guard an agent's API budget,
with no changes to the core. Every generic violation is flagged both by the
API-spend validator (`validate_api_spend`) and by the generic engine
(`validate_actions`) on the mapped objects. The per-model allowlist is
API-specific and validated only by `validate_api_spend`."""

import pytest

from agentrails import PolicyError, validate_actions
from agentrails.adapters.api_spend import (
    ApiCall,
    ApiCallPlan,
    SpendPolicy,
    SpendState,
    call_to_action,
    plan_to_action_plan,
    policy_to_core_policy,
    state_to_context,
    summarize_plan,
    validate_api_spend,
)


def make_policy(**o):
    base = dict(
        run_id="agent-1",
        allowed_providers={"anthropic", "openai"},
        dry_run=True,
        max_call_usd=1.00,
        max_calls_per_run=5,
        per_run_budget_usd=5.00,
    )
    base.update(o)
    return SpendPolicy(**base)


def make_state(**o):
    base = dict(run_id="agent-1", daily_budget_usd=20.0, spent_today_usd=0.0)
    base.update(o)
    return SpendState(**base)


def make_plan(calls):
    return ApiCallPlan(run_id="agent-1", generated_for="2026-07-18T10:00", calls=calls)


def both_reject(plan, pol, state):
    """Assert validate_api_spend raises AND the mapped core also raises."""
    with pytest.raises(PolicyError):
        validate_api_spend(plan, pol, state)
    with pytest.raises(PolicyError):
        validate_actions(
            plan_to_action_plan(plan), policy_to_core_policy(pol), state_to_context(state, pol)
        )


def both_pass(plan, pol, state):
    assert validate_api_spend(plan, pol, state) is None
    assert (
        validate_actions(
            plan_to_action_plan(plan), policy_to_core_policy(pol), state_to_context(state, pol)
        )
        is None
    )


# --- mapping ---------------------------------------------------------------


def test_mapping_field_by_field():
    call = ApiCall("anthropic", model="claude-opus-4-8", est_cost_usd=0.42, call_type="completion")
    action = call_to_action(call)
    assert action.target == "anthropic"
    assert action.cost == 0.42
    assert action.action_type == "completion"
    assert action.metadata["model"] == "claude-opus-4-8"


def test_state_maps_to_remaining_budget():
    state = make_state(daily_budget_usd=20.0, spent_today_usd=12.5)
    assert state.remaining_today_usd == 7.5
    ctx = state_to_context(state)
    assert ctx.available_budget == 7.5


# --- generic guardrails: flagged by BOTH validators ------------------------


def test_clean_plan_passes_both():
    both_pass(make_plan([ApiCall("anthropic", est_cost_usd=0.50)]), make_policy(), make_state())


def test_provider_not_allowed_flagged_by_both():
    both_reject(make_plan([ApiCall("cohere", est_cost_usd=0.10)]), make_policy(), make_state())


def test_empty_allowlist_denies_all():
    both_reject(
        make_plan([ApiCall("anthropic", est_cost_usd=0.10)]),
        make_policy(allowed_providers=set()),
        make_state(),
    )


def test_max_call_violation_flagged_by_both():
    both_reject(make_plan([ApiCall("openai", est_cost_usd=9.99)]), make_policy(), make_state())


def test_too_many_calls_flagged_by_both():
    calls = [ApiCall("anthropic", est_cost_usd=0.10) for _ in range(6)]
    both_reject(make_plan(calls), make_policy(max_calls_per_run=5), make_state())


def test_per_run_budget_flagged_by_both():
    calls = [ApiCall("anthropic", est_cost_usd=0.90), ApiCall("openai", est_cost_usd=0.90)]
    both_reject(make_plan(calls), make_policy(per_run_budget_usd=1.00), make_state())


def test_daily_budget_from_state_flagged_by_both():
    # per-run budget is generous, but only $0.20 of today's cap is left
    calls = [ApiCall("anthropic", est_cost_usd=0.50)]
    both_reject(
        make_plan(calls),
        make_policy(per_run_budget_usd=100.0),
        make_state(daily_budget_usd=20.0, spent_today_usd=19.80),
    )


def test_provider_concentration_flagged_by_both():
    # $0.80 of $1.00 total to one provider = 80% > 50%
    calls = [ApiCall("anthropic", est_cost_usd=0.80), ApiCall("openai", est_cost_usd=0.20)]
    both_reject(make_plan(calls), make_policy(max_provider_concentration=0.50), make_state())


def test_human_approval_flag_matches():
    pol = make_policy(max_call_usd=None, human_approval_threshold_usd=1.00)
    plan = make_plan([ApiCall("anthropic", est_cost_usd=2.50)])
    with pytest.raises(PolicyError) as e1:
        validate_api_spend(plan, pol, make_state())
    with pytest.raises(PolicyError) as e2:
        validate_actions(
            plan_to_action_plan(plan), policy_to_core_policy(pol), state_to_context(make_state(), pol)
        )
    assert e1.value.requires_human_approval is True
    assert e2.value.requires_human_approval is True
    assert e1.value.code == "needs_approval"


# --- API-specific rule: only validate_api_spend enforces it ----------------


def test_model_allowlist_is_api_specific():
    pol = make_policy(allowed_models={"claude-opus-4-8"})
    plan = make_plan([ApiCall("anthropic", model="claude-cheapo-0-1", est_cost_usd=0.10)])
    # The API-spend validator rejects the disallowed model...
    with pytest.raises(PolicyError) as e:
        validate_api_spend(plan, pol, make_state())
    assert e.value.code == "model_not_allowed"
    # ...but the generic core knows nothing about models, so it passes.
    assert (
        validate_actions(
            plan_to_action_plan(plan), policy_to_core_policy(pol), state_to_context(make_state(), pol)
        )
        is None
    )


def test_allowed_model_passes():
    pol = make_policy(allowed_models={"claude-opus-4-8", "gpt-5"})
    plan = make_plan([ApiCall("anthropic", model="claude-opus-4-8", est_cost_usd=0.10)])
    assert validate_api_spend(plan, pol, make_state()) is None


def test_model_allowlist_ignores_blank_model():
    # A call with no model set isn't second-guessed by the model allowlist.
    pol = make_policy(allowed_models={"gpt-5"})
    plan = make_plan([ApiCall("anthropic", est_cost_usd=0.10)])
    assert validate_api_spend(plan, pol, make_state()) is None


# --- shadow mode -----------------------------------------------------------


def test_shadow_mode_collects_generic_and_api_specific():
    pol = make_policy(
        allowed_providers={"anthropic"},
        allowed_models={"claude-opus-4-8"},
        max_call_usd=0.50,
        shadow_mode=True,
    )
    plan = make_plan(
        [
            ApiCall("cohere", model="command", est_cost_usd=9.99),  # provider + max_call
            ApiCall("anthropic", model="claude-cheapo-0-1", est_cost_usd=0.10),  # model
        ]
    )
    errors = validate_api_spend(plan, pol, make_state())
    assert isinstance(errors, list)
    codes = {e.code for e in errors}
    assert "not_allowed" in codes  # generic core violation
    assert "model_not_allowed" in codes  # API-specific violation


def test_no_state_still_validates():
    # State is optional; without it, only policy-level limits apply.
    plan = make_plan([ApiCall("anthropic", est_cost_usd=0.50)])
    assert validate_api_spend(plan, make_policy()) is None


# --- summary ---------------------------------------------------------------


def test_summary_reports_total_without_calling():
    plan = make_plan(
        [ApiCall("anthropic", est_cost_usd=0.40, reason="plan"), ApiCall("openai", est_cost_usd=0.10)]
    )
    out = summarize_plan(plan)
    assert "0.50" in out
    assert "anthropic" in out and "openai" in out
