"""Tests for the reference MCP gateway's GENERIC tool, `evaluate_actions`.

The gateway module imports without the optional `mcp` package (a shim stands in
for FastMCP), so its domain-agnostic safety pass is unit-testable here. This is
the Phase 4 proof that the gateway is no longer trading-only: the same three-step
pass (circuit breaker -> policy -> ledger) now guards arbitrary agent actions.
The trading tool is exercised by the trading/guardrail suites."""

import os
import subprocess
import sys
from datetime import datetime, timezone

import agentrails.mcp_server as gw


def test_import_has_no_disk_side_effect(tmp_path):
    # LEDGER/BREAKER used to be built at import time, which meant merely
    # `import agentrails.mcp_server` created reports/ on disk as a side effect —
    # even from a test collector or a static-analysis tool that never calls a
    # tool. They're now lazy; importing alone must touch nothing.
    result = subprocess.run(
        [sys.executable, "-c", "import agentrails.mcp_server"],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "reports").exists()


def setup_function():
    # Start from a clean breaker so a stale reports/ trip can't leak between runs.
    gw.BREAKER.reset()


def test_clean_plan_succeeds():
    r = gw.evaluate_actions([{"action_type": "call", "target": "anthropic", "cost": 0.40}])
    assert r.startswith("SUCCESS")
    assert "1 actions" in r


def test_target_not_allowed_returns_feedback():
    r = gw.evaluate_actions([{"action_type": "call", "target": "cohere", "cost": 0.10}])
    assert "deny-by-default" in r
    assert "revise" in r.lower()  # it's a self-correction feedback prompt


def test_over_ceiling_rejected():
    r = gw.evaluate_actions([{"action_type": "call", "target": "anthropic", "cost": 1.50}])
    assert "max_cost" in r


def test_human_approval_band():
    # Above the approval threshold but below the hard ceiling -> needs a person.
    r = gw.evaluate_actions([{"action_type": "call", "target": "anthropic", "cost": 0.75}])
    assert "HUMAN APPROVAL" in r


def test_irreversible_blocked():
    r = gw.evaluate_actions(
        [{"action_type": "delete", "target": "search-api", "reversible": False}]
    )
    assert "irreversible" in r


def test_missing_target_is_rejected():
    r = gw.evaluate_actions([{"action_type": "call", "cost": 0.10}])
    assert "missing 'target'" in r


def test_tripped_breaker_refuses_before_policy():
    gw.BREAKER.state.tripped = True
    gw.BREAKER.state.tripped_at = datetime.now(timezone.utc).isoformat()
    gw.BREAKER.state.reason = "test trip"
    gw.BREAKER._save()
    try:
        # Even a perfectly valid plan is refused while the breaker is tripped.
        r = gw.evaluate_actions([{"action_type": "call", "target": "anthropic", "cost": 0.40}])
        assert "TRIPPED" in r
    finally:
        gw.BREAKER.reset()
