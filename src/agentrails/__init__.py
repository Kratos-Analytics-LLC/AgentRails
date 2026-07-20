"""AgentRails — safety rails, dry-run harness and audit ledger for AI agents
that place real orders through a broker MCP (Robinhood, Alpaca, IBKR, or any
other).

AgentRails does NOT decide what to trade. Bring your own strategy/valuation
logic and generate a `TradePlan`; AgentRails validates it against hard,
config-driven guardrails, gives you a dry-run mode to rehearse safely, and
keeps an auditable ledger of every order that was ever proposed or executed.

This is developer tooling, not investment advice. See README.md.
"""

from .models import OrderSide, PlannedOrder, TradePlan, AccountState
from .guardrails import GuardrailConfig, GuardrailError, validate_plan
from .ledger import Ledger, LedgerEntry
from .circuit_breaker import CircuitBreaker, CircuitBreakerState
from .core import (
    Action,
    ActionPlan,
    Policy,
    PolicyContext,
    PolicyError,
    validate_actions,
)

__version__ = "0.1.0"

__all__ = [
    # Trading domain (reference adapter)
    "OrderSide",
    "PlannedOrder",
    "TradePlan",
    "AccountState",
    "GuardrailConfig",
    "GuardrailError",
    "validate_plan",
    # Cross-cutting
    "Ledger",
    "LedgerEntry",
    "CircuitBreaker",
    "CircuitBreakerState",
    # Generic core
    "Action",
    "ActionPlan",
    "Policy",
    "PolicyContext",
    "PolicyError",
    "validate_actions",
]
