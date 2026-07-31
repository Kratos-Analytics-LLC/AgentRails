"""Shell/command execution as a third reference adapter over the generic core.

This is the adapter that finally exercises the core's irreversibility primitive
(`reversible` / `allow_irreversible`), which neither trading nor api_spend needs:
running a shell command is the scariest thing people wire agents to, and the
dangerous part isn't cost — it's that `rm -rf`, `git push --force` or a
`DROP TABLE` can't be undone.

The mapping:

    CommandRequest -> Action(action_type="exec", target=<executable>, reversible=?)
    CommandPlan    -> ActionPlan
    ShellPolicy    -> Policy

Which core primitive does each shell limit become?

    allowed_commands          -> Policy.allowed_targets     (deny-by-default)
    allow_destructive         -> Policy.allow_irreversible
    max_commands_per_run      -> Policy.max_actions_per_run
    max_risk                  -> Policy.max_cost
    human_approval_threshold  -> Policy.human_approval_threshold

Two rules are genuinely command-specific and stay in this adapter (the same way
trading keeps its stop-loss): a **destructive-command heuristic** that marks
`rm -rf`, `dd`, `git push --force`, `DROP TABLE`, a fork bomb, etc. as
`reversible=False` so `allow_destructive=False` blocks them; and a
**shell-operator guard** that rejects arguments carrying `;`, `|`, `&`, backticks
or `$( )`, since command chaining/redirection would smuggle a second command past
the executable allowlist.

Honesty, because this is security tooling: these checks are a **tripwire, not a
sandbox**. They catch the obvious catastrophic patterns and enforce an allowlist;
they do not contain a command that runs, and a determined bypass (unusual quoting,
a renamed binary, an allowed interpreter like `python -c`) can defeat a heuristic.
Use it as one layer, alongside real OS-level isolation — see the project's stance
on "not a sandbox".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..core import (
    Action,
    ActionPlan,
    Policy,
    PolicyError,
    validate_actions,
)

_INHERENTLY_DESTRUCTIVE = {"mkfs", "shred", "fdisk", "dd"}
_SHELL_METACHARS = (";", "|", "&", "`", "$(", ">", "<", "\n")
_DESTRUCTIVE_SQL = ("drop table", "drop database", "truncate table", "delete from")


def _basename(executable: str) -> str:
    return executable.rsplit("/", 1)[-1]


def _short_flag_letters(args: list[str]) -> set[str]:
    """Collect the letters of short flags: ['-rf', '--foo', 'x'] -> {'r', 'f'}."""
    letters: set[str] = set()
    for a in args:
        if a.startswith("-") and not a.startswith("--"):
            letters.update(a[1:])
    return letters


def destructive_reason(executable: str, args: list[str]) -> str | None:
    """Heuristic: a human-readable reason if this command looks irreversible /
    high-blast-radius, else None. Targets catastrophic patterns (recursive
    deletes, disk tools, forced history rewrites, destructive SQL, fork bombs),
    not every irreversible op — a single-file `rm` is not flagged. It errs toward
    flagging, and is a tripwire, not a guarantee."""
    exe = _basename(executable).lower()
    joined = " ".join([exe, *(a.lower() for a in args)])

    if exe in _INHERENTLY_DESTRUCTIVE:
        return f"'{exe}' is an inherently destructive command"
    if exe == "rm" and _short_flag_letters(args) & {"r", "R"}:
        return "recursive delete (rm -r/-rf)"
    if exe == "git" and "push" in args and ("--force" in args or "-f" in args):
        return "git push --force rewrites remote history"
    if any(kw in joined for kw in _DESTRUCTIVE_SQL):
        return "destructive SQL (drop/truncate/delete)"
    if ":(){" in joined or ":|:&" in joined:
        return "fork bomb"
    return None


def _shell_metachar(argv: list[str]) -> str | None:
    """Return the first shell metacharacter found in any token, else None."""
    for token in argv:
        for meta in _SHELL_METACHARS:
            if meta in token:
                return "newline" if meta == "\n" else meta
    return None


@dataclass
class CommandRequest:
    """One command an agent wants to run, already split into an executable and
    its arguments (never a raw shell string — that's the whole point). `risk` is
    an optional scalar for domains that want a per-command ceiling or an approval
    threshold; most policies lean on the allowlist and the destructive check
    instead, so it defaults to 0."""

    executable: str
    args: list[str] = field(default_factory=list)
    risk: float = 0.0
    reason: str = ""
    tag: str = ""

    @property
    def argv(self) -> list[str]:
        return [self.executable, *self.args]

    def display(self) -> str:
        return " ".join(self.argv)


@dataclass
class CommandPlan:
    """The batch of commands one agent run intends to execute, before running
    any of them. Produced by your agent; the adapter only ever reads it."""

    scope_id: str
    generated_for: str
    dry_run: bool = True
    commands: list[CommandRequest] = field(default_factory=list)


@dataclass
class ShellPolicy:
    """Declarative command limits for one run scope. Fails closed: an empty
    `allowed_commands` denies everything, `dry_run` defaults to True, and
    destructive commands are blocked unless `allow_destructive` is set."""

    scope_id: str
    allowed_commands: set[str] = field(default_factory=set)  # empty = deny all
    dry_run: bool = True
    allow_destructive: bool = False  # -> Policy.allow_irreversible
    allow_shell_operators: bool = False  # block ; | & ` $( ) redirects by default
    max_commands_per_run: int = 20
    max_risk: float | None = None  # -> Policy.max_cost
    human_approval_threshold: float | None = None
    shadow_mode: bool = False


# --- mapping onto the generic core ----------------------------------------


def command_to_action(cmd: CommandRequest) -> Action:
    reason = destructive_reason(cmd.executable, cmd.args)
    return Action(
        action_type="exec",
        target=_basename(cmd.executable),
        cost=cmd.risk,
        reversible=reason is None,
        reason=cmd.reason,
        tag=cmd.tag,
        metadata={"argv": cmd.argv, "destructive_reason": reason},
    )


def plan_to_action_plan(plan: CommandPlan) -> ActionPlan:
    return ActionPlan(
        scope_id=plan.scope_id,
        generated_for=plan.generated_for,
        dry_run=plan.dry_run,
        actions=[command_to_action(c) for c in plan.commands],
    )


def policy_to_core_policy(policy: ShellPolicy) -> Policy:
    return Policy(
        scope_id=policy.scope_id,
        allowed_targets=set(policy.allowed_commands),
        dry_run=policy.dry_run,
        max_cost=policy.max_risk,
        max_actions_per_run=policy.max_commands_per_run,
        human_approval_threshold=policy.human_approval_threshold,
        allow_irreversible=policy.allow_destructive,
        shadow_mode=policy.shadow_mode,
    )


# --- canonical shell validator --------------------------------------------


def validate_commands(
    plan: CommandPlan, policy: ShellPolicy
) -> list[PolicyError] | None:
    """Validate a CommandPlan against a ShellPolicy.

    Runs the generic core validation on the mapped plan (executable allowlist,
    commands-per-run, destructive/irreversible block via the heuristic,
    per-command risk ceiling and approval threshold), then applies the
    command-specific shell-operator guard.

    Same contract as `agentrails.core.validate_actions`: raises `PolicyError` on
    the first violation, or — in shadow mode — collects and returns every
    violation, or returns None if the plan is clean.
    """
    core_plan = plan_to_action_plan(plan)
    core_policy = policy_to_core_policy(policy)

    errors = list(validate_actions(core_plan, core_policy) or [])

    if not policy.allow_shell_operators:
        for cmd in plan.commands:
            meta = _shell_metachar(cmd.argv)
            if meta is not None:
                err = PolicyError(
                    f"{cmd.display()}: argument carries shell operator '{meta}' — "
                    "command chaining/redirection is blocked "
                    "(allow_shell_operators=False).",
                    code="shell_operator",
                    target=_basename(cmd.executable),
                )
                if not policy.shadow_mode:
                    raise err
                errors.append(err)

    return errors if (errors and policy.shadow_mode) else None


def summarize_plan(plan: CommandPlan) -> str:
    """Human-readable dry-run summary: exactly what would run, and which commands
    are flagged destructive, without executing a thing."""
    lines = [
        f"Command plan '{plan.generated_for}' (scope {plan.scope_id}) — "
        f"dry_run={plan.dry_run}"
    ]
    for c in plan.commands:
        flag = destructive_reason(c.executable, c.args)
        mark = f"  [DESTRUCTIVE: {flag}]" if flag else ""
        lines.append(f"  $ {c.display()}{mark}")
    lines.append(f"  {len(plan.commands)} command(s)")
    return "\n".join(lines)


__all__ = [
    "CommandRequest",
    "CommandPlan",
    "ShellPolicy",
    "destructive_reason",
    "command_to_action",
    "plan_to_action_plan",
    "policy_to_core_policy",
    "validate_commands",
    "summarize_plan",
]
