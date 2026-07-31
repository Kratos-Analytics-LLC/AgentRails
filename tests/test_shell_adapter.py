"""Proves shell/command execution is a genuine third instance of the generic
core, and the one that exercises the irreversibility primitive. Generic
violations (allowlist, commands-per-run, approval) are flagged both by the shell
validator (`validate_commands`) and by the generic engine (`validate_actions`)
on the mapped objects. The destructive-command heuristic and the shell-operator
guard are command-specific and validated only by `validate_commands`."""

import pytest

from agentrails import PolicyError, validate_actions
from agentrails.adapters.shell import (
    CommandPlan,
    CommandRequest,
    ShellPolicy,
    command_to_action,
    destructive_reason,
    plan_to_action_plan,
    policy_to_core_policy,
    summarize_plan,
    validate_commands,
)


def make_policy(**o):
    base = dict(
        scope_id="host-1",
        allowed_commands={"ls", "cat", "git", "rm", "echo"},
        dry_run=True,
        max_commands_per_run=5,
    )
    base.update(o)
    return ShellPolicy(**base)


def make_plan(commands):
    return CommandPlan(scope_id="host-1", generated_for="run-1", commands=commands)


def both_reject(plan, pol):
    """Assert validate_commands raises AND the mapped core also raises."""
    with pytest.raises(PolicyError):
        validate_commands(plan, pol)
    with pytest.raises(PolicyError):
        validate_actions(plan_to_action_plan(plan), policy_to_core_policy(pol))


def both_pass(plan, pol):
    assert validate_commands(plan, pol) is None
    assert validate_actions(plan_to_action_plan(plan), policy_to_core_policy(pol)) is None


# --- mapping ---------------------------------------------------------------


def test_mapping_field_by_field():
    action = command_to_action(CommandRequest("git", ["status"], reason="check"))
    assert action.action_type == "exec"
    assert action.target == "git"
    assert action.reversible is True
    assert action.metadata["argv"] == ["git", "status"]


def test_basename_normalizes_target():
    action = command_to_action(CommandRequest("/usr/bin/ls", ["-la"]))
    assert action.target == "ls"


# --- generic guardrails: flagged by BOTH validators ------------------------


def test_clean_plan_passes_both():
    both_pass(make_plan([CommandRequest("ls", ["-la"])]), make_policy())


def test_command_not_allowed_flagged_by_both():
    both_reject(make_plan([CommandRequest("curl", ["http://x"])]), make_policy())


def test_empty_allowlist_denies_all():
    both_reject(make_plan([CommandRequest("ls")]), make_policy(allowed_commands=set()))


def test_too_many_commands_flagged_by_both():
    cmds = [CommandRequest("ls") for _ in range(6)]
    both_reject(make_plan(cmds), make_policy(max_commands_per_run=5))


def test_human_approval_flag_matches():
    pol = make_policy(human_approval_threshold=1.0)
    plan = make_plan([CommandRequest("git", ["gc"], risk=2.0)])
    with pytest.raises(PolicyError) as e1:
        validate_commands(plan, pol)
    with pytest.raises(PolicyError) as e2:
        validate_actions(plan_to_action_plan(plan), policy_to_core_policy(pol))
    assert e1.value.requires_human_approval is True
    assert e2.value.requires_human_approval is True


# --- destructive heuristic: the irreversibility primitive ------------------


def test_rm_rf_is_destructive_and_blocked():
    # rm -rf is on the allowlist as a command, but it's irreversible, so a policy
    # that doesn't allow destructive commands blocks it.
    plan = make_plan([CommandRequest("rm", ["-rf", "/data"])])
    with pytest.raises(PolicyError) as e:
        validate_commands(plan, make_policy())  # allow_destructive defaults False
    assert e.value.code == "irreversible_blocked"


def test_destructive_allowed_when_configured():
    plan = make_plan([CommandRequest("rm", ["-rf", "/tmp/scratch"])])
    assert validate_commands(plan, make_policy(allow_destructive=True)) is None


@pytest.mark.parametrize(
    "cmd,args",
    [
        ("rm", ["-rf", "/"]),
        ("dd", ["if=/dev/zero", "of=/dev/sda"]),
        ("git", ["push", "--force"]),
        ("psql", ["-c", "DROP TABLE users"]),
    ],
)
def test_known_destructive_patterns_flagged(cmd, args):
    assert destructive_reason(cmd, args) is not None


def test_single_file_rm_is_not_flagged():
    # The heuristic targets high-blast-radius destruction, not every delete.
    assert destructive_reason("rm", ["notes.txt"]) is None


# --- shell-operator guard: command-specific --------------------------------


def test_shell_operator_is_command_specific():
    # Even though `echo` is allowlisted, chaining a second command is blocked...
    plan = make_plan([CommandRequest("echo", ["hi;", "rm", "-rf", "/"])])
    with pytest.raises(PolicyError) as e:
        validate_commands(plan, make_policy())
    assert e.value.code == "shell_operator"
    # ...but the generic core knows nothing about shell operators, so it passes.
    assert validate_actions(plan_to_action_plan(plan), policy_to_core_policy(make_policy())) is None


def test_pipe_and_backtick_blocked():
    for bad in (["a", "|", "b"], ["`whoami`"], ["$(id)"], ["out", ">", "/etc/passwd"]):
        plan = make_plan([CommandRequest("echo", bad)])
        with pytest.raises(PolicyError):
            validate_commands(plan, make_policy())


def test_shell_operators_allowed_when_configured():
    plan = make_plan([CommandRequest("echo", ["a", "|", "b"])])
    assert validate_commands(plan, make_policy(allow_shell_operators=True)) is None


# --- shadow mode -----------------------------------------------------------


def test_shadow_mode_collects_generic_and_command_specific():
    pol = make_policy(allowed_commands={"ls"}, shadow_mode=True)
    plan = make_plan(
        [
            CommandRequest("curl", ["x"]),  # not allowed (generic)
            CommandRequest("echo", ["a;", "b"]),  # shell operator (command-specific)
        ]
    )
    errors = validate_commands(plan, pol)
    assert isinstance(errors, list)
    codes = {e.code for e in errors}
    assert "not_allowed" in codes
    assert "shell_operator" in codes


# --- summary ---------------------------------------------------------------


def test_summary_marks_destructive_without_running():
    plan = make_plan([CommandRequest("ls"), CommandRequest("rm", ["-rf", "/data"])])
    out = summarize_plan(plan)
    assert "DESTRUCTIVE" in out
    assert "rm -rf /data" in out
