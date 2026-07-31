"""Declarative policies: load a `Policy` from JSON or YAML so the rules live in a
config file reviewed like code (versioned, diffable) instead of buried in Python.

JSON works out of the box (stdlib). YAML is optional — install `agentrails[yaml]`
— so the library stays dependency-free by default.

Fails closed on typos: an unknown key in the config is an error, never a silently
ignored limit that would leave you less protected than you thought.
"""

from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path
from typing import Any

from .core import Policy

# Fields on Policy that are sets in Python but lists in JSON/YAML.
_POLICY_SET_FIELDS = {"allowed_targets"}


def policy_from_dict(data: dict[str, Any]) -> Policy:
    """Build a core `Policy` from a plain dict (parsed from JSON/YAML).

    Any key that isn't a Policy field raises `ValueError`, so a misspelled limit
    (`max_costt`, `budjet`) can't be silently dropped."""
    known = {f.name for f in fields(Policy)}
    unknown = set(data) - known
    if unknown:
        raise ValueError(
            f"Unknown policy field(s): {sorted(unknown)}. "
            f"Valid fields: {sorted(known)}."
        )
    kwargs = dict(data)
    for name in _POLICY_SET_FIELDS:
        if name in kwargs and kwargs[name] is not None:
            kwargs[name] = set(kwargs[name])
    return Policy(**kwargs)


def policy_to_dict(policy: Policy) -> dict[str, Any]:
    """Inverse of `policy_from_dict`. Sets become sorted lists so the output is
    stable and diff-friendly."""
    out: dict[str, Any] = {}
    for f in fields(Policy):
        val = getattr(policy, f.name)
        if isinstance(val, set):
            val = sorted(val)
        out[f.name] = val
    return out


def load_policy(path: str | Path) -> Policy:
    """Load a `Policy` from a `.json`, `.yaml` or `.yml` file."""
    path = Path(path)
    text = path.read_text()
    data = _parse_yaml(text) if path.suffix in (".yaml", ".yml") else json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"Policy file {path} must contain a mapping at the top level.")
    return policy_from_dict(data)


def save_policy(policy: Policy, path: str | Path) -> None:
    """Write a `Policy` to a `.json`, `.yaml` or `.yml` file."""
    path = Path(path)
    data = policy_to_dict(policy)
    text = _dump_yaml(data) if path.suffix in (".yaml", ".yml") else json.dumps(data, indent=2)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _require_yaml():
    try:
        import yaml  # noqa: F401
    except ImportError as e:  # pragma: no cover - exercised only without PyYAML
        raise ImportError(
            "YAML support needs PyYAML: `pip install agentrails[yaml]` (or use JSON)."
        ) from e
    return yaml


def _parse_yaml(text: str) -> Any:
    return _require_yaml().safe_load(text)


def _dump_yaml(data: dict[str, Any]) -> str:
    return _require_yaml().safe_dump(data, sort_keys=True)


__all__ = [
    "policy_from_dict",
    "policy_to_dict",
    "load_policy",
    "save_policy",
]
