"""Account-level circuit breaker: pause new entries after a losing streak
or a drawdown past a threshold, independent of whatever guardrails apply
to individual orders. This is the "the agent is allowed to be wrong on
any single trade, but must stop and wait for a human after a bad run"
control.

Deliberately dumb and file-backed (JSON) so it survives process restarts
— a scheduled agent run that starts fresh each time still remembers it's
tripped.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass
class CircuitBreakerState:
    tripped: bool = False
    tripped_at: str | None = None
    reason: str = ""
    consecutive_losses: int = 0
    peak_equity: float = 0.0


class CircuitBreaker:
    def __init__(
        self,
        path: str | Path,
        *,
        max_consecutive_losses: int = 5,
        max_drawdown_pct: float = 0.35,
        cooldown_hours: float = 4.0,
    ):
        self.path = Path(path)
        self.max_consecutive_losses = max_consecutive_losses
        self.max_drawdown_pct = max_drawdown_pct
        self.cooldown_hours = cooldown_hours
        self.state = self._load()

    def _load(self) -> CircuitBreakerState:
        if self.path.exists():
            data = json.loads(self.path.read_text())
            return CircuitBreakerState(**data)
        return CircuitBreakerState()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(self.state), indent=2))

    def record_trade_result(self, pnl: float) -> None:
        if pnl < 0:
            self.state.consecutive_losses += 1
        else:
            self.state.consecutive_losses = 0
        self._save()

    def update_equity(self, equity: float) -> None:
        self.state.peak_equity = max(self.state.peak_equity, equity)
        drawdown = 0.0
        if self.state.peak_equity > 0:
            drawdown = (self.state.peak_equity - equity) / self.state.peak_equity

        if (
            self.state.consecutive_losses >= self.max_consecutive_losses
            or drawdown >= self.max_drawdown_pct
        ):
            if not self.state.tripped:
                self.state.tripped = True
                self.state.tripped_at = datetime.now(timezone.utc).isoformat()
                self.state.reason = (
                    f"{self.state.consecutive_losses} consecutive losses"
                    if self.state.consecutive_losses >= self.max_consecutive_losses
                    else f"drawdown {drawdown:.1%} >= {self.max_drawdown_pct:.1%}"
                )
        self._save()

    def is_tripped(self) -> bool:
        """Auto-resets after `cooldown_hours` — same pattern as F9 in a
        pause-then-resume circuit breaker, not a permanent kill switch."""
        if not self.state.tripped:
            return False
        tripped_at = datetime.fromisoformat(self.state.tripped_at)
        if datetime.now(timezone.utc) - tripped_at >= timedelta(hours=self.cooldown_hours):
            self.reset()
            return False
        return True

    def reset(self) -> None:
        self.state = CircuitBreakerState(peak_equity=self.state.peak_equity)
        self._save()
