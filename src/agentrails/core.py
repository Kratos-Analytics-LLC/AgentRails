"""The domain-agnostic core of AgentRails.

Everything in this module is generic: it knows nothing about trading, brokers,
symbols or dollars. It models the shared pattern behind every guardrailed agent
action — "the agent proposes actions, a policy says which are allowed, and a
pure validator decides" — so that any domain (trading, email, code execution,
API spend, infra changes) can be built on top as a thin adapter.

Trading is one such adapter; see `agentrails.adapters.trading`. The historic
trading API (`GuardrailConfig`, `TradePlan`, `validate_plan`) still works
exactly as before and is the reference implementation of these ideas.

Vocabulary map (trading term -> generic term):
    order/symbol/dollar_amount  -> Action(target, cost)
    TradePlan                   -> ActionPlan
    GuardrailConfig             -> Policy
    account buying power/pos.   -> PolicyContext(available_budget, exposures)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_EPS = 1e-9


class PolicyError(RuntimeError):
    """Raised (or collected, in shadow mode) when an action violates a policy.

    `code` is a stable machine-readable reason; `requires_human_approval`
    marks the "not forbidden, but needs a person to sign off" case so callers
    can route it to an approval flow instead of treating it as a hard failure.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "",
        requires_human_approval: bool = False,
        target: str = "",
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.requires_human_approval = requires_human_approval
        self.target = target

    def to_feedback_prompt(self) -> str:
        """A structured message you can hand back to an LLM planner so it can
        revise and retry against the same constraint."""
        return (
            "Your proposed action plan was rejected by the safety policy for the "
            "following reason:\n"
            f"- {self.message}\n"
            "Please revise your plan to comply with this constraint and try again."
        )


@dataclass
class Action:
    """One thing an agent wants to do.

    `cost` is the magnitude on whatever axis the policy limits (dollars, number
    of recipients, API tokens, ...). `reversible=False` marks destructive or
    irreversible actions (delete, transfer, irreversible send) that a policy can
    choose to block outright. `metadata` carries domain-specific extras the core
    ignores (e.g. a trading stop-loss price).
    """

    action_type: str
    target: str
    cost: float = 0.0
    reversible: bool = True
    reason: str = ""
    tag: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionPlan:
    """A concrete batch of actions for one scope, one run. Produced by the
    agent's own logic; the core only ever reads it."""

    scope_id: str
    generated_for: str
    dry_run: bool
    actions: list[Action] = field(default_factory=list)

    @property
    def cost_total(self) -> float:
        return round(sum(a.cost for a in self.actions), 2)

    def cost_by_target(self) -> dict[str, float]:
        totals: dict[str, float] = {}
        for a in self.actions:
            totals[a.target] = totals.get(a.target, 0.0) + a.cost
        return totals


@dataclass
class PolicyContext:
    """Optional live state the policy validates against: how much budget is
    actually available and current exposure per target."""

    scope_id: str
    available_budget: float | None = None
    exposures: dict[str, float] = field(default_factory=dict)


@dataclass
class Policy:
    """Declarative rules. Fails closed: an empty `allowed_targets` denies every
    action, and `dry_run` defaults to True.
    """

    scope_id: str
    allowed_targets: set[str] = field(default_factory=set)  # empty = deny all
    dry_run: bool = True

    min_cost: float = 0.0
    max_cost: float | None = None
    max_actions_per_run: int = 5

    budget: float | None = None  # cap on total cost of the run
    human_approval_threshold: float | None = None
    max_target_concentration: float | None = None  # max share of run cost to one target
    allow_irreversible: bool = True

    shadow_mode: bool = False


def validate_actions(
    plan: ActionPlan,
    policy: Policy,
    context: PolicyContext | None = None,
) -> list[PolicyError] | None:
    """Validate an ActionPlan against a Policy.

    Default mode: raises PolicyError on the first violation, returns None if the
    plan is clean. Shadow mode (`policy.shadow_mode=True`): collects and returns
    every violation without raising, or None if the plan is clean.
    """
    errors: list[PolicyError] = []

    def _fail(msg: str, code: str, *, requires_human: bool = False, target: str = ""):
        err = PolicyError(msg, code=code, requires_human_approval=requires_human, target=target)
        if not policy.shadow_mode:
            raise err
        errors.append(err)

    # Scope must match — acting on the wrong account/namespace is the worst case.
    if plan.scope_id != policy.scope_id:
        _fail(
            f"Plan targets scope '{plan.scope_id}' but policy is scoped to "
            f"'{policy.scope_id}'. Aborting.",
            code="scope_mismatch",
        )
    if context is not None and context.scope_id != policy.scope_id:
        _fail(
            f"Context is for scope '{context.scope_id}', not the configured "
            f"'{policy.scope_id}'. Aborting.",
            code="scope_mismatch",
        )

    if len(plan.actions) > policy.max_actions_per_run:
        _fail(
            f"{len(plan.actions)} actions exceeds max_actions_per_run="
            f"{policy.max_actions_per_run}.",
            code="too_many",
        )

    for a in plan.actions:
        if a.target not in policy.allowed_targets:
            _fail(
                f"{a.target}: not in allowed_targets. Actions are deny-by-default.",
                code="not_allowed",
                target=a.target,
            )
        if not policy.allow_irreversible and not a.reversible:
            _fail(
                f"{a.target}: irreversible action blocked (allow_irreversible=False).",
                code="irreversible_blocked",
                target=a.target,
            )
        if a.cost < policy.min_cost - _EPS:
            _fail(
                f"{a.target}: cost {a.cost:.2f} is below min_cost={policy.min_cost:.2f}.",
                code="below_min",
                target=a.target,
            )
        if policy.max_cost is not None and a.cost > policy.max_cost + _EPS:
            _fail(
                f"{a.target}: cost {a.cost:.2f} exceeds max_cost={policy.max_cost:.2f}.",
                code="above_max",
                target=a.target,
            )
        if (
            policy.human_approval_threshold is not None
            and a.cost > policy.human_approval_threshold + _EPS
        ):
            _fail(
                f"{a.target}: cost {a.cost:.2f} exceeds human_approval_threshold="
                f"{policy.human_approval_threshold:.2f} and requires manual confirmation.",
                code="needs_approval",
                requires_human=True,
                target=a.target,
            )

    # Budget: total run cost can't exceed the smaller of the policy budget and
    # whatever the context says is actually available.
    budget = policy.budget
    if context is not None and context.available_budget is not None:
        budget = context.available_budget if budget is None else min(budget, context.available_budget)
    if budget is not None and plan.cost_total > budget + _EPS:
        _fail(
            f"Total run cost {plan.cost_total:.2f} exceeds available budget {budget:.2f}.",
            code="over_budget",
        )

    # Concentration: no single target may take more than the configured share of
    # this run's total cost.
    if policy.max_target_concentration is not None and plan.cost_total > 0:
        for target, cost in plan.cost_by_target().items():
            share = cost / plan.cost_total
            if share > policy.max_target_concentration + 1e-5:
                _fail(
                    f"{target}: {share:.1%} of run cost exceeds "
                    f"max_target_concentration={policy.max_target_concentration:.1%}.",
                    code="over_concentration",
                    target=target,
                )

    return errors if (errors and policy.shadow_mode) else None
