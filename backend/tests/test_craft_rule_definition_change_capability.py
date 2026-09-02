from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
import json

import pytest

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext


ALLOWED_CHANGES = {
    "name", "description", "severity", "enabled", "condition", "message",
    "scope", "tags", "priority", "category",
}


def _rule() -> dict:
    return {
        "gid": "rule-1", "owner_user_gid": "owner-1", "team_gid": "team-a",
        "revision": 1, "name": "Original", "description": "old", "severity": "warning",
        "enabled": True, "expression": "quantity > 0", "message": "old message",
        "scope": "team", "tags": ["old"], "priority": 1, "category": "process",
    }


class MemoryRuleDefinitionRepository:
    def __init__(self, rule=None):
        self.rules = {"rule-1": deepcopy(rule or _rule())}
        self.replays = {}
        self.operations = []
        self.audits = []
        self.results = []
        self.commits = 0
        self.rollbacks = 0
        self.fail_after_mutation = False

    def change(self, *, rule_gid, expected_revision, changes, actor_gid, team_gid, idempotency_key, command_digest):
        key = (actor_gid, idempotency_key)
        existing = self.replays.get(key)
        if existing:
            if existing["digest"] != command_digest:
                raise CapabilityBusinessError("idempotency_conflict", "changed command")
            return deepcopy(existing["result"])
        rule = self.rules.get(rule_gid)
        if not rule or rule["owner_user_gid"] != actor_gid or rule["team_gid"] != team_gid:
            raise LookupError("rule not found")
        if rule["revision"] != expected_revision:
            raise CapabilityBusinessError("revision_conflict", "stale rule")
        before = deepcopy(rule)
        try:
            rule.update(changes)
            if "condition" in rule:
                rule["expression"] = rule.pop("condition")
            rule["revision"] += 1
            if self.fail_after_mutation:
                raise RuntimeError("audit unavailable")
            result = {"rule_gid": rule_gid, "revision": rule["revision"], **{
                field: rule.get("expression") if field == "condition" else rule.get(field)
                for field in sorted(ALLOWED_CHANGES)
            }}
            self.operations.append({"rule_gid": rule_gid})
            self.audits.append({"rule_gid": rule_gid})
            self.results.append(deepcopy(result))
            self.replays[key] = {"digest": command_digest, "result": deepcopy(result)}
            self.commits += 1
            return result
        except Exception:
            self.rules[rule_gid] = before
            self.rollbacks += 1
            raise


def _context(*, user_gid="owner-1", team_gid="team-a", key="idem-1"):
    return CapabilityContext(user_gid=user_gid, team_gid=team_gid, idempotency_key=key)


def _payload(changes, *, revision=1):
    return {"rule_gid": "rule-1", "expected_revision": revision, "changes": changes}


def _handler(monkeypatch, repository=None):
    from plugins.craft.craft_backend.capabilities import rule_library

    repository = repository or MemoryRuleDefinitionRepository()
    monkeypatch.setattr(rule_library, "rule_definition_repository", repository)
    return rule_library.change_rule_definition, repository


def _mysql_repository_with_replay(monkeypatch, stored_replay, target_rules):
    from plugins.craft.craft_backend.application import rules

    class Cursor:
        def __init__(self):
            self.replay = stored_replay
            self.rules = deepcopy(target_rules)
            self.current = None

        def __enter__(self): return self
        def __exit__(self, *_): return False
        def execute(self, sql, params=()):
            if "SELECT result_json" in sql:
                self.current = self.replay
            elif "SELECT gid,name" in sql:
                self.current = deepcopy(self.rules.get(params[0]))
            else:
                self.current = None
            self.rowcount = 1
        def fetchone(self): return self.current

    class Connection:
        def __init__(self): self.cursor_value = Cursor()
        def cursor(self): return self.cursor_value
        def commit(self): pass
        def rollback(self): pass

    connection = Connection()
    @contextmanager
    def factory(): yield connection
    monkeypatch.setattr(rules, "get_conn", factory)
    return rules.MysqlRuleDefinitionRepository()


def _stored_rule_replay():
    return {"result_json": json.dumps({
        "actor_gid": "owner-1", "team_gid": "team-a", "rule_gid": "rule-1",
        "command_digest": "digest-1", "result": {"rule_gid": "rule-1", "revision": 2},
    })}


def _stored_rule(rule_gid="rule-1", *, owner="owner-1", team="team-a"):
    return {
        **_rule(), "gid": rule_gid, "owner_user_gid": owner,
        "applicable_scope": {"team_gid": team}, "rule_definition": {"_revision": 1},
    }


@pytest.mark.parametrize("field", sorted(ALLOWED_CHANGES))
def test_rule_definition_change_accepts_each_frozen_field(monkeypatch, field):
    handler, repository = _handler(monkeypatch)
    values = {
        "name": "Renamed", "description": "new", "severity": "block", "enabled": False,
        "condition": "quantity >= 2", "message": "new message", "scope": "project",
        "tags": ["safe", "reviewed"], "priority": 2, "category": "quality",
    }

    result = handler(_payload({field: values[field]}), _context()).data

    assert result[field] == values[field]
    assert result["rule_gid"] == "rule-1"
    assert result["revision"] == 2
    assert repository.commits == 1
    assert len(repository.operations) == len(repository.audits) == len(repository.results) == 1


@pytest.mark.parametrize("changes", [
    {"owner_user_gid": "attacker"},
    {"rule_definition": {"compiled": "payload"}},
    {"condition": {"source": "quantity > 0"}},
    {"condition": "sql.execute('DROP TABLE rules')"},
    {"tags": ["ok", {"audit": "forged"}]},
])
def test_rule_definition_change_rejects_unknown_or_executable_data_before_mutation(monkeypatch, changes):
    handler, repository = _handler(monkeypatch)

    with pytest.raises((CapabilityBusinessError, ValueError)):
        handler(_payload(changes), _context())

    assert repository.rules["rule-1"]["revision"] == 1
    assert repository.commits == repository.rollbacks == 0


def test_rule_definition_change_hides_cross_team_rules(monkeypatch):
    handler, repository = _handler(monkeypatch)

    with pytest.raises(LookupError, match="rule not found"):
        handler(_payload({"name": "nope"}), _context(team_gid="team-b"))

    assert repository.rules["rule-1"]["revision"] == 1


def test_rule_definition_change_rejects_stale_revision_without_writes(monkeypatch):
    handler, repository = _handler(monkeypatch)

    with pytest.raises(CapabilityBusinessError) as raised:
        handler(_payload({"name": "nope"}, revision=7), _context())

    assert raised.value.code == "revision_conflict"
    assert repository.commits == repository.rollbacks == 0


def test_rule_definition_change_rolls_back_mutation_when_audit_persistence_fails(monkeypatch):
    repository = MemoryRuleDefinitionRepository()
    repository.fail_after_mutation = True
    handler, repository = _handler(monkeypatch, repository)

    with pytest.raises(RuntimeError, match="audit unavailable"):
        handler(_payload({"name": "not persisted"}), _context())

    assert repository.rules["rule-1"] == _rule()
    assert repository.commits == 0
    assert repository.rollbacks == 1
    assert repository.operations == repository.audits == repository.results == []


def test_rule_definition_change_replays_the_canonical_result_and_conflicts_on_changed_payload(monkeypatch):
    handler, repository = _handler(monkeypatch)
    first = handler(_payload({"name": "Stable"}), _context()).data
    replay = handler(_payload({"name": "Stable"}), _context()).data

    with pytest.raises(CapabilityBusinessError) as raised:
        handler(_payload({"name": "Changed"}), _context())

    assert replay == first
    assert repository.commits == 1
    assert raised.value.code == "idempotency_conflict"
    assert set(first) == {"rule_gid", "revision", *ALLOWED_CHANGES}
    assert "expression" not in first


def test_mysql_rule_definition_repository_replays_before_revision_check(monkeypatch):
    from plugins.craft.craft_backend.application import rules

    class Cursor:
        def __init__(self):
            self.rule = {
                **_rule(),
                "rule_definition": {"_revision": 1},
                "applicable_scope": {"team_gid": "team-a"},
            }
            self.replay = None
            self.current = None
            self.calls = []

        def __enter__(self): return self
        def __exit__(self, *_): return False
        def execute(self, sql, params=()):
            self.calls.append((" ".join(sql.split()), params))
            if "SELECT result_json" in sql:
                self.current = self.replay
            elif "SELECT gid,name" in sql:
                self.current = deepcopy(self.rule)
            elif sql.startswith("UPDATE workmanship_know_craft_rules"):
                self.rule.update({"name": params[0], "expression": params[1], "rule_definition": json.loads(params[2])})
                self.current = None
            elif "INSERT INTO workmanship_craft_bop_write_idempotency" in sql:
                self.replay = {"result_json": params[3]}
                self.current = None
            else:
                self.current = None
            self.rowcount = 1

        def fetchone(self): return self.current

    class Connection:
        def __init__(self): self.cursor_value = Cursor(); self.commits = self.rollbacks = 0
        def cursor(self): return self.cursor_value
        def commit(self): self.commits += 1
        def rollback(self): self.rollbacks += 1

    connection = Connection()

    @contextmanager
    def factory():
        yield connection

    monkeypatch.setattr(rules, "get_conn", factory)
    repository = rules.MysqlRuleDefinitionRepository()
    first = repository.change(
        rule_gid="rule-1", expected_revision=1, changes={"name": "Stable"},
        actor_gid="owner-1", team_gid="team-a", idempotency_key="idem-1", command_digest="digest-1",
    )
    replay = repository.change(
        rule_gid="rule-1", expected_revision=1, changes={"name": "Stable"},
        actor_gid="owner-1", team_gid="team-a", idempotency_key="idem-1", command_digest="digest-1",
    )

    assert replay == first
    assert connection.commits == 2
    assert connection.rollbacks == 0
    cross_domain_audit_writes = [
        sql for sql, _params in connection.cursor_value.calls
        if "workmanship_app_capability_audit" in sql
    ]
    assert cross_domain_audit_writes == []
    assert sum(sql.startswith("UPDATE workmanship_know_craft_rules") for sql, _ in connection.cursor_value.calls) == 1


def test_mysql_rule_definition_replay_requires_the_current_team_scope(monkeypatch):
    from plugins.craft.craft_backend.application import rules

    class Cursor:
        def __init__(self):
            self.rule = {**_rule(), "applicable_scope": {"team_gid": "team-a"}, "rule_definition": {"_revision": 1}}
            self.replay = None
            self.current = None
            self.rowcount = 1

        def __enter__(self): return self
        def __exit__(self, *_): return False
        def execute(self, sql, params=()):
            if "SELECT result_json" in sql:
                self.current = self.replay
            elif "SELECT gid,name" in sql:
                self.current = deepcopy(self.rule)
            elif sql.startswith("UPDATE workmanship_know_craft_rules"):
                self.rule.update({"name": params[0], "expression": params[1], "rule_definition": json.loads(params[2])})
                self.current = None
            elif "INSERT INTO workmanship_craft_bop_write_idempotency" in sql:
                self.replay = {"result_json": params[3]}
                self.current = None
            else:
                self.current = None

        def fetchone(self): return self.current

    class Connection:
        def __init__(self): self.cursor_value = Cursor()
        def cursor(self): return self.cursor_value
        def commit(self): pass
        def rollback(self): pass

    connection = Connection()
    @contextmanager
    def factory(): yield connection
    monkeypatch.setattr(rules, "get_conn", factory)
    repository = rules.MysqlRuleDefinitionRepository()
    command = dict(rule_gid="rule-1", expected_revision=1, changes={"name": "Stable"}, actor_gid="owner-1", idempotency_key="idem-1", command_digest="digest-1")
    repository.change(**command, team_gid="team-a")

    with pytest.raises(LookupError, match="rule not found"):
        repository.change(**command, team_gid="team-b")


def test_mysql_rule_definition_conflicts_when_an_authorized_other_rule_reuses_key(monkeypatch):
    repository = _mysql_repository_with_replay(
        monkeypatch, _stored_rule_replay(), {"rule-2": _stored_rule("rule-2")},
    )

    with pytest.raises(CapabilityBusinessError) as raised:
        repository.change(
            rule_gid="rule-2", expected_revision=1, changes={"name": "Other"},
            actor_gid="owner-1", team_gid="team-a", idempotency_key="idem-1", command_digest="digest-2",
        )

    assert raised.value.code == "idempotency_conflict"


@pytest.mark.parametrize("target", [
    _stored_rule("team-b-rule", team="team-b"),
    _stored_rule("other-owner-rule", owner="owner-2"),
])
def test_mysql_rule_definition_hides_key_replay_for_cross_team_or_unowned_target(monkeypatch, target):
    repository = _mysql_repository_with_replay(monkeypatch, _stored_rule_replay(), {target["gid"]: target})

    with pytest.raises(LookupError, match="rule not found"):
        repository.change(
            rule_gid=target["gid"], expected_revision=1, changes={"name": "Other"},
            actor_gid="owner-1", team_gid="team-a", idempotency_key="idem-1", command_digest="digest-2",
        )


@pytest.mark.parametrize("stored_scope", [{}, "", "{bad"])
def test_mysql_rule_definition_rejects_empty_or_malformed_team_scope(monkeypatch, stored_scope):
    from plugins.craft.craft_backend.application import rules

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        rowcount = 1
        def execute(self, sql, _params=()):
            self.sql = sql
        def fetchone(self):
            if "result_json" in self.sql:
                return None
            return {**_rule(), "applicable_scope": stored_scope, "rule_definition": {"_revision": 1}}

    class Connection:
        def cursor(self): return Cursor()
        def commit(self): raise AssertionError("must not commit")
        def rollback(self): pass

    @contextmanager
    def factory(): yield Connection()
    monkeypatch.setattr(rules, "get_conn", factory)

    with pytest.raises(LookupError, match="rule not found"):
        rules.MysqlRuleDefinitionRepository().change(
            rule_gid="rule-1", expected_revision=1, changes={"name": "Stable"},
            actor_gid="owner-1", team_gid="team-a", idempotency_key="empty-scope", command_digest="digest",
        )


@pytest.mark.parametrize("condition", [
    "os.system('calc')", "subprocess.call('x')", "open('/secret')", "eval('x')",
    "x => x > 0", "function(x) { return x > 0; }", "quantity > 0; DROP TABLE rules",
    "quantity > 0 // comment", "quantity > 0 /* comment */",
])
def test_rule_definition_change_rejects_non_cel_executable_condition_shapes(monkeypatch, condition):
    handler, repository = _handler(monkeypatch)

    with pytest.raises(ValueError):
        handler(_payload({"condition": condition}), _context())

    assert repository.commits == 0


def test_rule_definition_change_accepts_the_approved_cel_boolean_surface(monkeypatch):
    handler, _repository = _handler(monkeypatch)

    result = handler(_payload({"condition": "quantity >= 2 && enabled"}), _context()).data

    assert result["condition"] == "quantity >= 2 && enabled"


def test_closed_rule_projection_drops_legacy_compiled_and_audit_poison():
    from plugins.craft.craft_backend.application.rules import closed_rule_projection

    projection = closed_rule_projection({
        "gid": "rule-1", "name": {"source": "forged"}, "expression": "open('/secret')",
        "rule_definition": {
            "_revision": "bad", "description": {"compiled": "payload"}, "severity": ["block"],
            "enabled": {"audit": "forged"}, "message": {"source": "leak"}, "scope": {"team_gid": "team-a"},
            "tags": ["safe", {"compiled": "payload"}], "priority": {"audit": 1}, "category": ["process"],
        },
    })

    assert projection == {
        "rule_gid": "rule-1", "revision": 1, "name": "", "description": "", "severity": "",
        "enabled": False, "condition": "", "message": "", "scope": "", "tags": ["safe"],
        "priority": 0, "category": "",
    }


def test_rule_definition_change_registration_is_exact_closed_and_governed():
    from backend.capabilities.registry_next import CapabilityRegistry
    from plugins.craft.craft_backend.capabilities.provider import NativeContractRegistry
    from plugins.craft.craft_backend.capabilities.rule_library import register_rule_definition_change_capability

    registry = CapabilityRegistry()
    register_rule_definition_change_capability(NativeContractRegistry(registry))
    item = registry.get("craft.rule.definition.change.apply", 1)

    assert set(item.spec.input_schema["properties"]) == {"rule_gid", "expected_revision", "changes"}
    assert item.spec.input_schema["required"] == ["rule_gid", "expected_revision", "changes"]
    assert item.spec.input_schema["additionalProperties"] is False
    assert item.spec.input_schema["properties"]["changes"]["additionalProperties"] is False
    assert item.descriptor.concurrency_policy == "expected_version"
    assert item.descriptor.expected_version_payload_path == "expected_revision"
    assert item.descriptor.confirmation_policy == "user"
    assert item.descriptor.idempotency_policy == "required"
