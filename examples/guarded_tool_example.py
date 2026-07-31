"""Reference integration: the low-friction path — a declarative policy file plus
the @guarded decorator, so validation + audit + circuit breaker wrap your
executor automatically.

Unlike the domain examples, this one is fully runnable as-is (no broker, no API,
no shell needed): `python examples/guarded_tool_example.py`.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from agentrails import (
    Action,
    ActionPlan,
    CircuitBreaker,
    Ledger,
    PolicyError,
    guarded,
    load_policy,
)

# ---------------------------------------------------------------------------
# 1. The policy lives in a file, reviewed like code. Here we write one to a temp
#    dir; in practice it's `policy.json` (or .yaml) checked into your repo.
# ---------------------------------------------------------------------------
POLICY_JSON = {
    "scope_id": "research-agent",
    "allowed_targets": ["anthropic", "openai"],
    "dry_run": False,
    "max_cost": 1.00,
    "max_actions_per_run": 20,
    "budget": 5.00,
    "human_approval_threshold": 2.00,
}


def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        policy_path = Path(d) / "policy.json"
        policy_path.write_text(json.dumps(POLICY_JSON, indent=2))

        policy = load_policy(policy_path)
        ledger = Ledger(Path(d) / "ledger.csv")
        breaker = CircuitBreaker(Path(d) / "breaker.json", max_consecutive_failures=5)

        # 2. Wrap the executor. Validation, audit and breaker now happen on every
        #    call; the body only runs if the plan is allowed and the breaker is OK.
        @guarded(policy, ledger=ledger, breaker=breaker)
        def call_apis(plan: ActionPlan) -> str:
            # Your real code would hit the providers here.
            return f"executed {len(plan.actions)} call(s)"

        # 3a. A compliant plan runs.
        ok = ActionPlan("research-agent", "run-1", dry_run=False,
                        actions=[Action("call", "anthropic", cost=0.4, reason="planning")])
        print(call_apis(ok))

        # 3b. A plan that violates the policy is blocked before the body runs.
        bad = ActionPlan("research-agent", "run-1", dry_run=False,
                         actions=[Action("call", "cohere", cost=0.4)])
        try:
            call_apis(bad)
        except PolicyError as e:
            print(f"blocked ({e.code}): {e.message}")

        # 4. Everything is in the audit trail.
        print("\nledger:")
        for row in ledger.read_all():
            print(f"  {row['target']:10} {row['status']}")


if __name__ == "__main__":
    main()
