# Security policy

AgentRails is a **safety layer**, not a sandbox. Being honest about that boundary
is part of using it safely — it changes what you should and shouldn't rely on it
for.

## What AgentRails protects

- **Policy enforcement on declared plans.** Given an `ActionPlan` and a `Policy`,
  `validate_actions` deterministically enforces the allowlist, per-action and
  total-cost limits, action count, human-approval threshold, concentration and
  irreversibility — re-checked against the *final* plan, right before execution.
- **An audit trail.** Every proposed, dry-run, executed, rejected, skipped or
  failed action is appended to the ledger, so "what did the agent do" is a file,
  not a claim in a chat transcript.
- **A pause switch.** The circuit breaker halts new actions after a streak of
  failures or a drawdown, and survives process restarts.

## What AgentRails does NOT protect against

This is the important half.

- **It is not a sandbox.** It does not isolate, contain, or intercept execution.
  If a command passes the policy and your code runs it, AgentRails has no further
  control over what that command does. Pair it with real OS-level isolation
  (containers, seccomp, VMs, least-privilege credentials).
- **It only sees what it's given.** AgentRails validates the plan the agent
  *declares*. An agent (or a bug) that performs a side effect **without routing it
  through AgentRails** is completely unguarded. The library is a gate you must
  choose to walk your actions through; it cannot guard a path it never sees.
- **Garbage in, limited protection.** The checks are only as good as the inputs:
  a wrong `cost` estimate, a mislabeled `reversible` flag, or a `scope_id`
  mismatch weakens the corresponding limit. Feed it accurate plans.
- **Heuristics are tripwires, not guarantees.** The shell adapter's
  destructive-command and shell-operator detection catches common catastrophic
  patterns (`rm -rf`, `git push --force`, `DROP TABLE`, piping). It can be
  defeated by unusual quoting, a renamed binary, or an allowed interpreter
  (`python -c`, `bash -c`). Treat the executable allowlist as the real control
  and the heuristic as a helpful extra.
- **It holds no credentials and makes no calls.** It never talks to the network.
  Securing your API keys, broker credentials and execution environment is on you
  (see the README's "Secrets" section).

## Trust model, in one line

AgentRails reduces the blast radius of an agent that *tries* to do the right thing
and routes its actions through the gate. It is defense-in-depth, not a boundary
you can put an untrusted adversary behind.

## Reporting a vulnerability

If you find a security issue in AgentRails itself (e.g. a policy that can be
bypassed with inputs it claims to reject, or a validator that fails open), please
report it privately via this repository's **GitHub Security Advisories**
("Security" tab → "Report a vulnerability") rather than opening a public issue.
Include a minimal reproduction and the version/commit. We'll acknowledge and work
a fix before any public disclosure.

Please do **not** report issues that amount to "AgentRails didn't stop a command
it never received" or "a heuristic was bypassed" — those are documented limits
above, not defects.
