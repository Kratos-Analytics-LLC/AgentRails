"""Tests for the `agentrails report` CLI over an audit ledger."""

import json
import tempfile
from pathlib import Path

from agentrails import Action, ActionPlan, Ledger
from agentrails.cli import main, summarize


def _seed_ledger(path: Path) -> Ledger:
    led = Ledger(path)
    plan = ActionPlan(
        "agent-1", "run-1", dry_run=False,
        actions=[Action("call", "anthropic", cost=0.4), Action("call", "openai", cost=0.1)],
    )
    led.record_action_plan(plan, status="placed")
    led.record_action(
        scope_id="agent-1", run_label="run-1", target="cohere",
        action_type="call", cost=0.0, status="rejected", note="not allowed",
    )
    led.record_action(
        scope_id="agent-1", run_label="run-1", target="cohere",
        action_type="call", cost=0.0, status="rejected", note="not allowed",
    )
    return led


def test_summarize_counts_and_costs():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "ledger.csv"
        led = _seed_ledger(path)
        s = summarize(led.read_all())
        assert s["total"] == 4
        assert s["by_status"]["placed"] == 2
        assert s["by_status"]["rejected"] == 2
        assert s["executed_count"] == 2
        assert s["executed_cost"] == 0.5
        assert s["blocked_count"] == 2
        assert s["top_blocked"][0] == {"target": "cohere", "blocked": 2}


def test_report_text_output(capsys):
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "ledger.csv"
        _seed_ledger(path)
        rc = main(["report", str(path)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "4 rows" in out
        assert "anthropic" in out
        assert "cohere" in out


def test_report_json_output(capsys):
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "ledger.csv"
        _seed_ledger(path)
        rc = main(["report", str(path), "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["executed_cost"] == 0.5
        assert data["blocked_count"] == 2


def test_report_missing_file_returns_1(capsys):
    rc = main(["report", "/nonexistent/ledger.csv"])
    assert rc == 1
    assert "no such ledger" in capsys.readouterr().err.lower()


def test_empty_ledger_is_handled(capsys):
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "ledger.csv"
        Ledger(path)  # header only, no rows
        rc = main(["report", str(path)])
        assert rc == 0
        assert "0 rows" in capsys.readouterr().out
