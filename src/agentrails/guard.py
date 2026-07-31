"""Ergonomic one-call integration: bundle a `Policy` with an optional audit
`Ledger` and `CircuitBreaker` so a single call enforces all three — breaker
check, policy validation, and audit logging — around whatever actually executes.

Three levels of ergonomics, pick what fits:

    guard.authorize(plan)          # raise if the plan can't proceed; log it
    guard.run(plan, execute)       # authorize, then dry-run or execute + record
    @guarded(policy, ledger=, breaker=)   # decorate your executor directly

The core (`validate_actions`) stays a pure function; this is a thin, optional
convenience on top for callers who want the whole pass wired for them.
"""

from __future__ import annotations

import functools
from typing import Any, Callable

from .core import ActionPlan, Policy, PolicyError, validate_actions


class CircuitBreakerTripped(RuntimeError):
    """Raised by a Guard when the breaker is tripped, so a pause reads differently
    from a policy rejection (`PolicyError`)."""

    def __init__(self, reason: str):
        super().__init__(f"Circuit breaker tripped: {reason}")
        self.reason = reason


class Guard:
    """A Policy plus an optional Ledger and CircuitBreaker, wired together."""

    def __init__(self, policy: Policy, *, ledger=None, breaker=None):
        self.policy = policy
        self.ledger = ledger
        self.breaker = breaker

    def _log(self, plan: ActionPlan, status: str) -> None:
        if self.ledger is not None:
            self.ledger.record_action_plan(plan, status=status)

    def authorize(self, plan: ActionPlan) -> None:
        """Raise if the plan can't proceed — `CircuitBreakerTripped` if the
        breaker is tripped (logged `skipped`), or `PolicyError` if it violates the
        policy (logged `rejected`). Returns None if the plan is clear.

        Under a shadow-mode policy the core collects violations instead of
        raising: we don't block, but we record them as `shadow` so "what would
        have been rejected" is still auditable rather than silently discarded.
        The plan then proceeds through `run` exactly as a clean one would."""
        if self.breaker is not None and self.breaker.is_tripped():
            self._log(plan, "skipped")
            raise CircuitBreakerTripped(self.breaker.state.reason)
        try:
            violations = validate_actions(plan, self.policy)
        except PolicyError:
            self._log(plan, "rejected")
            raise
        if violations:  # only possible under shadow_mode; observe, don't block
            self._log(plan, "shadow")

    def run(self, plan: ActionPlan, execute: Callable[[ActionPlan], Any]) -> Any:
        """Authorize the plan, then either dry-run (log and skip execution) or run
        `execute(plan)`, recording the outcome to the ledger and the breaker.

        Returns the executor's result, or None in dry-run. In dry-run `execute`
        is never called — that's what dry-run means."""
        self.authorize(plan)

        if self.policy.dry_run:
            self._log(plan, "dry_run")
            return None

        try:
            result = execute(plan)
        except Exception:
            if self.breaker is not None:
                self.breaker.record_failure()
            self._log(plan, "failed")
            raise

        if self.breaker is not None:
            self.breaker.record_success()
        self._log(plan, "placed")
        return result


def guarded(policy: Policy, *, ledger=None, breaker=None):
    """Decorator: wrap an executor `fn(plan, ...)` so every call runs through a
    `Guard` (breaker -> validate -> ledger -> execute). The first positional
    argument must be the `ActionPlan`. In dry-run the wrapped function is not
    called and the call returns None."""
    guard = Guard(policy, ledger=ledger, breaker=breaker)

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(plan: ActionPlan, *args, **kwargs):
            return guard.run(plan, lambda p: fn(p, *args, **kwargs))

        wrapper.guard = guard  # expose the Guard for inspection/testing
        return wrapper

    return decorator


__all__ = ["Guard", "guarded", "CircuitBreakerTripped"]
