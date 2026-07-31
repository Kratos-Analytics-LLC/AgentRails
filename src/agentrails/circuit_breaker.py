"""Scope-level circuit breaker: pause an agent after a run goes bad, independent
of whatever per-action policy applies. Two orthogonal trip conditions, both
domain-agnostic:

    - N consecutive failures     (`record_failure` / `record_success`)
    - a drawdown past a threshold (`update_value`) — the tracked value drops too
      far from its running peak (portfolio equity, remaining budget, a health
      score, ...).

This is the "the agent is allowed to be wrong on any single action, but must stop
and wait for a human after a bad run" control.

Trading keeps its old vocabulary through thin aliases: `record_trade_result(pnl)`
and `update_equity(equity)` map onto the generic methods, so a "loss" is just a
failure and "equity" is just the tracked value.

Deliberately dumb and file-backed (JSON) so it survives process restarts — a
scheduled agent run that starts fresh each time still remembers it's tripped.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass
class CircuitBreakerState:
    tripped: bool = False
    tripped_at: str | None = None
    reason: str = ""
    consecutive_failures: int = 0
    peak_value: float = 0.0


class CircuitBreaker:
    def __init__(
        self,
        path: str | Path,
        *,
        max_consecutive_failures: int = 5,
        max_drawdown_pct: float = 0.35,
        cooldown_hours: float = 4.0,
        max_consecutive_losses: int | None = None,  # deprecated trading alias
    ):
        self.path = Path(path)
        self.max_consecutive_failures = (
            max_consecutive_losses
            if max_consecutive_losses is not None
            else max_consecutive_failures
        )
        self.max_drawdown_pct = max_drawdown_pct
        self.cooldown_hours = cooldown_hours
        self.state = self._load()

    def _load(self) -> CircuitBreakerState:
        if self.path.exists():
            data = json.loads(self.path.read_text())
            # Tolerate legacy trading-named keys and any unknown/extra keys so an
            # old state file (or a newer one) never crashes the load.
            if "consecutive_losses" in data and "consecutive_failures" not in data:
                data["consecutive_failures"] = data.pop("consecutive_losses")
            if "peak_equity" in data and "peak_value" not in data:
                data["peak_value"] = data.pop("peak_equity")
            known = {f.name for f in fields(CircuitBreakerState)}
            return CircuitBreakerState(**{k: v for k, v in data.items() if k in known})
        return CircuitBreakerState()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(self.state), indent=2))

    def _trip(self, reason: str) -> None:
        if not self.state.tripped:
            self.state.tripped = True
            self.state.tripped_at = datetime.now(timezone.utc).isoformat()
            self.state.reason = reason

    # --- generic API -------------------------------------------------------

    def record_result(self, success: bool) -> None:
        """Record the outcome of one action. A failure grows the streak (and may
        trip on the spot); a success clears it."""
        if success:
            self.state.consecutive_failures = 0
        else:
            self.state.consecutive_failures += 1
            if self.state.consecutive_failures >= self.max_consecutive_failures:
                self._trip(f"{self.state.consecutive_failures} consecutive failures")
        self._save()

    def record_failure(self) -> None:
        self.record_result(False)

    def record_success(self) -> None:
        self.record_result(True)

    def update_value(self, value: float) -> None:
        """Track a value over time and trip if it drops too far from its peak."""
        self.state.peak_value = max(self.state.peak_value, value)
        drawdown = 0.0
        if self.state.peak_value > 0:
            drawdown = (self.state.peak_value - value) / self.state.peak_value
        if drawdown >= self.max_drawdown_pct:
            self._trip(f"drawdown {drawdown:.1%} >= {self.max_drawdown_pct:.1%}")
        self._save()

    # --- trading aliases (adapter helpers) ---------------------------------

    def record_trade_result(self, pnl: float) -> None:
        """Trading view of `record_result`: a non-negative P&L is a success."""
        self.record_result(pnl >= 0)

    def update_equity(self, equity: float) -> None:
        """Trading view of `update_value`."""
        self.update_value(equity)

    # --- status ------------------------------------------------------------

    def is_tripped(self) -> bool:
        """Auto-resets after `cooldown_hours` — a pause-then-resume breaker, not a
        permanent kill switch. `cooldown_hours=0` means no pause at all."""
        if not self.state.tripped:
            return False
        if self.state.tripped_at is None:
            # Inconsistent state (tripped with no timestamp — a hand-edited or
            # partially written file). Fail closed: start the cooldown clock now
            # and stay paused, rather than crash on datetime.fromisoformat(None).
            self.state.tripped_at = datetime.now(timezone.utc).isoformat()
            self._save()
            return True
        tripped_at = datetime.fromisoformat(self.state.tripped_at)
        if datetime.now(timezone.utc) - tripped_at >= timedelta(hours=self.cooldown_hours):
            self.reset()
            return False
        return True

    def reset(self) -> None:
        self.state = CircuitBreakerState(peak_value=self.state.peak_value)
        self._save()
