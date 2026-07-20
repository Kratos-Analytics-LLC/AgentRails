"""Tests for declarative policies: dict/JSON/YAML round-trips and fail-closed
handling of unknown keys."""

import json
import tempfile
from pathlib import Path

import pytest

from agentrails import (
    Policy,
    load_policy,
    policy_from_dict,
    policy_to_dict,
    save_policy,
    validate_actions,
)
from agentrails import Action, ActionPlan


def test_policy_from_dict_basic():
    p = policy_from_dict(
        {"scope_id": "s1", "allowed_targets": ["a", "b"], "max_cost": 10, "dry_run": False}
    )
    assert isinstance(p, Policy)
    assert p.allowed_targets == {"a", "b"}  # list -> set
    assert p.max_cost == 10
    assert p.dry_run is False


def test_unknown_key_fails_closed():
    with pytest.raises(ValueError, match="Unknown policy field"):
        policy_from_dict({"scope_id": "s1", "budjet": 100})  # typo


def test_missing_required_scope_id_raises():
    with pytest.raises(TypeError):
        policy_from_dict({"allowed_targets": ["a"]})


def test_dict_round_trip():
    p = Policy(scope_id="s1", allowed_targets={"b", "a"}, max_cost=5.0, budget=20.0)
    d = policy_to_dict(p)
    # sets serialize as sorted lists for stable diffs
    assert d["allowed_targets"] == ["a", "b"]
    assert policy_from_dict(d) == p


def test_json_file_round_trip():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "policy.json"
        p = Policy(scope_id="agent", allowed_targets={"anthropic"}, max_cost=1.0, budget=5.0)
        save_policy(p, path)
        assert json.loads(path.read_text())["allowed_targets"] == ["anthropic"]
        assert load_policy(path) == p


def test_loaded_policy_actually_enforces():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "policy.json"
        path.write_text(json.dumps({"scope_id": "s1", "allowed_targets": ["a"], "max_cost": 1.0}))
        policy = load_policy(path)
        plan = ActionPlan("s1", "r", True, [Action("call", "a", cost=99)])
        with pytest.raises(Exception):  # over max_cost
            validate_actions(plan, policy)


def test_non_mapping_file_rejected():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "policy.json"
        path.write_text("[1, 2, 3]")
        with pytest.raises(ValueError, match="mapping"):
            load_policy(path)


def test_yaml_round_trip_if_available():
    yaml = pytest.importorskip("yaml")  # optional dependency
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "policy.yaml"
        p = Policy(scope_id="agent", allowed_targets={"x"}, max_cost=2.0)
        save_policy(p, path)
        loaded = yaml.safe_load(path.read_text())
        assert loaded["allowed_targets"] == ["x"]
        assert load_policy(path) == p
