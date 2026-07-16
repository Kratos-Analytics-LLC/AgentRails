"""The core of AgentRails: a pure, deterministic second barrier between a
generated TradePlan and whatever actually places the order.

Design principle (learned the hard way building a live trading autopilot):
guardrails must be validated against the FINAL plan, not just assumed by
whoever built it. A bug in your allocation math should never be able to
place a forbidden order — `validate_plan` re-checks everything from
scratch and raises before a single order reaches your execution layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import AccountState, OrderSide, TradePlan


class GuardrailError(RuntimeError):
    """Raised when a plan would violate a configured guardrail.

    If your planning code is correct this should never fire in practice —
    it's defense in depth, not the primary check. Treat any occurrence as
    a bug worth investigating, not routine control flow.
    """
    def __init__(self, message: str, requires_human_approval: bool = False):
        super().__init__(message)
        self.message = message
        self.requires_human_approval = requires_human_approval

    def to_feedback_prompt(self) -> str:
        """Returns a structured prompt that can be fed back to an LLM for autonomous correction."""
        return (
            "Your proposed trade plan was rejected by the safety guardrails for the following reason:\n"
            f"- {self.message}\n"
            "Please revise your plan to comply with this constraint and try again."
        )


@dataclass
class GuardrailConfig:
    """Every limit is opt-in with a safe default. Nothing trades by
    accident: `allow_sells` defaults to False and `dry_run` defaults to
    True, so a config you haven't touched can only ever simulate buys.
    """

    account_id: str
    allowed_symbols: set[str] = field(default_factory=set)  # empty = deny all buys
    allow_sells: bool = False
    dry_run: bool = True

    min_order_usd: float = 1.0
    max_order_usd: float | None = None
    max_orders_per_run: int = 5

    reserve_cash_usd: float = 0.0
    weekly_cap_usd: float | None = None

    human_approval_threshold_usd: float | None = None
    require_stop_loss_for_buys: bool = False
    max_position_concentration: float | None = None
    shadow_mode: bool = False


def validate_plan(
    plan: TradePlan,
    config: GuardrailConfig,
    account: AccountState,
) -> list[GuardrailError] | None:
    """Validate a TradePlan against a GuardrailConfig.
    
    If config.shadow_mode is False, raises GuardrailError on the first violation.
    If config.shadow_mode is True, returns a list of all GuardrailErrors found, or None if clean.
    Returns None (silently) if the plan is clean and shadow_mode is False.
    """
    errors: list[GuardrailError] = []

    def _fail(msg: str, requires_human: bool = False):
        err = GuardrailError(msg, requires_human_approval=requires_human)
        if not config.shadow_mode:
            raise err
        errors.append(err)

    # Fail closed: wrong account entirely is the single worst failure mode.
    if plan.account_id != config.account_id:
        _fail(
            f"Plan targets account '{plan.account_id}' but GuardrailConfig is "
            f"scoped to '{config.account_id}'. Aborting — this usually means "
            f"the wrong account snapshot was fed into the planner."
        )
    if account.account_id != config.account_id:
        _fail(
            f"AccountState is for '{account.account_id}', not the configured "
            f"'{config.account_id}'. Aborting."
        )

    if len(plan.orders) > config.max_orders_per_run:
        _fail(
            f"{len(plan.orders)} orders exceeds max_orders_per_run="
            f"{config.max_orders_per_run}."
        )

    # For portfolio concentration check
    post_trade_positions = dict(account.positions)

    for o in plan.orders:
        if o.side == OrderSide.SELL and not config.allow_sells:
            _fail(f"{o.symbol}: sell order present but allow_sells=False.")
        
        if o.side == OrderSide.SELL:
            held = account.positions.get(o.symbol, 0.0)
            if held <= 0:
                _fail(f"{o.symbol}: sell order for a position the account doesn't hold.")
            post_trade_positions[o.symbol] = post_trade_positions.get(o.symbol, 0.0) - o.dollar_amount

        if o.side == OrderSide.BUY:
            if o.symbol not in config.allowed_symbols:
                _fail(f"{o.symbol}: not in allowed_symbols whitelist. Buys are deny-by-default.")
            
            if config.require_stop_loss_for_buys and o.stop_loss_price is None:
                _fail(f"{o.symbol}: Buy orders must include a stop_loss_price when require_stop_loss_for_buys=True.")
            
            post_trade_positions[o.symbol] = post_trade_positions.get(o.symbol, 0.0) + o.dollar_amount

        if o.dollar_amount < config.min_order_usd - 1e-9:
            _fail(
                f"{o.symbol}: ${o.dollar_amount:.2f} is below min_order_usd="
                f"${config.min_order_usd:.2f}."
            )
        if config.max_order_usd is not None and o.dollar_amount > config.max_order_usd + 1e-9:
            _fail(
                f"{o.symbol}: ${o.dollar_amount:.2f} exceeds max_order_usd="
                f"${config.max_order_usd:.2f}."
            )
            
        if config.human_approval_threshold_usd is not None and o.dollar_amount > config.human_approval_threshold_usd + 1e-9:
            _fail(
                f"{o.symbol}: ${o.dollar_amount:.2f} exceeds human_approval_threshold_usd="
                f"${config.human_approval_threshold_usd:.2f} and requires manual confirmation.",
                requires_human=True
            )

    # Concentration math
    if config.max_position_concentration is not None:
        total_post_trade_equity = account.buying_power - plan.buy_total + plan.sell_total + sum(post_trade_positions.values())
        if total_post_trade_equity > 0:
            for sym, pos_val in post_trade_positions.items():
                concentration = pos_val / total_post_trade_equity
                if concentration > config.max_position_concentration + 1e-5:
                    _fail(
                        f"{sym}: Post-trade concentration {concentration:.1%} exceeds "
                        f"max_position_concentration={config.max_position_concentration:.1%}."
                    )

    # Cash math: net new spend (buys - sells) can never exceed what's
    # actually spendable once the reserve and weekly cap are honored.
    net_new = plan.buy_total - plan.sell_total
    spendable = account.buying_power - config.reserve_cash_usd
    if config.weekly_cap_usd is not None:
        spendable = min(spendable, config.weekly_cap_usd)
    if net_new > spendable + 1e-9:
        _fail(
            f"Net new spend ${net_new:.2f} (buys ${plan.buy_total:.2f} - sells "
            f"${plan.sell_total:.2f}) exceeds spendable ${spendable:.2f}."
        )

    return errors if (errors and config.shadow_mode) else None
