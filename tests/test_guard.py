"""Tests for the ergonomic Guard / @guarded wrapper: it must enforce the breaker,
the policy and the ledger around an executor, without changing the core."""

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agentrails import (
    Action,
    ActionPlan,
    CircuitBreaker,
    CircuitBreakerTripped,
    Guard,
    Ledger,
    Policy,
    PolicyError,
    guarded,
)


def make_policy(**o):
    base = dict(scope_id="s1", allowed_targets={"a", "b"}, dry_run=False, max_cost=10)
    base.update(o)
    return Policy(**base)


def plan(actions=None, scope="s1"):
    actions = actions if actions is not None else [Action("call", "a", cost=1)]
    return ActionPlan(scope, "run-1", False, actions)


def ledger(d):
    return Ledger(Path(d) / "ledger.csv")


# --- authorize -------------------------------------------------------------


def test_authorize_clean_plan_passes():
    assert Guard(make_policy()).authorize(plan()) is None


def test_authorize_rejects_and_logs():
    with tempfile.TemporaryDirectory() as d:
        led = ledger(d)
        g = Guard(make_policy(), ledger=led)
        with pytest.raises(PolicyError):
            g.authorize(plan([Action("call", "zzz", cost=1)]))  # not allowed
        rows = led.read_all()
        assert rows and rows[0]["status"] == "rejected"


def test_authorize_breaker_tripped_raises_and_logs_skipped():
    with tempfile.TemporaryDirectory() as d:
        led = ledger(d)
        br = CircuitBreaker(Path(d) / "cb.json", max_consecutive_failures=1, cooldown_hours=1)
        br.state.tripped = True
        br.state.tripped_at = datetime.now(timezone.utc).isoformat()
        br.state.reason = "test"
        br._save()
        g = Guard(make_policy(), ledger=led, breaker=br)
        with pytest.raises(CircuitBreakerTripped):
            g.authorize(plan())
        assert led.read_all()[0]["status"] == "skipped"


# --- run -------------------------------------------------------------------


def test_run_dry_run_skips_execution():
    calls = []
    g = Guard(make_policy(dry_run=True))
    result = g.run(plan(), lambda p: calls.append(p) or "ran")
    assert result is None
    assert calls == []  # executor never called in dry-run


def test_run_executes_and_records_success():
    with tempfile.TemporaryDirectory() as d:
        led = ledger(d)
        br = CircuitBreaker(Path(d) / "cb.json", max_consecutive_failures=2)
        br.record_failure()  # streak = 1
        g = Guard(make_policy(dry_run=False), ledger=led, breaker=br)
        result = g.run(plan(), lambda p: "done")
        assert result == "done"
        assert led.read_all()[0]["status"] == "placed"
        assert br.state.consecutive_failures == 0  # success reset the streak


def test_run_records_failure_and_reraises():
    with tempfile.TemporaryDirectory() as d:
        led = ledger(d)
        br = CircuitBreaker(Path(d) / "cb.json", max_consecutive_failures=5)

        def boom(p):
            raise RuntimeError("exec blew up")

        g = Guard(make_policy(dry_run=False), ledger=led, breaker=br)
        with pytest.raises(RuntimeError, match="blew up"):
            g.run(plan(), boom)
        assert br.state.consecutive_failures == 1
        assert led.read_all()[0]["status"] == "failed"


def test_run_rejected_plan_never_executes():
    calls = []
    g = Guard(make_policy())
    with pytest.raises(PolicyError):
        g.run(plan([Action("call", "zzz", cost=1)]), lambda p: calls.append(p))
    assert calls == []


# --- decorator -------------------------------------------------------------


def test_guarded_decorator_happy_path():
    @guarded(make_policy(dry_run=False))
    def execute(p):
        return f"executed {len(p.actions)} actions"

    assert execute(plan()) == "executed 1 actions"


def test_guarded_decorator_blocks_violation():
    @guarded(make_policy())
    def execute(p):
        return "should not run"

    with pytest.raises(PolicyError):
        execute(plan([Action("call", "nope", cost=1)]))


def test_guarded_decorator_dry_run_returns_none():
    ran = []

    @guarded(make_policy(dry_run=True))
    def execute(p):
        ran.append(True)
        return "x"

    assert execute(plan()) is None
    assert ran == []


def test_guarded_passes_through_extra_args():
    @guarded(make_policy(dry_run=False))
    def execute(p, suffix=""):
        return f"ok{suffix}"

    assert execute(plan(), suffix="!") == "ok!"
