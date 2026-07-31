"""Append-only audit trail. Every action an agent ever proposed, dry-ran,
executed, rejected or skipped goes through here — the whole point is that "what
did the agent do and when" is never just a claim in a chat transcript, it's a
line in a file you can open in Excel.

The schema is generic (`target` / `action_type` / `cost`) so it fits any domain.
Trading keeps its old vocabulary through the `record` / `record_plan` helpers,
which map symbol->target, side->action_type, dollar_amount->cost, order_id->ref_id.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

Status = Literal[
    "dry_run", "placed", "filled", "rejected", "skipped", "failed", "shadow"
]

_FIELDS = [
    "timestamp", "scope_id", "run_label", "target", "action_type",
    "cost", "status", "ref_id", "note",
]


@dataclass
class LedgerEntry:
    timestamp: str
    scope_id: str
    run_label: str
    target: str
    action_type: str
    cost: float
    status: Status
    ref_id: str = ""
    note: str = ""


class Ledger:
    """CSV-backed ledger. One file per scope is the recommended setup; nothing
    stops you from pointing several scopes at the same file since `scope_id` is
    always recorded per row.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("w", newline="") as f:
                csv.writer(f).writerow(_FIELDS)

    # --- generic API -------------------------------------------------------

    def record_action(
        self,
        *,
        scope_id: str,
        run_label: str,
        target: str,
        action_type: str,
        cost: float,
        status: Status,
        ref_id: str = "",
        note: str = "",
    ) -> LedgerEntry:
        entry = LedgerEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            scope_id=scope_id,
            run_label=run_label,
            target=target,
            action_type=action_type,
            cost=round(cost, 2),
            status=status,
            ref_id=ref_id,
            note=note,
        )
        with self.path.open("a", newline="") as f:
            csv.writer(f).writerow([getattr(entry, field) for field in _FIELDS])
        return entry

    def record_action_plan(
        self, plan, status: Status, run_label: str | None = None
    ) -> list[LedgerEntry]:
        """Log every action in an ActionPlan (generic core) with the same status
        in one call."""
        label = run_label or plan.generated_for
        return [
            self.record_action(
                scope_id=plan.scope_id,
                run_label=label,
                target=a.target,
                action_type=a.action_type,
                cost=a.cost,
                status=status,
                note=a.reason,
            )
            for a in plan.actions
        ]

    # --- trading aliases (adapter helpers) ---------------------------------

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
        """Trading-flavored convenience that writes the generic schema:
        account_id->scope_id, symbol->target, side->action_type,
        dollar_amount->cost, order_id->ref_id."""
        return self.record_action(
            scope_id=account_id,
            run_label=run_label,
            target=symbol,
            action_type=side,
            cost=dollar_amount,
            status=status,
            ref_id=order_id,
            note=note,
        )

    def record_plan(self, plan, status: Status, run_label: str | None = None) -> list[LedgerEntry]:
        """Log every order in a TradePlan with the same status in one call."""
        label = run_label or plan.generated_for
        return [
            self.record_action(
                scope_id=plan.account_id,
                run_label=label,
                target=o.symbol,
                action_type=o.side.value if hasattr(o.side, "value") else str(o.side),
                cost=o.dollar_amount,
                status=status,
                note=o.reason,
            )
            for o in plan.orders
        ]

    # --- reads -------------------------------------------------------------

    def read_all(self) -> list[dict]:
        with self.path.open("r", newline="") as f:
            return list(csv.DictReader(f))

    def to_json(self) -> str:
        return json.dumps(self.read_all(), indent=2)
