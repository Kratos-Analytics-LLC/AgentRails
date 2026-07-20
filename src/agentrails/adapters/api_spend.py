"""API spend as a second reference adapter over the generic core.

Trading was the first adapter; this is the second, and it is deliberately
non-financial-*markets* — it's about capping how much an autonomous agent can
spend calling paid APIs (LLM providers, search, geocoding, whatever it's wired
to). Its whole reason to exist is to prove the core generalizes: the exact same
`agentrails.core` primitives that guard a trade plan also guard an agent's
API budget, with no changes to the core.

The mapping:

    ApiCall      -> Action(action_type=call_type, target=provider, cost=est_cost_usd)
    ApiCallPlan  -> ActionPlan
    SpendPolicy  -> Policy
    SpendState   -> PolicyContext

Which core primitive does each spend limit become?

    allowed_providers            -> Policy.allowed_targets      (deny-by-default)
    max_call_usd                 -> Policy.max_cost             (per-action size)
    max_calls_per_run            -> Policy.max_actions_per_run
    per_run_budget_usd           -> Policy.budget               (cap for one run)
    daily_budget - spent_today   -> PolicyContext.available_budget
    human_approval_threshold_usd -> Policy.human_approval_threshold
    max_provider_concentration   -> Policy.max_target_concentration

The generic core does the generic part. The one genuinely API-specific rule —
an optional per-*model* allowlist that is finer-grained than the per-provider
allowlist — stays in this adapter's validator (`validate_api_spend`), exactly
as trading keeps its stop-loss and "can't sell what you don't hold" rules in
`agentrails.validate_plan`. That split is the pattern for writing any adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..core import (
    Action,
    ActionPlan,
    Policy,
    PolicyContext,
    PolicyError,
    validate_actions,
)


@dataclass
class ApiCall:
    """One paid API call an agent wants to make.

    `est_cost_usd` is your *estimate* of what the call will cost before you make
    it — the whole point is to check the estimate against the budget before the
    money is spent, not to reconcile the bill after. `model` is optional and only
    matters if the policy pins an allowed-model list.
    """

    provider: str
    model: str = ""
    est_cost_usd: float = 0.0
    call_type: str = "call"  # e.g. "completion", "embedding", "search"
    reason: str = ""
    tag: str = ""  # free-form grouping label (e.g. "planning", "retrieval")


@dataclass
class ApiCallPlan:
    """The batch of API calls one agent run intends to make, before making any
    of them. Produced by your agent's own logic; the adapter only ever reads it.
    """

    run_id: str
    generated_for: str  # e.g. an ISO timestamp or run label
    dry_run: bool = True
    calls: list[ApiCall] = field(default_factory=list)

    @property
    def cost_total(self) -> float:
        # Rounded to cents to match what the core actually enforces.
        return round(sum(c.est_cost_usd for c in self.calls), 2)


@dataclass
class SpendPolicy:
    """Declarative spend limits for one run scope. Fails closed, same as every
    other AgentRails policy: an empty `allowed_providers` denies every call and
    `dry_run` defaults to True, so an untouched policy can only ever simulate.
    """

    run_id: str
    allowed_providers: set[str] = field(default_factory=set)  # empty = deny all
    # None = any model from an allowed provider is fine; a set pins the allowed
    # models on top of the provider allowlist (the one API-specific rule).
    allowed_models: set[str] | None = None
    dry_run: bool = True

    max_call_usd: float | None = None  # per-call ceiling
    max_calls_per_run: int = 50
    per_run_budget_usd: float | None = None  # cap on one run's total spend
    human_approval_threshold_usd: float | None = None
    max_provider_concentration: float | None = None  # max share of run to one provider
    shadow_mode: bool = False


@dataclass
class SpendState:
    """Live spend state for the scope, so a fresh agent run picks up where the
    last one left off: today's budget and how much of it is already gone. A
    scheduled task that starts cold each time still respects the daily cap.
    """

    run_id: str
    daily_budget_usd: float | None = None
    spent_today_usd: float = 0.0
    spend_by_provider: dict[str, float] = field(default_factory=dict)

    @property
    def remaining_today_usd(self) -> float | None:
        if self.daily_budget_usd is None:
            return None
        return round(self.daily_budget_usd - self.spent_today_usd, 2)


# --- mapping onto the generic core ----------------------------------------


def call_to_action(call: ApiCall) -> Action:
    return Action(
        action_type=call.call_type,
        target=call.provider,
        cost=call.est_cost_usd,
        # Spending money is not "irreversible/destructive" in the core sense
        # (that flag is for deletes/transfers); a budget overrun is caught by
        # the budget/max_cost checks instead.
        reversible=True,
        reason=call.reason,
        tag=call.tag,
        metadata={"model": call.model},
    )


def plan_to_action_plan(plan: ApiCallPlan) -> ActionPlan:
    return ActionPlan(
        scope_id=plan.run_id,
        generated_for=plan.generated_for,
        dry_run=plan.dry_run,
        actions=[call_to_action(c) for c in plan.calls],
    )


def policy_to_core_policy(policy: SpendPolicy) -> Policy:
    return Policy(
        scope_id=policy.run_id,
        allowed_targets=set(policy.allowed_providers),
        dry_run=policy.dry_run,
        max_cost=policy.max_call_usd,
        max_actions_per_run=policy.max_calls_per_run,
        budget=policy.per_run_budget_usd,
        human_approval_threshold=policy.human_approval_threshold_usd,
        max_target_concentration=policy.max_provider_concentration,
        shadow_mode=policy.shadow_mode,
    )


def state_to_context(
    state: SpendState, policy: SpendPolicy | None = None
) -> PolicyContext:
    # The effective budget for this run is whatever is left of today's cap; the
    # core takes the min of this and the policy's per-run budget.
    return PolicyContext(
        scope_id=state.run_id,
        available_budget=state.remaining_today_usd,
        exposures=dict(state.spend_by_provider),
    )


# --- canonical API-spend validator ----------------------------------------


def validate_api_spend(
    plan: ApiCallPlan,
    policy: SpendPolicy,
    state: SpendState | None = None,
) -> list[PolicyError] | None:
    """Validate an ApiCallPlan against a SpendPolicy.

    Runs the full generic core validation on the mapped plan (allowlist, per-call
    ceiling, calls-per-run, per-run and daily budget, human-approval threshold,
    provider concentration), then applies the one API-specific rule: an optional
    per-model allowlist.

    Same contract as `agentrails.core.validate_actions`: raises `PolicyError` on
    the first violation, or — in shadow mode — collects and returns every
    violation without raising, or returns None if the plan is clean.
    """
    core_plan = plan_to_action_plan(plan)
    core_policy = policy_to_core_policy(policy)
    context = state_to_context(state, policy) if state is not None else None

    # In default (fail-fast) mode this raises on the first violation and we never
    # reach the model check. In shadow mode it returns the list of core errors.
    errors = list(validate_actions(core_plan, core_policy, context) or [])

    # API-specific: pin which *model* is allowed, finer than the provider
    # allowlist. Providers are the coarse target; some teams also want to make
    # sure the agent didn't quietly switch to a pricier model.
    if policy.allowed_models is not None:
        for call in plan.calls:
            if call.model and call.model not in policy.allowed_models:
                err = PolicyError(
                    f"{call.provider}/{call.model}: model not in allowed_models.",
                    code="model_not_allowed",
                    target=call.provider,
                )
                if not policy.shadow_mode:
                    raise err
                errors.append(err)

    return errors if (errors and policy.shadow_mode) else None


def summarize_plan(plan: ApiCallPlan) -> str:
    """Human-readable dry-run summary: exactly what would be spent, per call and
    in total, without making a single request."""
    lines = [
        f"API-spend plan '{plan.generated_for}' (run {plan.run_id}) — "
        f"dry_run={plan.dry_run}"
    ]
    for c in plan.calls:
        model = f"/{c.model}" if c.model else ""
        reason = f"  — {c.reason}" if c.reason else ""
        lines.append(f"  {c.provider}{model}: ~${c.est_cost_usd:.2f}{reason}")
    lines.append(
        f"  TOTAL: ~${plan.cost_total:.2f} across {len(plan.calls)} call(s)"
    )
    return "\n".join(lines)


__all__ = [
    "ApiCall",
    "ApiCallPlan",
    "SpendPolicy",
    "SpendState",
    "call_to_action",
    "plan_to_action_plan",
    "policy_to_core_policy",
    "state_to_context",
    "validate_api_spend",
    "summarize_plan",
]
