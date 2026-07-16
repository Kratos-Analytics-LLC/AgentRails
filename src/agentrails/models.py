"""Broker-agnostic data models.

Nothing here talks to a network, a broker SDK, or an MCP. That's
deliberate: these types are the shared language between (a) whatever
strategy/valuation logic you already have, (b) AgentRails' guardrail
validation, and (c) whatever executes the plan (usually an agent calling
broker MCP tools).
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass
class AccountState:
    """Snapshot of the account a plan is about to act on.

    `account_id` is deliberately opaque (string) so it works whether the
    broker calls it an account number, an account UUID, etc. `positions`
    maps symbol -> current market value in the account's currency.
    """

    account_id: str
    buying_power: float
    positions: dict[str, float] = field(default_factory=dict)


@dataclass
class PlannedOrder:
    symbol: str
    side: OrderSide
    dollar_amount: float
    reason: str = ""
    tag: str = ""  # free-form grouping label (e.g. "core", "rebalance", "dca")
    stop_loss_price: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["side"] = self.side.value
        return d


@dataclass
class TradePlan:
    """A concrete, self-contained set of orders for one account, one run.

    Produced by YOUR strategy code. AgentRails only ever reads this — it
    never builds allocation logic for you, because "what to buy" is the
    one part of this that should stay yours.
    """

    account_id: str
    generated_for: str  # e.g. an ISO date or run label
    dry_run: bool
    orders: list[PlannedOrder] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def orders_total(self) -> float:
        return round(sum(o.dollar_amount for o in self.orders), 2)

    @property
    def buy_total(self) -> float:
        return round(sum(o.dollar_amount for o in self.orders if o.side == OrderSide.BUY), 2)

    @property
    def sell_total(self) -> float:
        return round(sum(o.dollar_amount for o in self.orders if o.side == OrderSide.SELL), 2)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["orders"] = [o.to_dict() for o in self.orders]
        d["orders_total"] = self.orders_total
        return d
