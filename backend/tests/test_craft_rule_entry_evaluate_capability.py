from __future__ import annotations

import importlib
import json
import time

import pytest

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext


def _handler():
    module = importlib.import_module("plugins.craft.craft_backend.capabilities.rule_engine")
    handler = getattr(module, "evaluate_rule_entry", None)
    assert handler is not None, "craft.rule.entry.evaluate must have a provider handler"
    return module, handler


def _rule(*, team_gid: str = "team-a", revision: str = "rev-1"):
    return {
        "gid": "rule-1",
        "team_gid": team_gid,
        "owner_user_gid": "owner-1",
        "share_scope": "team",
        "rule_revision": revision,
        "expression": "quantity > 0",
    }


def _payload(entry=None):
    return {
        "rule_gid": "rule-1",
        "rule_revision": "rev-1",
        "entry": {"quantity": 2} if entry is None else entry,
    }


def _context():
    return CapabilityContext(user_gid="user-1", team_gid="team-a")


def test_rule_entry_evaluation_returns_only_the_closed_result(monkeypatch):
    module, handler = _handler()
    monkeypatch.setattr(module, "load_visible_rule", lambda *_: _rule())
    monkeypatch.setattr(module, "check_rule", lambda *_: (module.RuleResult.PASS, None))

    result = handler(_payload(), _context()).data

    assert result == {"passed": True, "rule_revision": "rev-1", "diagnostics": []}


def test_rule_entry_evaluation_hides_cross_team_rule(monkeypatch):
    from plugins.craft.craft_backend.application import rules

    class Cursor:
        def execute(self, *_args):
            pass

        def fetchone(self):
            return _rule(team_gid="team-b")

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

    class Connection:
        def cursor(self):
            return Cursor()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

    monkeypatch.setattr(rules, "get_conn", lambda: Connection())

    with pytest.raises(LookupError, match="rule not found"):
        rules.load_visible_rule("rule-1", "user-1", "team-a")


def test_rule_entry_evaluation_rejects_wrong_revision(monkeypatch):
    module, handler = _handler()
    monkeypatch.setattr(module, "load_visible_rule", lambda *_: _rule())

    with pytest.raises(CapabilityBusinessError) as raised:
        handler({**_payload(), "rule_revision": "rev-0"}, _context())

    assert raised.value.code == "revision_conflict"


@pytest.mark.parametrize("entry", [
    {"quantity": "x" * 9000},
    {"quantity": {"nested": {"again": {"too": {"deep": True}}}}},
    {"quantity": 2, "expression": "secret()"},
])
def test_rule_entry_evaluation_rejects_unbounded_or_executable_entry(monkeypatch, entry):
    _module, handler = _handler()

    with pytest.raises(ValueError):
        handler(_payload(entry), _context())


def test_rule_entry_evaluation_times_out_without_exposing_checker_text(monkeypatch):
    module, handler = _handler()
    monkeypatch.setattr(module, "load_visible_rule", lambda *_: _rule())
    monkeypatch.setattr(module, "RULE_EVALUATION_TIMEOUT_SECONDS", 0.01)

    def slow_check(*_args):
        time.sleep(0.05)
        return module.RuleResult.FAIL, "expression secret: source code"

    monkeypatch.setattr(module, "check_rule", slow_check)

    result = handler(_payload(), _context()).data

    assert result == {"passed": False, "rule_revision": "rev-1", "diagnostics": [{"code": "evaluation_timeout"}]}
    assert "secret" not in json.dumps(result)
    assert "expression" not in json.dumps(result)


def test_rule_entry_evaluation_caps_diagnostics_and_never_returns_checker_message(monkeypatch):
    module, handler = _handler()
    monkeypatch.setattr(module, "load_visible_rule", lambda *_: _rule())
    monkeypatch.setattr(module, "check_rule", lambda *_: (module.RuleResult.FAIL, "source=hidden; secret=hidden"))

    result = handler(_payload(), _context()).data

    assert result == {"passed": False, "rule_revision": "rev-1", "diagnostics": [{"code": "rule_failed"}]}
    assert set(result) == {"passed", "rule_revision", "diagnostics"}
    assert len(result["diagnostics"]) <= module.MAX_DIAGNOSTICS
    assert all(len(item["code"]) <= module.MAX_DIAGNOSTIC_CODE_LENGTH for item in result["diagnostics"])
    assert "source" not in json.dumps(result)
    assert "secret" not in json.dumps(result)


def test_rule_entry_evaluation_registration_is_exact_and_closed():
    from backend.capabilities.registry_next import CapabilityRegistry
    from plugins.craft.craft_backend.capabilities.rule_engine import register_rule_engine_capability

    registry = CapabilityRegistry()
    register_rule_engine_capability(registry)
    spec = registry.get("craft.rule.entry.evaluate", 1).spec

    assert set(spec.input_schema["properties"]) == {"rule_gid", "rule_revision", "entry"}
    assert spec.input_schema["required"] == ["rule_gid", "rule_revision", "entry"]
    assert spec.input_schema["additionalProperties"] is False
    assert spec.output_schema["required"] == ["passed", "rule_revision", "diagnostics"]
    assert spec.output_schema["additionalProperties"] is False
    assert spec.output_schema["properties"]["diagnostics"]["maxItems"] <= 5
    assert spec.execution_budget.max_input_bytes <= 16 * 1024
    assert spec.execution_budget.max_output_bytes <= 4 * 1024
