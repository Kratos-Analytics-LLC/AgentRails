"""Reference integration: putting a safety gate in front of an agent that runs
shell commands.

Like the other examples, this is illustrative, not runnable as-is —
`run_command` stands in for however your agent actually executes a command
(subprocess, a container exec, a remote runner). The control flow is the same
shape as the trading and api_spend examples, even though nothing here is
financial:

    1. Check the circuit breaker — hard stop if too many recent commands failed.
    2. Run YOUR agent logic to produce a CommandPlan (not shown — bring yours).
    3. validate_commands() — hard stop on any policy violation: a non-allowlisted
       binary, a destructive command, a shell-operator injection, too many
       commands.
    4. If dry_run: print the summary (destructive commands are marked) and log it.
       Otherwise run each command, record the result, feed failures to the breaker.

Reminder: this is a tripwire, not a sandbox. Pair it with real OS-level isolation.
"""

from __future__ import annotations

from agentrails import CircuitBreaker, Ledger, PolicyError
from agentrails.adapters.shell import (
    CommandPlan,
    CommandRequest,
    ShellPolicy,
    summarize_plan,
    validate_commands,
)

# ---------------------------------------------------------------------------
# 1. Policy lives in one place, reviewed like code (not edited on a whim).
# ---------------------------------------------------------------------------

POLICY = ShellPolicy(
    scope_id="build-agent",
    allowed_commands={"ls", "cat", "git", "npm", "pytest", "python"},
    dry_run=True,  # flip to False only after you trust the plan output
    allow_destructive=False,  # blocks rm -rf, git push --force, DROP TABLE, ...
    allow_shell_operators=False,  # blocks ; | & ` $( ) and redirects
    max_commands_per_run=10,
)

LEDGER = Ledger("reports/shell_ledger.csv")
BREAKER = CircuitBreaker(
    "reports/shell_breaker.json",
    max_consecutive_failures=5,  # 5 failing commands in a row -> pause
    max_drawdown_pct=1.0,
    cooldown_hours=1,
)


def run_command(cmd: CommandRequest) -> dict:
    """Stand-in for your agent's actual executor (subprocess.run, a container
    exec, ...). AgentRails never runs it for you; it tells you whether you're
    allowed to, you run it."""
    raise NotImplementedError("wire this up to your command runner")


def build_plan_with_your_agent() -> CommandPlan:
    """The one function AgentRails deliberately does NOT provide: your agent
    decides which commands it wants to run. AgentRails' job starts the moment you
    have a CommandPlan."""
    raise NotImplementedError("bring your own agent logic")


def run() -> None:
    if BREAKER.is_tripped():
        print(f"Circuit breaker tripped ({BREAKER.state.reason}); skipping this run.")
        return

    plan = build_plan_with_your_agent()

    try:
        validate_commands(plan, POLICY)
    except PolicyError as e:
        LEDGER.record_action(
            scope_id=POLICY.scope_id,
            run_label=plan.generated_for,
            target=e.target or "-",
            action_type="exec",
            cost=0.0,
            status="rejected",
            note=e.message,
        )
        if e.requires_human_approval:
            print(f"Needs human approval before running: {e}")
        else:
            print(f"Command policy violation, nothing run: {e}")
            print(e.to_feedback_prompt())  # hand back to the agent to revise
        return

    if plan.dry_run:
        print(summarize_plan(plan))
        for c in plan.commands:
            LEDGER.record_action(
                scope_id=POLICY.scope_id,
                run_label=plan.generated_for,
                target=c.executable,
                action_type="exec",
                cost=c.risk,
                status="dry_run",
                note=c.display(),
            )
        return

    for c in plan.commands:
        try:
            result = run_command(c)
        except Exception as exc:
            BREAKER.record_failure()  # grows the streak; trips on the Nth in a row
            LEDGER.record_action(
                scope_id=POLICY.scope_id,
                run_label=plan.generated_for,
                target=c.executable,
                action_type="exec",
                cost=c.risk,
                status="rejected",
                note=f"exec error: {exc}",
            )
            continue

        BREAKER.record_success()  # resets the failure streak
        LEDGER.record_action(
            scope_id=POLICY.scope_id,
            run_label=plan.generated_for,
            target=c.executable,
            action_type="exec",
            cost=c.risk,
            status="filled",
            ref_id=str(result.get("returncode", "")),
            note=c.display(),
        )


if __name__ == "__main__":
    run()
