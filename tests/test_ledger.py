import tempfile
from pathlib import Path

from agentrails import Ledger, OrderSide, PlannedOrder, TradePlan


def test_ledger_creates_file_with_header():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "ledger.csv"
        Ledger(path)
        assert path.exists()
        rows = list(path.open())
        assert "timestamp" in rows[0]


def test_ledger_records_entry():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "ledger.csv"
        ledger = Ledger(path)
        entry = ledger.record(
            account_id="acc-1", run_label="2026-07-16", symbol="VOO",
            side="buy", dollar_amount=100, status="placed", order_id="abc123",
        )
        assert entry.symbol == "VOO"
        rows = ledger.read_all()
        assert len(rows) == 1
        assert rows[0]["order_id"] == "abc123"


def test_ledger_records_whole_plan():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "ledger.csv"
        ledger = Ledger(path)
        plan = TradePlan(
            account_id="acc-1",
            generated_for="2026-07-16",
            dry_run=True,
            orders=[
                PlannedOrder("VOO", OrderSide.BUY, 100, reason="core"),
                PlannedOrder("QQQ", OrderSide.BUY, 50, reason="opportunity"),
            ],
        )
        entries = ledger.record_plan(plan, status="dry_run")
        assert len(entries) == 2
        rows = ledger.read_all()
        assert len(rows) == 2
        assert all(r["status"] == "dry_run" for r in rows)
