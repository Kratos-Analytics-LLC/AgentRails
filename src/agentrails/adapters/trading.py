"""Trading as a reference adapter over the generic core.

This shows how the historic trading domain maps onto `agentrails.core`:

    PlannedOrder  -> Action(action_type=side, target=symbol, cost=dollar_amount)
    TradePlan     -> ActionPlan
    GuardrailConfig -> Policy
    AccountState  -> PolicyContext

The mapping covers the domain-agnostic guardrails (allowlist, per-action size,
max actions per run, budget, human-approval threshold, concentration). Trading
also has domain-specific rules that stay in `guardrails.validate_plan` — the
mandatory stop-loss and the "can't sell what you don't hold" check — because
they only make sense for orders. In other words: the generic core does the
generic part, the adapter keeps what is genuinely trading-specific.

The canonical trading validator remains `agentrails.validate_plan`; these
helpers exist to demonstrate (and test) that trading is an instance of the
core, and to make it easy to build the next, non-financial adapter the same way.
"""

from __future__ import annotations

from ..core import Action, ActionPlan, Policy, PolicyContext
from ..guardrails import GuardrailConfig
from ..models import AccountState, OrderSide, PlannedOrder, TradePlan


def order_to_action(order: PlannedOrder) -> Action:
    return Action(
        action_type=order.side.value,
        target=order.symbol,
        cost=order.dollar_amount,
        # Trading orders are not "irreversible/destructive" in the core sense;
        # the buy/sell distinction is handled by the trading-specific validator.
        reversible=True,
        reason=order.reason,
        tag=order.tag,
        metadata={"stop_loss_price": order.stop_loss_price, "side": order.side.value},
    )


def plan_to_action_plan(plan: TradePlan) -> ActionPlan:
    return ActionPlan(
        scope_id=plan.account_id,
        generated_for=plan.generated_for,
        dry_run=plan.dry_run,
        actions=[order_to_action(o) for o in plan.orders],
    )


def config_to_policy(config: GuardrailConfig) -> Policy:
    return Policy(
        scope_id=config.account_id,
        allowed_targets=set(config.allowed_symbols),
        dry_run=config.dry_run,
        min_cost=config.min_order_usd,
        max_cost=config.max_order_usd,
        max_actions_per_run=config.max_orders_per_run,
        budget=config.weekly_cap_usd,
        human_approval_threshold=config.human_approval_threshold_usd,
        max_target_concentration=config.max_position_concentration,
        shadow_mode=config.shadow_mode,
    )


def account_to_context(
    account: AccountState, config: GuardrailConfig | None = None
) -> PolicyContext:
    reserve = config.reserve_cash_usd if config is not None else 0.0
    return PolicyContext(
        scope_id=account.account_id,
        available_budget=account.buying_power - reserve,
        exposures=dict(account.positions),
    )


__all__ = [
    "order_to_action",
    "plan_to_action_plan",
    "config_to_policy",
    "account_to_context",
]
