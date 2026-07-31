"""AgentRails — a domain-agnostic safety layer for AI agents that take real,
consequential actions: spending an API budget, running a command, sending a
message, changing infrastructure, placing an order.

The reusable pattern sits between "the agent decided" and "the action happened":
declarative policy -> validate the proposed actions -> dry-run -> auditable
ledger -> circuit breaker after repeated failures. The generic core
(`Action`, `ActionPlan`, `Policy`, `validate_actions`) knows nothing about any
one domain; thin adapters map a concrete domain onto it — trading is the
reference adapter (`agentrails.adapters.trading`), alongside `api_spend` and
`shell`.

AgentRails does NOT decide *what* to do. It decides what is *allowed* to be done
and writes down everything that happens. This is developer tooling, not
investment (or any other) advice. See README.md.
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
from .config import load_policy, policy_from_dict, policy_to_dict, save_policy
from .guard import CircuitBreakerTripped, Guard, guarded

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
    # Declarative policies (JSON/YAML)
    "policy_from_dict",
    "policy_to_dict",
    "load_policy",
    "save_policy",
    # Ergonomic integration
    "Guard",
    "guarded",
    "CircuitBreakerTripped",
]
