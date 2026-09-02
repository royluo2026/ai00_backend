from __future__ import annotations

from pathlib import Path

import pytest


EXPECTED_IDS = {
    "craft.resource_requirement.search",
    "craft.resource_requirement.create",
    "craft.resource_requirement.update",
    "craft.resource_requirement.retire",
    "craft.resource_requirement.alias.create",
    "craft.resource_requirement.alias.delete",
    "craft.resource_requirement.staging.search",
    "craft.resource_requirement.staging.resolve",
    "craft.resource_requirement.staging.ignore",
}


class Registry:
    def __init__(self):
        self.items = {}

    def register(self, spec, handler):
        self.items[spec.id] = (spec, handler)


def test_resource_requirement_capabilities_are_atomic_and_paged():
    from plugins.craft.craft_backend.capabilities import resource_requirements

    registry = Registry()
    resource_requirements.register_resource_requirement_capabilities(registry)

    assert set(registry.items) == EXPECTED_IDS
    search, _ = registry.items["craft.resource_requirement.search"]
    assert search.execution_budget.collection_policy.value == "paged"
    assert search.execution_budget.max_page_size == 200
    assert search.input_schema["additionalProperties"] is False
    assert search.input_schema["properties"]["resource_type"]["enum"] == [
        "socket", "tool", "fixture", "equipment",
    ]
    for capability_id in EXPECTED_IDS - {
        "craft.resource_requirement.search",
        "craft.resource_requirement.staging.search",
    }:
        assert registry.items[capability_id][0].risk.value in {"write", "destructive"}


def test_resource_requirement_migration_is_additive_and_versioned():
    sql = Path("backend/db/migrations/domains/craft/0004_resource_requirements.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS `workmanship_craft_resource_requirements`" in sql
    assert "CREATE TABLE IF NOT EXISTS `workmanship_craft_resource_aliases`" in sql
    assert "CREATE TABLE IF NOT EXISTS `workmanship_craft_tc_resource_staging`" in sql
    assert "UNIQUE KEY `uq_craft_resource_type_code` (`resource_type`, `code`)" in sql
    assert "`resource_version` BIGINT NOT NULL DEFAULT 1" in sql
    assert "FROM `workmanship_tpl_vpps_tools`" in sql
    assert "FROM `workmanship_tpl_vpps_fixtures`" in sql
    assert "FROM `workmanship_tpl_vpps_equipments`" in sql
    assert "DROP TABLE" not in sql.upper()


def test_normalization_rejects_blank_values_and_unknown_types():
    from plugins.craft.craft_backend.capabilities import resource_requirements

    assert resource_requirements.normalize_resource_type(" tool ") == "tool"
    assert resource_requirements.normalize_nonblank("  T-01  ", "code", 128) == "T-01"
    with pytest.raises(ValueError, match="resource_type"):
        resource_requirements.normalize_resource_type("factory")
    with pytest.raises(ValueError, match="name"):
        resource_requirements.normalize_nonblank("   ", "name", 255)


def test_socket_need_is_an_independent_tc_resource_node():
    from plugins.craft.craft_backend.capabilities import resource_requirements
    from plugins.craft.craft_backend.routers._bop._constants import _AI00_LEVEL

    assert resource_requirements.TC_RESOURCE_NODES["socket_need"] == ("socket", "resource_socket")
    assert resource_requirements.TC_RESOURCE_NODES["tool_need"] == ("tool", "resource_tool")
    assert _AI00_LEVEL["socket_need"] == _AI00_LEVEL["tool_need"]


def test_update_requires_expected_resource_version():
    from plugins.craft.craft_backend.capabilities import resource_requirements

    with pytest.raises(ValueError, match="expected_resource_version"):
        resource_requirements.update_resource_requirement(
            {"gid": "resource-1", "name": "updated"},
            type("Context", (), {"user_gid": "user-1"})(),
        )


def test_create_rejects_duplicate_type_scoped_code(monkeypatch):
    from backend.capability_v2.provider_contracts import CapabilityBusinessError
    from plugins.craft.craft_backend.capabilities import resource_requirements

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, _sql, _params):
            raise resource_requirements.IntegrityError(1062, "duplicate")

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def cursor(self): return Cursor()
        def commit(self): raise AssertionError("duplicate resource must not commit")

    monkeypatch.setattr(resource_requirements, "get_conn", lambda: Connection())
    monkeypatch.setattr(resource_requirements, "next_gid", lambda: "resource-1")

    with pytest.raises(CapabilityBusinessError) as conflict:
        resource_requirements.create_resource_requirement(
            {"resource_type": "socket", "code": "S-01", "name": "Socket"},
            type("Context", (), {"user_gid": "user-1"})(),
        )
    assert conflict.value.code == "resource_code_conflict"


def test_alias_create_requires_active_resource_and_unique_value(monkeypatch):
    from backend.capability_v2.provider_contracts import CapabilityBusinessError
    from plugins.craft.craft_backend.capabilities import resource_requirements

    class Cursor:
        def __init__(self, resource): self.resource = resource
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, sql, _params):
            if sql.startswith("INSERT"):
                raise resource_requirements.IntegrityError(1062, "duplicate")
        def fetchone(self): return self.resource

    class Connection:
        def __init__(self, resource): self.resource = resource
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def cursor(self): return Cursor(self.resource)
        def commit(self): raise AssertionError("rejected alias must not commit")

    monkeypatch.setattr(resource_requirements, "next_gid", lambda: "alias-1")
    context = type("Context", (), {"user_gid": "user-1"})()

    monkeypatch.setattr(resource_requirements, "get_conn", lambda: Connection(None))
    with pytest.raises(CapabilityBusinessError) as missing:
        resource_requirements.create_resource_alias(
            {"resource_gid": "resource-1", "alias_value": "S one"}, context,
        )
    assert missing.value.code == "resource_not_found"

    monkeypatch.setattr(resource_requirements, "get_conn", lambda: Connection({"gid": "resource-1"}))
    with pytest.raises(CapabilityBusinessError) as duplicate:
        resource_requirements.create_resource_alias(
            {"resource_gid": "resource-1", "alias_value": "S one"}, context,
        )
    assert duplicate.value.code == "resource_alias_conflict"


def test_alias_delete_rejects_wrong_resource(monkeypatch):
    from backend.capability_v2.provider_contracts import CapabilityBusinessError
    from plugins.craft.craft_backend.capabilities import resource_requirements

    class Cursor:
        rowcount = 0
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, _sql, params): assert params == ("alias-1", "resource-2")

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def cursor(self): return Cursor()
        def commit(self): raise AssertionError("wrong resource must not commit")

    monkeypatch.setattr(resource_requirements, "get_conn", lambda: Connection())
    with pytest.raises(CapabilityBusinessError) as missing:
        resource_requirements.delete_resource_alias(
            {"resource_gid": "resource-2", "alias_gid": "alias-1"}, object(),
        )
    assert missing.value.code == "resource_alias_not_found"


def test_staging_decisions_are_separate_capabilities():
    from plugins.craft.craft_backend.capabilities import resource_requirements

    registry = Registry()
    resource_requirements.register_resource_requirement_capabilities(registry)

    resolve_schema = registry.items["craft.resource_requirement.staging.resolve"][0].input_schema
    ignore_schema = registry.items["craft.resource_requirement.staging.ignore"][0].input_schema
    assert "resource_gid" in resolve_schema["required"]
    assert "resource_gid" not in ignore_schema["properties"]
    assert "ignored" not in resolve_schema["properties"]
    assert "ignored" not in ignore_schema["properties"]


def test_authoritative_contracts_match_registered_atomic_schemas():
    from plugins.craft.craft_backend.capabilities import resource_requirements
    from plugins.craft.craft_backend.capabilities.contracts import INPUT_SCHEMAS, OUTPUT_SCHEMAS

    registry = Registry()
    resource_requirements.register_resource_requirement_capabilities(registry)

    for capability_id, (spec, _handler) in registry.items.items():
        assert INPUT_SCHEMAS[(capability_id, 1)] == spec.input_schema
        assert OUTPUT_SCHEMAS[(capability_id, 1)] == spec.output_schema


def test_descriptors_declare_business_purpose_concurrency_and_resource_scope():
    from plugins.craft.craft_backend.capabilities import resource_requirements
    from plugins.craft.craft_backend.capabilities.provider import descriptor_for

    registry = Registry()
    resource_requirements.register_resource_requirement_capabilities(registry)

    update = descriptor_for(registry.items["craft.resource_requirement.update"][0])
    resolve = descriptor_for(registry.items["craft.resource_requirement.staging.resolve"][0])
    search = descriptor_for(registry.items["craft.resource_requirement.search"][0])

    assert "process resource requirement standard" in update.business_effect.lower()
    assert update.concurrency_policy == "expected_version"
    assert update.expected_version_payload_path == "expected_resource_version"
    assert [(item.resource_type, item.payload_path) for item in update.resource_selectors] == [
        ("craft-resource-requirement", "gid")
    ]
    assert resolve.business_invariants
    assert search.no_business_invariant_reason


def test_published_resource_contract_accepts_nonempty_attributes_and_aliases():
    from backend.capability_v2.schema_validation import validate_payload
    from plugins.craft.craft_backend.capabilities import resource_requirements
    from plugins.craft.craft_backend.capabilities.provider import descriptor_for

    registry = Registry()
    resource_requirements.register_resource_requirement_capabilities(registry)
    create = descriptor_for(registry.items["craft.resource_requirement.create"][0])
    search = descriptor_for(registry.items["craft.resource_requirement.search"][0])

    validate_payload(create.input_schema, {
        "resource_type": "tool", "code": "T-01", "name": "Tool 01",
        "attributes": {"gun_model": "G-01"}, "source": "manual",
    })
    validate_payload(search.output_schema, {
        "items": [{
            "gid": "r-1", "resource_type": "tool", "code": "T-01", "name": "Tool 01",
            "attributes": {"gun_model": "G-01"}, "source": "manual", "status": "active",
            "resource_version": 1,
            "aliases": [{
                "gid": "a-1", "resource_gid": "r-1", "alias_value": "枪一",
                "normalized_value": "枪一", "created_at": "2026-09-02T12:00:00",
                "updated_at": "2026-09-02T12:00:00",
            }],
        }],
        "next_cursor": None,
    }, label="output")


def test_published_staging_contract_is_version_scoped_and_accepts_real_rows():
    from backend.capability_v2.schema_validation import validate_payload
    from plugins.craft.craft_backend.capabilities import resource_requirements
    from plugins.craft.craft_backend.capabilities.provider import descriptor_for

    registry = Registry()
    resource_requirements.register_resource_requirement_capabilities(registry)
    staging = descriptor_for(registry.items["craft.resource_requirement.staging.search"][0])

    with pytest.raises(ValueError, match="version_gid"):
        validate_payload(staging.input_schema, {"page_size": 100})
    validate_payload(staging.output_schema, {
        "items": [{
            "gid": "s-1", "version_gid": "v-1", "entry_gid": "e-1",
            "resource_type": "socket", "raw_name": "S-01",
            "raw_payload": {"resource_code": "S-01"}, "match_status": "unmatched",
            "candidate_resource_gids": [], "resolved_resource_gid": None,
            "review_note": None, "resource_version": 1,
            "created_by": "u-1", "decided_by": None, "decided_at": None,
            "created_at": "2026-09-02T12:00:00", "updated_at": "2026-09-02T12:00:00",
        }],
        "next_cursor": None,
    }, label="output")


def test_resource_descriptors_publish_only_reachable_errors_and_real_rules():
    from plugins.craft.craft_backend.capabilities import resource_requirements
    from plugins.craft.craft_backend.capabilities.provider import descriptor_for

    registry = Registry()
    resource_requirements.register_resource_requirement_capabilities(registry)
    descriptors = {capability_id: descriptor_for(spec) for capability_id, (spec, _) in registry.items.items()}
    expected_errors = {
        "craft.resource_requirement.search": {"invalid_page_size"},
        "craft.resource_requirement.create": {"resource_code_conflict"},
        "craft.resource_requirement.update": {"resource_not_found", "resource_code_conflict", "resource_version_conflict"},
        "craft.resource_requirement.retire": {"resource_in_use", "resource_version_conflict"},
        "craft.resource_requirement.alias.create": {"resource_not_found", "resource_alias_conflict"},
        "craft.resource_requirement.alias.delete": {"resource_alias_not_found"},
        "craft.resource_requirement.staging.search": {"invalid_page_size"},
        "craft.resource_requirement.staging.resolve": {
            "resource_staging_not_found", "resource_staging_conflict", "resource_not_found", "resource_type_mismatch",
        },
        "craft.resource_requirement.staging.ignore": {"resource_staging_not_found", "resource_staging_conflict"},
    }
    for capability_id, expected in expected_errors.items():
        descriptor = descriptors[capability_id]
        assert {item.code for item in descriptor.domain_errors} == expected
        assert descriptor.domain_errors_complete is True
        if descriptor.side_effect_level.value != "read":
            assert descriptor.business_invariants
            assert descriptor.no_business_invariant_reason is None

    create = descriptors["craft.resource_requirement.create"]
    assert [(item.resource_type, item.payload_path) for item in create.resource_selectors] == [
        ("craft-resource-requirement-type", "resource_type")
    ]


def test_resolve_replaces_only_the_matching_resource_link(monkeypatch):
    from plugins.craft.craft_backend.capabilities import resource_requirements

    statements = []

    class Cursor:
        rowcount = 1
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, sql, params):
            statements.append((" ".join(sql.split()), params))
        def fetchone(self):
            sql = statements[-1][0]
            if "tc_resource_staging" in sql:
                return {"gid": "s-1", "version_gid": "v-1", "entry_gid": "e-1", "resource_type": "tool", "match_status": "pending", "resource_version": 1}
            if "resource_requirements" in sql:
                return {"gid": "r-1", "resource_type": "tool", "status": "active"}
            return None

    class Connection:
        commits = 0
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def cursor(self): return Cursor()
        def commit(self): self.commits += 1

    connection = Connection()
    monkeypatch.setattr(resource_requirements, "get_conn", lambda: connection)
    monkeypatch.setattr(resource_requirements, "next_gid", lambda: "link-1")

    result = resource_requirements.resolve_resource_staging(
        {"staging_gid": "s-1", "resource_gid": "r-1", "expected_staging_version": 1},
        type("Context", (), {"user_gid": "reviewer-1"})(),
    )

    link_retire = next((sql, params) for sql, params in statements if sql.startswith("UPDATE workmanship_bop_bop_entry_links"))
    assert link_retire[1] == ("e-1", "resource_tool")
    assert result.data["status"] == "resolved"
    assert connection.commits == 1


def test_ignore_removes_only_same_type_provisional_link(monkeypatch):
    from plugins.craft.craft_backend.capabilities import resource_requirements

    statements = []

    class Cursor:
        rowcount = 1
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, sql, params): statements.append((" ".join(sql.split()), params))
        def fetchone(self):
            return {
                "gid": "s-1", "version_gid": "v-1", "entry_gid": "e-1",
                "resource_type": "socket", "match_status": "unmatched", "resource_version": 1,
            }

    class Connection:
        commits = 0
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def cursor(self): return Cursor()
        def commit(self): self.commits += 1

    connection = Connection()
    monkeypatch.setattr(resource_requirements, "get_conn", lambda: connection)

    result = resource_requirements.ignore_resource_staging(
        {"staging_gid": "s-1", "expected_staging_version": 1},
        type("Context", (), {"user_gid": "reviewer-1"})(),
    )

    link_retire = next((sql, params) for sql, params in statements if sql.startswith("UPDATE workmanship_bop_bop_entry_links"))
    assert link_retire[1] == ("e-1", "resource_socket")
    assert not any(sql.startswith("INSERT INTO workmanship_bop_bop_entry_links") for sql, _params in statements)
    assert result.data == {"gid": "s-1", "status": "ignored", "resource_gid": None, "resource_version": 2}
    assert connection.commits == 1


def test_resource_link_validation_rejects_wrong_type_and_retired_rows():
    from backend.capability_v2.provider_contracts import CapabilityBusinessError
    from plugins.craft.craft_backend.capabilities import resource_requirements

    class Cursor:
        def __init__(self, row):
            self.row = row

        def execute(self, _sql, _params):
            return None

        def fetchone(self):
            return self.row

    with pytest.raises(CapabilityBusinessError) as wrong_type:
        resource_requirements.validate_resource_link(
            "resource_tool", "resource-1", Cursor({"resource_type": "fixture", "status": "active"})
        )
    assert wrong_type.value.code == "resource_type_mismatch"

    with pytest.raises(CapabilityBusinessError) as retired:
        resource_requirements.validate_resource_link(
            "resource_tool", "resource-1", Cursor({"resource_type": "tool", "status": "retired"})
        )
    assert retired.value.code == "resource_not_found"


def test_tc_resource_matching_uses_exact_code_or_stages_ambiguous_aliases(monkeypatch):
    from plugins.craft.craft_backend.capabilities import resource_requirements

    class Cursor:
        def __init__(self, exact=None, aliases=()):
            self.exact = exact
            self.aliases = list(aliases)
            self.sql = ""
            self.inserts = []

        def execute(self, sql, params):
            self.sql = " ".join(sql.split())
            if self.sql.startswith("INSERT INTO workmanship_craft_tc_resource_staging"):
                self.inserts.append(params)

        def fetchone(self):
            return self.exact if "BINARY code" in self.sql else None

        def fetchall(self):
            return self.aliases if "craft_resource_aliases" in self.sql else []

    exact = Cursor(exact={"gid": "resource-1"})
    assert resource_requirements.resolve_tc_resource_for_import(
        exact, "version-1", "entry-1", "equipment_need", {"code": "EQ-1"}
    ) == ("resource-1", None)

    ambiguous = Cursor(aliases=({"gid": "resource-1"}, {"gid": "resource-2"}))
    monkeypatch.setattr(resource_requirements, "next_gid", lambda: "staging-1")
    assert resource_requirements.resolve_tc_resource_for_import(
        ambiguous, "version-1", "entry-1", "equipment_need", {"name": "Lift"}
    ) == (None, "staging-1")
    assert ambiguous.inserts
    assert ambiguous.inserts[0][6] == "ambiguous"


def test_retirement_rejects_resources_still_used_by_a_bop():
    from backend.capability_v2.provider_contracts import CapabilityBusinessError
    from plugins.craft.craft_backend.capabilities import resource_requirements

    class Cursor:
        def execute(self, sql, _params): self.sql = sql
        def fetchone(self):
            return {"used": 1} if "bop_entry_links" in self.sql else None

    with pytest.raises(CapabilityBusinessError) as in_use:
        resource_requirements.ensure_resource_not_referenced(Cursor(), "resource-1")
    assert in_use.value.code == "resource_in_use"


def test_search_does_not_run_retirement_reference_guard(monkeypatch):
    from plugins.craft.craft_backend.capabilities import resource_requirements

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, _sql, _params): return None
        def fetchall(self): return []

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def cursor(self): return Cursor()

    monkeypatch.setattr(resource_requirements, "get_conn", lambda: Connection())
    monkeypatch.setattr(
        resource_requirements,
        "ensure_resource_not_referenced",
        lambda *_args: (_ for _ in ()).throw(AssertionError("retirement guard called during search")),
    )

    result = resource_requirements.search_resource_requirements(
        {"resource_type": "socket", "page_size": 5}, object()
    )
    assert result.data == {"items": [], "next_cursor": None}


def test_retire_checks_references_before_updating(monkeypatch):
    from plugins.craft.craft_backend.capabilities import resource_requirements

    checked = []

    class Cursor:
        rowcount = 1
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, _sql, _params): return None

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def cursor(self): return Cursor()
        def commit(self): return None

    monkeypatch.setattr(resource_requirements, "get_conn", lambda: Connection())
    monkeypatch.setattr(
        resource_requirements,
        "ensure_resource_not_referenced",
        lambda _cur, gid: checked.append(gid),
    )

    resource_requirements.retire_resource_requirement(
        {"gid": "resource-1", "expected_resource_version": 1},
        type("Context", (), {"user_gid": "user-1"})(),
    )
    assert checked == ["resource-1"]
