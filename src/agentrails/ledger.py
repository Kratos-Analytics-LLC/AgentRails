"""Append-only audit trail. Every order ever proposed, dry-run'd, placed,
rejected or skipped goes through here — the whole point is that "what did
the agent do and when" is never just a claim in a chat transcript, it's a
line in a file you can open in Excel.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

Status = Literal["dry_run", "placed", "filled", "rejected", "skipped"]

_FIELDS = [
    "timestamp", "account_id", "run_label", "symbol", "side",
    "dollar_amount", "status", "order_id", "note",
]


@dataclass
class LedgerEntry:
    timestamp: str
    account_id: str
    run_label: str
    symbol: str
    side: str
    dollar_amount: float
    status: Status
    order_id: str = ""
    note: str = ""


class Ledger:
    """CSV-backed ledger. One file per account is the recommended setup;
    nothing stops you from pointing several accounts at the same file
    since `account_id` is always recorded per row.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("w", newline="") as f:
                csv.writer(f).writerow(_FIELDS)

    def record(
        self,
        *,
        account_id: str,
        run_label: str,
        symbol: str,
        side: str,
        dollar_amount: float,
        status: Status,
        order_id: str = "",
        note: str = "",
    ) -> LedgerEntry:
        entry = LedgerEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            account_id=account_id,
            run_label=run_label,
            symbol=symbol,
            side=side,
            dollar_amount=round(dollar_amount, 2),
            status=status,
            order_id=order_id,
            note=note,
        )
        with self.path.open("a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([getattr(entry, field) for field in _FIELDS])
        return entry

    def record_plan(self, plan, status: Status, run_label: str | None = None) -> list[LedgerEntry]:
        """Convenience: log every order in a TradePlan with the same status
        in one call (e.g. the whole plan was dry-run, or the whole plan
        was rejected by a guardrail before execution even started)."""
        label = run_label or plan.generated_for
        return [
            self.record(
                account_id=plan.account_id,
                run_label=label,
                symbol=o.symbol,
                side=o.side.value if hasattr(o.side, "value") else str(o.side),
                dollar_amount=o.dollar_amount,
                status=status,
                note=o.reason,
            )
            for o in plan.orders
        ]

    def read_all(self) -> list[dict]:
        with self.path.open("r", newline="") as f:
            return list(csv.DictReader(f))

    def to_json(self) -> str:
        return json.dumps(self.read_all(), indent=2)
