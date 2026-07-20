import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agentrails import CircuitBreaker


# --- generic API -----------------------------------------------------------


def test_trips_after_consecutive_failures():
    with tempfile.TemporaryDirectory() as d:
        cb = CircuitBreaker(Path(d) / "cb.json", max_consecutive_failures=3, max_drawdown_pct=0.99)
        assert not cb.is_tripped()
        cb.record_failure()
        cb.record_failure()
        assert not cb.is_tripped()  # only 2 in a row
        cb.record_failure()
        assert cb.is_tripped()  # 3rd trips on the spot, no update_value needed


def test_success_resets_the_streak():
    with tempfile.TemporaryDirectory() as d:
        cb = CircuitBreaker(Path(d) / "cb.json", max_consecutive_failures=2, max_drawdown_pct=0.99)
        cb.record_failure()
        cb.record_success()  # streak back to 0
        cb.record_failure()
        assert not cb.is_tripped()
        assert cb.state.consecutive_failures == 1


def test_trips_on_drawdown():
    with tempfile.TemporaryDirectory() as d:
        cb = CircuitBreaker(Path(d) / "cb.json", max_consecutive_failures=999, max_drawdown_pct=0.20)
        cb.update_value(1000)
        cb.update_value(750)  # -25% from peak
        assert cb.is_tripped()


def test_resets_after_cooldown():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "cb.json"
        cb = CircuitBreaker(path, max_consecutive_failures=1, max_drawdown_pct=0.99, cooldown_hours=1)
        cb.record_failure()
        assert cb.is_tripped()  # tripped; the 1h cooldown hasn't elapsed yet

        # Simulate the cooldown window having passed by backdating the trip time,
        # so the reset logic is tested deterministically (no real waiting).
        cb.state.tripped_at = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        cb._save()

        assert cb.is_tripped() is False  # cooldown elapsed -> auto-reset
        assert cb.state.tripped is False


def test_zero_cooldown_never_blocks():
    # cooldown_hours=0 means "no pause": the trip is eligible to clear on the
    # very next check, so is_tripped() reports False immediately.
    with tempfile.TemporaryDirectory() as d:
        cb = CircuitBreaker(Path(d) / "cb.json", max_consecutive_failures=1, max_drawdown_pct=0.99, cooldown_hours=0)
        cb.record_failure()
        assert cb.is_tripped() is False


def test_state_persists_across_instances():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "cb.json"
        cb1 = CircuitBreaker(path, max_consecutive_failures=2, max_drawdown_pct=0.99)
        cb1.record_failure()
        cb2 = CircuitBreaker(path, max_consecutive_failures=2, max_drawdown_pct=0.99)
        assert cb2.state.consecutive_failures == 1


# --- trading aliases (backward compat) -------------------------------------


def test_trading_aliases_still_work():
    with tempfile.TemporaryDirectory() as d:
        # old kwarg name `max_consecutive_losses` is still accepted
        cb = CircuitBreaker(Path(d) / "cb.json", max_consecutive_losses=3, max_drawdown_pct=0.99)
        cb.update_equity(1000)
        for _ in range(3):
            cb.record_trade_result(-10)  # each is a failure (pnl < 0)
        assert cb.is_tripped()


def test_trade_result_nonnegative_is_success():
    with tempfile.TemporaryDirectory() as d:
        cb = CircuitBreaker(Path(d) / "cb.json", max_consecutive_failures=2, max_drawdown_pct=0.99)
        cb.record_trade_result(-1)
        cb.record_trade_result(0)  # pnl >= 0 counts as success and resets
        assert cb.state.consecutive_failures == 0


def test_loads_legacy_state_keys():
    # A state file written by the old trading-named schema must still load.
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "cb.json"
        path.write_text('{"tripped": false, "consecutive_losses": 2, "peak_equity": 500.0}')
        cb = CircuitBreaker(path, max_consecutive_failures=5)
        assert cb.state.consecutive_failures == 2
        assert cb.state.peak_value == 500.0
