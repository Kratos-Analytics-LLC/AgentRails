"""AgentRails command-line interface.

Right now it has one job: turn an audit ledger CSV into a readable summary of what
an agent actually proposed, what got blocked, and what ran — so the append-only
trail is something you look at, not just something you keep.

    agentrails report path/to/ledger.csv
    agentrails report path/to/ledger.csv --json
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

_EXECUTED = {"placed", "filled"}
_BLOCKED = {"rejected", "skipped"}


def _to_float(x: Any) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _read_rows(path: Path) -> list[dict]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def summarize(rows: list[dict]) -> dict[str, Any]:
    """Reduce ledger rows to a summary dict (also the shape of `--json` output)."""
    by_status: Counter[str] = Counter()
    cost_by_status: dict[str, float] = defaultdict(float)
    exec_count_by_target: Counter[str] = Counter()
    exec_cost_by_target: dict[str, float] = defaultdict(float)
    blocked_by_target: Counter[str] = Counter()
    timestamps: list[str] = []
    scopes: set[str] = set()

    for r in rows:
        status = r.get("status", "")
        target = r.get("target", "") or "-"
        cost = _to_float(r.get("cost"))
        by_status[status] += 1
        cost_by_status[status] += cost
        if status in _EXECUTED:
            exec_count_by_target[target] += 1
            exec_cost_by_target[target] += cost
        if status in _BLOCKED:
            blocked_by_target[target] += 1
        if r.get("timestamp"):
            timestamps.append(r["timestamp"])
        if r.get("scope_id"):
            scopes.add(r["scope_id"])

    executed_cost = round(sum(c for s, c in cost_by_status.items() if s in _EXECUTED), 2)
    proposed_cost = round(sum(cost_by_status.values()), 2)

    return {
        "total": len(rows),
        "range": [min(timestamps), max(timestamps)] if timestamps else [],
        "scopes": sorted(scopes),
        "by_status": dict(by_status),
        "cost_by_status": {s: round(c, 2) for s, c in cost_by_status.items()},
        "executed_count": sum(by_status[s] for s in _EXECUTED),
        "executed_cost": executed_cost,
        "blocked_count": sum(by_status[s] for s in _BLOCKED),
        "proposed_cost": proposed_cost,
        "top_targets": [
            {"target": t, "executed_cost": round(c, 2), "count": exec_count_by_target[t]}
            for t, c in sorted(exec_cost_by_target.items(), key=lambda kv: -kv[1])[:5]
        ],
        "top_blocked": [
            {"target": t, "blocked": n}
            for t, n in blocked_by_target.most_common(5)
        ],
    }


def _print_report(path: Path, summary: dict[str, Any]) -> None:
    rng = summary["range"]
    span = f"{rng[0][:19]} → {rng[1][:19]}" if rng else "no dated rows"
    scopes = ", ".join(summary["scopes"]) or "-"
    print(f"AgentRails ledger report — {path}")
    print(f"  {summary['total']} rows · {span} · scopes: {scopes}\n")

    print(f"  {'status':<10} {'count':>7} {'cost':>12}")
    for status, count in sorted(summary["by_status"].items(), key=lambda kv: -kv[1]):
        cost = summary["cost_by_status"].get(status, 0.0)
        cost_str = f"{cost:>12.2f}" if status in _EXECUTED or cost else f"{'—':>12}"
        print(f"  {status:<10} {count:>7} {cost_str}")

    print(
        f"\n  executed (placed+filled): {summary['executed_count']} actions, "
        f"cost {summary['executed_cost']:.2f}"
    )
    print(f"  blocked (rejected+skipped): {summary['blocked_count']} actions")
    print(f"  proposed total cost: {summary['proposed_cost']:.2f}")

    if summary["top_targets"]:
        print("\n  top targets by executed cost:")
        for t in summary["top_targets"]:
            print(f"    {t['target']:<14} {t['count']:>4}x  cost {t['executed_cost']:.2f}")

    if summary["top_blocked"]:
        print("\n  most-blocked targets:")
        for t in summary["top_blocked"]:
            print(f"    {t['target']:<14} {t['blocked']:>4}x")


def cmd_report(args: argparse.Namespace) -> int:
    path = Path(args.ledger)
    if not path.exists():
        print(f"agentrails: no such ledger file: {path}", file=sys.stderr)
        return 1
    rows = _read_rows(path)
    summary = summarize(rows)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        _print_report(path, summary)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentrails", description="AgentRails — safety layer for AI agents."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    rep = sub.add_parser("report", help="Summarize an audit ledger CSV.")
    rep.add_argument("ledger", help="Path to the ledger CSV.")
    rep.add_argument("--json", action="store_true", help="Machine-readable JSON output.")
    rep.set_defaults(func=cmd_report)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
