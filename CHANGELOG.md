# Changelog

All notable changes to AgentRails are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-08-04

The release that turns AgentRails from a trading library into a domain-agnostic
safety layer for AI agents.

### Added

- **Generic core** (`agentrails.core`): `Action`, `ActionPlan`, `Policy`,
  `PolicyContext`, `validate_actions` — domain-agnostic guardrails (allowlist,
  per-action and total-cost limits, actions-per-run, human-approval threshold,
  concentration, irreversibility, shadow mode).
- **Reference adapters** proving the core generalizes across very different
  domains: `adapters.trading` (broker orders), `adapters.api_spend` (paid-API
  budget), `adapters.shell` (command execution — the one that exercises the
  irreversibility primitive, blocking `rm -rf`, `git push --force`, `DROP TABLE`,
  fork bombs, plus a shell-operator injection guard).
- **Declarative policies** (`agentrails.config`): `load_policy` / `save_policy`
  from JSON (stdlib) or YAML (optional `agentrails[yaml]` extra). Fails closed on
  unknown keys.
- **One-line integration** (`agentrails.guard`): `Guard` and the `@guarded`
  decorator wrap an executor with the full pass (circuit breaker → validation →
  ledger → execute). `CircuitBreakerTripped` distinguishes a pause from a
  rejection.
- **Generic MCP gateway** tool `evaluate_actions` alongside the trading
  `evaluate_and_place_trade`; the module imports without the optional `mcp`
  package via a FastMCP shim.
- **CLI**: `agentrails report <ledger.csv>` summarizes proposed vs. blocked vs.
  executed actions, with `--json` output.
- `SECURITY.md` documenting the trust boundary (safety layer, not a sandbox) and
  CI running the test suite on Python 3.10–3.13.

### Changed

- **Ledger** schema is now generic (`target` / `action_type` / `cost` via
  `record_action` / `record_action_plan`); the trading `record` / `record_plan`
  remain as adapter aliases. Added `failed` and `shadow` statuses.
- **CircuitBreaker** base API is generic (`record_failure` / `record_success` /
  `update_value`); a failure now trips on the spot. `record_trade_result` /
  `update_equity` remain as trading aliases, and legacy state files still load.
- README reoriented as "a safety layer for AI agents"; package description and
  keywords generalized away from trading.

### Fixed

- **`Guard` / `@guarded` under a shadow-mode policy** no longer silently
  discards violations. `validate_actions` returns (not raises) in shadow mode, so
  `authorize` used to ignore its result and execute unguarded with no record. It
  now logs would-be rejections as `shadow` while still not blocking, so the
  observation is auditable.
- **`CircuitBreaker.is_tripped()`** no longer crashes on a `tripped` state file
  with no `tripped_at` (hand-edited or partially written). It fails closed:
  starts the cooldown clock and stays paused instead of raising on
  `datetime.fromisoformat(None)`.
- **`agentrails.mcp_server`** no longer creates `reports/` on disk merely by
  being imported. `LEDGER`/`BREAKER` are now built lazily on first use;
  `mcp_server.LEDGER` / `.BREAKER` still work the same way for external callers
  via a module-level `__getattr__`.

### Notes

- Published on PyPI as `kratos-agentrails` (the import name and CLI command
  remain `agentrails`). `requires-python >= 3.10`.
