import asyncio
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext
from plugins.integration.integration_backend.application.service import IntegrationApplication
from plugins.integration.integration_backend.capabilities.contracts import INPUT_SCHEMAS
from plugins.integration.integration_backend.infrastructure.repository import IntegrationRepository


CONTEXT = CapabilityContext(user_gid="actor-1", team_gid="team-1", request_id="mapping-query-1")


class Identity:
    counter = 0

    def new_id(self, kind):
        self.counter += 1
        return f"{kind}-{self.counter}"

    def now(self):
        return datetime(2026, 8, 28, tzinfo=UTC)


class MappingRepository:
    def __init__(self, *, connector_visible=True):
        self.connector_visible = connector_visible
        self.searches = []
        self.runtime_calls = []
        self.operations = {}
        self.connector = {
            "gid": "connector-1", "revision": 1, "name": "ERP", "connector_type": "postgresql",
            "host": "8.8.8.8", "port": 5432, "database_name": "erp", "username": "reader",
            "credential_ref": "vault://private", "status": "untested",
        }
        self.mapping = {
            "gid": "mapping-1", "revision": 3, "datasource_gid": "connector-1", "name": "Parts",
            "source_object": "parts", "target_domain": "knowledge",
            "target_capability_id": "knowledge.reference_dataset.publish", "target_major_version": 1,
            "minimum_catalog_release": "rel_20260828", "status": "active",
            "field_mappings": [{
                "gid": "field-1", "revision": 3, "source_field": "part_no", "target_field": "code",
                "transform_expression": "upper(source.part_no)",
            }],
        }

    def get_connector(self, data):
        self.runtime_calls.append(("connector", dict(data)))
        if not self.connector_visible or data["gid"] != self.connector["gid"]:
            return None
        return {**self.connector, "owner_gid": data["owner_gid"], "team_gid": data.get("team_gid")}

    def get_mapping(self, data):
        self.runtime_calls.append(("mapping", dict(data)))
        if data["gid"] != self.mapping["gid"]:
            return None
        return {**self.mapping, "owner_gid": data["owner_gid"], "team_gid": data.get("team_gid")}

    def search_mappings(self, data):
        self.searches.append(dict(data))
        return [{**self.mapping, "credential_ref": "must-not-leak", "arbitrary_config": {"sql": "secret"}}]

    def search_field_mappings(self, data):
        return list(self.mapping["field_mappings"])

    def claim_operation(self, record):
        self.operations[record.operation_id] = record
        return record, False

    def transition_operation(self, operation_id, _expected_version, replacement, _owner_gid, _team_gid):
        self.operations[operation_id] = replacement
        return replacement


class Runtime:
    def __init__(self):
        self.calls = []

    async def source_columns(self, connector, mapping, *, timeout_seconds, result_limit):
        self.calls.append(("columns", connector, mapping, timeout_seconds, result_limit))
        return {"columns": [
            {"name": "part_no", "data_type": "text", "nullable": False, "credential_ref": "hidden"},
            {"name": "description", "data_type": "text", "nullable": True},
        ]}

    async def preview(self, connector, mapping, *, timeout_seconds, result_limit):
        self.calls.append(("preview", connector, mapping, timeout_seconds, result_limit))
        return {"rows": [
            {"part_no": "P-1", "session_token": "opaque-token"},
            {"part_no": "P-2"},
            {"part_no": "P-3"},
        ], "truncated": False, "credential_ref": "hidden"}


def application(repository=None, runtime=None):
    return IntegrationApplication(
        repository or MappingRepository(), connector_runtime=runtime or Runtime(), operation_identity=Identity()
    )


def test_mapping_search_requires_and_authorizes_the_owned_datasource_gid():
    assert "datasource_gid" in INPUT_SCHEMAS["integration.mapping.search"]["required"]
    with pytest.raises(CapabilityBusinessError) as missing:
        asyncio.run(application().invoke("integration.mapping.search", {"limit": 10}, CONTEXT))
    assert missing.value.code == "invalid_input"

    hidden = MappingRepository(connector_visible=False)
    with pytest.raises(CapabilityBusinessError) as unavailable:
        asyncio.run(application(hidden).invoke(
            "integration.mapping.search", {"datasource_gid": "connector-1", "limit": 10}, CONTEXT
        ))
    assert unavailable.value.code == "resource_not_found"
    assert hidden.searches == []

    visible = MappingRepository()
    result = asyncio.run(application(visible).invoke(
        "integration.mapping.search", {"datasource_gid": "connector-1", "limit": 10}, CONTEXT
    ))
    assert visible.searches == [{
        "datasource_gid": "connector-1", "limit": 10, "owner_gid": "actor-1", "team_gid": "team-1"
    }]
    assert result == {"items": [{
        key: visible.mapping[key] for key in (
            "gid", "revision", "datasource_gid", "name", "source_object", "target_domain",
            "target_capability_id", "target_major_version", "minimum_catalog_release", "status",
        )
    }]}


class SqlCursor:
    def __init__(self, connection):
        self.connection = connection
        self.result = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        self.connection.statements.append((normalized, params))
        if "workmanship_int_ext_field_mappings" in normalized:
            self.result = self.connection.field_rows
        elif "workmanship_int_ext_mappings" in normalized:
            self.result = self.connection.mapping_rows
        else:
            self.result = []

    def fetchone(self):
        return self.result[0] if self.result else None

    def fetchall(self):
        return list(self.result or ())


class SqlConnection:
    def __init__(self):
        self.statements = []
        self.mapping_rows = [{
            "gid": "mapping-1", "revision": 3, "datasource_gid": "connector-1", "name": "Parts",
            "source_object": "parts", "target_domain": "knowledge",
            "target_capability_id": "knowledge.reference_dataset.publish", "target_major_version": 1,
            "minimum_catalog_release": "rel_20260828", "status": "active",
        }]
        self.field_rows = [{
            "gid": "field-1", "revision": 3, "source_field": "part_no", "target_field": "code",
            "transform_expression": None, "mapping_revision": 3,
        }]

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return SqlCursor(self)


def use_connection(monkeypatch, connection):
    @contextmanager
    def fake_connection():
        yield connection

    monkeypatch.setattr(
        "plugins.integration.integration_backend.infrastructure.repository.get_integration_conn",
        fake_connection,
    )


def test_mapping_repository_projects_and_scopes_datasource_search(monkeypatch):
    connection = SqlConnection()
    use_connection(monkeypatch, connection)

    result = IntegrationRepository().search_mappings({
        "datasource_gid": "connector-1", "owner_gid": "actor-1", "team_gid": "team-1", "limit": 7,
    })

    assert result == connection.mapping_rows
    assert len(connection.statements) == 1
    sql, params = connection.statements[0]
    assert "SELECT gid,revision,datasource_gid,name,source_object,target_domain,target_capability_id," in sql
    assert "SELECT *" not in sql
    assert "datasource_gid=%s" in sql and "owner_gid=%s AND team_gid=%s" in sql
    assert params == ("actor-1", "team-1", "connector-1", 7)


def test_field_mapping_repository_uses_one_owned_bounded_collection_query(monkeypatch):
    connection = SqlConnection()
    use_connection(monkeypatch, connection)

    result = IntegrationRepository().search_field_mappings({
        "mapping_gid": "mapping-1", "owner_gid": "actor-1", "team_gid": "team-1", "limit": 4,
    })

    assert result == connection.field_rows
    assert len(connection.statements) == 1
    sql, params = connection.statements[0]
    assert "FROM workmanship_int_ext_mappings m LEFT JOIN workmanship_int_ext_field_mappings f" in sql
    assert "m.owner_gid=%s AND m.team_gid=%s" in sql and "m.archived_at IS NULL" in sql
    assert params == ("mapping-1", "actor-1", "team-1", 4)


def test_field_mapping_repository_distinguishes_hidden_mapping_from_empty_collection(monkeypatch):
    hidden = SqlConnection()
    hidden.field_rows = []
    use_connection(monkeypatch, hidden)
    assert IntegrationRepository().search_field_mappings({
        "mapping_gid": "mapping-hidden", "owner_gid": "actor-1", "team_gid": "team-1", "limit": 4,
    }) is None
    assert len(hidden.statements) == 1

    empty = SqlConnection()
    empty.field_rows = [{
        "gid": None, "revision": None, "source_field": None, "target_field": None,
        "transform_expression": None, "mapping_revision": 3,
    }]
    use_connection(monkeypatch, empty)
    assert IntegrationRepository().search_field_mappings({
        "mapping_gid": "mapping-empty", "owner_gid": "actor-1", "team_gid": "team-1", "limit": 4,
    }) == []
    assert len(empty.statements) == 1


class FieldSearchRepository(MappingRepository):
    def __init__(self, result):
        super().__init__()
        self.result = result
        self.field_searches = []

    def get_mapping(self, _data):
        raise AssertionError("field_mapping.search must not prefetch mapping.get")

    def search_field_mappings(self, data):
        self.field_searches.append(dict(data))
        return self.result


def test_field_mapping_capability_uses_only_the_owned_bounded_collection_path():
    repository = FieldSearchRepository([{
        "gid": "field-1", "revision": 3, "source_field": "part_no", "target_field": "code",
        "transform_expression": None,
    }])

    result = asyncio.run(application(repository).invoke(
        "integration.field_mapping.search", {"mapping_gid": "mapping-1", "limit": 4}, CONTEXT
    ))

    assert result == {"items": [{
        "gid": "field-1", "revision": 3, "source_field": "part_no", "target_field": "code",
    }]}
    assert repository.field_searches == [{
        "mapping_gid": "mapping-1", "limit": 4, "owner_gid": "actor-1", "team_gid": "team-1",
    }]

    hidden = FieldSearchRepository(None)
    with pytest.raises(CapabilityBusinessError) as missing:
        asyncio.run(application(hidden).invoke(
            "integration.field_mapping.search", {"mapping_gid": "mapping-1", "limit": 4}, CONTEXT
        ))
    assert missing.value.code == "resource_not_found"


def test_source_columns_bind_owned_mapping_and_connector_and_return_closed_columns():
    repository = MappingRepository()
    runtime = Runtime()
    result = asyncio.run(application(repository, runtime).invoke(
        "integration.mapping.source_columns.discover", {"mapping_gid": "mapping-1", "limit": 1}, CONTEXT
    ))

    call = runtime.calls[0]
    assert call[0] == "columns" and call[1]["gid"] == "connector-1" and call[2]["gid"] == "mapping-1"
    assert call[4] == 1
    assert result["columns"] == [{"name": "part_no", "data_type": "text", "nullable": False}]
    assert result["operation_ref"]["status"] == "succeeded"
    assert "credential_ref" not in str(result)


def test_preview_is_bounded_redacted_and_reports_structured_outcome():
    result = asyncio.run(application().invoke(
        "integration.mapping.preview", {"gid": "mapping-1", "limit": 2}, CONTEXT
    ))

    assert len(result["rows"]) == 2
    assert result["truncated"] is True
    assert result["operation_ref"]["status"] == "succeeded"
    assert set(result) == {"rows", "truncated", "operation_ref"}
    token = next(cell for cell in result["rows"][0]["values"] if cell["field"] == "session_token")
    assert token == {"field": "session_token", "value": "[REDACTED]", "redacted": True}
    assert "opaque-token" not in str(result)


class TimedOutRuntime(Runtime):
    async def preview(self, *_args, **_kwargs):
        raise TimeoutError("external deadline")


def test_preview_timeout_returns_a_structured_unknown_outcome_without_raw_rows():
    result = asyncio.run(application(runtime=TimedOutRuntime()).invoke(
        "integration.mapping.preview", {"gid": "mapping-1", "limit": 2}, CONTEXT
    ))

    assert result == {
        "rows": [],
        "truncated": False,
        "operation_ref": {"operation_id": "operation-1", "status": "outcome_unknown", "version": 2},
    }
