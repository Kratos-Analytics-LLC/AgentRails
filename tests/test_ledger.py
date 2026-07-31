import tempfile
from pathlib import Path

from agentrails import Action, ActionPlan, Ledger, OrderSide, PlannedOrder, TradePlan


def test_ledger_creates_file_with_generic_header():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "ledger.csv"
        Ledger(path)
        assert path.exists()
        header = path.open().readline()
        assert "timestamp" in header
        # generic schema, not trading-specific columns
        assert "target" in header and "action_type" in header and "cost" in header
        assert "symbol" not in header and "dollar_amount" not in header


def test_record_action_generic():
    with tempfile.TemporaryDirectory() as d:
        ledger = Ledger(Path(d) / "ledger.csv")
        entry = ledger.record_action(
            scope_id="agent-1", run_label="run-9", target="anthropic",
            action_type="call", cost=0.42, status="dry_run", ref_id="req-1",
        )
        assert entry.target == "anthropic"
        assert entry.cost == 0.42
        rows = ledger.read_all()
        assert len(rows) == 1
        assert rows[0]["target"] == "anthropic"
        assert rows[0]["ref_id"] == "req-1"


def test_record_action_plan_generic():
    with tempfile.TemporaryDirectory() as d:
        ledger = Ledger(Path(d) / "ledger.csv")
        plan = ActionPlan(
            scope_id="agent-1", generated_for="run-9", dry_run=True,
            actions=[Action("call", "anthropic", cost=0.4), Action("send", "openai", cost=0.1)],
        )
        entries = ledger.record_action_plan(plan, status="dry_run")
        assert len(entries) == 2
        rows = ledger.read_all()
        assert [r["target"] for r in rows] == ["anthropic", "openai"]
        assert all(r["status"] == "dry_run" for r in rows)


def test_trading_record_alias_maps_to_generic_schema():
    # The trading-flavored record() is kept as an adapter view: it writes the
    # SAME generic columns (symbol->target, side->action_type, order_id->ref_id).
    with tempfile.TemporaryDirectory() as d:
        ledger = Ledger(Path(d) / "ledger.csv")
        entry = ledger.record(
            account_id="acc-1", run_label="2026-07-16", symbol="VOO",
            side="buy", dollar_amount=100, status="placed", order_id="abc123",
        )
        assert entry.target == "VOO"
        assert entry.action_type == "buy"
        rows = ledger.read_all()
        assert rows[0]["target"] == "VOO"
        assert rows[0]["ref_id"] == "abc123"


def test_record_plan_maps_trade_plan():
    with tempfile.TemporaryDirectory() as d:
        ledger = Ledger(Path(d) / "ledger.csv")
        plan = TradePlan(
            account_id="acc-1", generated_for="2026-07-16", dry_run=True,
            orders=[
                PlannedOrder("VOO", OrderSide.BUY, 100, reason="core"),
                PlannedOrder("QQQ", OrderSide.BUY, 50, reason="opportunity"),
            ],
        )
        entries = ledger.record_plan(plan, status="dry_run")
        assert len(entries) == 2
        rows = ledger.read_all()
        assert [r["target"] for r in rows] == ["VOO", "QQQ"]
        assert all(r["status"] == "dry_run" for r in rows)
