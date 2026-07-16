import tempfile
from pathlib import Path

from agentrails import CircuitBreaker


def test_trips_after_consecutive_losses():
    with tempfile.TemporaryDirectory() as d:
        cb = CircuitBreaker(Path(d) / "cb.json", max_consecutive_losses=3, max_drawdown_pct=0.99)
        cb.update_equity(1000)
        assert not cb.is_tripped()
        for _ in range(3):
            cb.record_trade_result(-10)
        cb.update_equity(970)
        assert cb.is_tripped()


def test_trips_on_drawdown():
    with tempfile.TemporaryDirectory() as d:
        cb = CircuitBreaker(Path(d) / "cb.json", max_consecutive_losses=999, max_drawdown_pct=0.20)
        cb.update_equity(1000)
        cb.update_equity(750)  # -25% from peak
        assert cb.is_tripped()


def test_resets_after_cooldown():
    with tempfile.TemporaryDirectory() as d:
        cb = CircuitBreaker(Path(d) / "cb.json", max_consecutive_losses=1, max_drawdown_pct=0.99, cooldown_hours=0)
        cb.record_trade_result(-5)
        cb.update_equity(995)
        assert cb.is_tripped()
        # cooldown_hours=0 means it should already be eligible to reset on next check
        assert cb.is_tripped() is False


def test_state_persists_across_instances():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "cb.json"
        cb1 = CircuitBreaker(path, max_consecutive_losses=2, max_drawdown_pct=0.99)
        cb1.record_trade_result(-1)
        cb2 = CircuitBreaker(path, max_consecutive_losses=2, max_drawdown_pct=0.99)
        assert cb2.state.consecutive_losses == 1
