import asyncio
import json
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext
from plugins.integration.integration_backend.application.operations import IntegrationOperation, IntegrationOperations
from plugins.integration.integration_backend.application.service import IntegrationApplication
from plugins.integration.integration_backend.infrastructure.repository import IntegrationRepository


NOW = datetime(2026, 8, 28, tzinfo=UTC)
CONTEXT = CapabilityContext(user_gid="actor-1", team_gid="team-1", request_id="fix-request")


class Identity:
    def __init__(self):
        self.counter = 0

    def new_id(self, kind):
        self.counter += 1
        return f"{kind}-{self.counter}"

    def now(self):
        return NOW


class AtomicStore:
    def __init__(self):
        self.record = None

    def claim_operation(self, record):
        if self.record is not None:
            return self.record, True
        self.record = record
        return record, False

    def claim_import_operation(self, record, _run):
        return self.claim_operation(record)

    def get_operation(self, operation_id, owner_gid, team_gid):
        if (
            self.record is not None
            and self.record.operation_id == operation_id
            and self.record.owner_gid == owner_gid
            and self.record.team_gid == team_gid
        ):
            return self.record
        return None

    def transition_operation(self, operation_id, expected_version, replacement, owner_gid, team_gid):
        current = self.get_operation(operation_id, owner_gid, team_gid)
        if current is None or current.version != expected_version:
            from plugins.integration.integration_backend.application.ports import RevisionConflict

            raise RevisionConflict("operation")
        self.record = replacement
        return replacement


def operation(**changes):
    values = {
        "operation_id": "operation-1",
        "owner_gid": "actor-1",
        "team_gid": "team-1",
        "capability_id": "integration.mapping.import.start",
        "idempotency_key": "import-1",
        "payload_hash": "a" * 64,
        "status": "accepted",
        "version": 1,
        "result": {"run_id": "run-1"},
        "error_code": None,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(changes)
    return IntegrationOperation(**values)


def import_row(**changes):
    values = {
        "run_id": "run-1",
        "mapping_gid": "mapping-1",
        "operation_id": "operation-1",
        "status": "accepted",
        "target_capability_id": "knowledge.reference_dataset.publish",
        "target_major_version": 1,
        "catalog_release": "rel_20260828",
        "owner_gid": "actor-1",
        "team_gid": "team-1",
        "idempotency_key": "import-1",
        "target_invocation": {},
    }
    values.update(changes)
    return values


def test_atomic_claim_replays_winner_and_compares_payload_and_team():
    store = AtomicStore()
    operations = IntegrationOperations(store, identity=Identity())
    first = operations.start(
        capability_id="integration.mapping.create", payload={"name": "Parts"},
        owner_gid="actor-1", team_gid="team-1", idempotency_key="mapping-1",
    )
    replay = operations.start(
        capability_id="integration.mapping.create", payload={"name": "Parts"},
        owner_gid="actor-1", team_gid="team-1", idempotency_key="mapping-1",
    )
    assert replay.replayed is True and replay.record == first.record

    with pytest.raises(CapabilityBusinessError) as payload_conflict:
        operations.start(
            capability_id="integration.mapping.create", payload={"name": "Other"},
            owner_gid="actor-1", team_gid="team-1", idempotency_key="mapping-1",
        )
    assert payload_conflict.value.code == "idempotency_conflict"
    with pytest.raises(CapabilityBusinessError) as team_conflict:
        operations.start(
            capability_id="integration.mapping.create", payload={"name": "Parts"},
            owner_gid="actor-1", team_gid="team-2", idempotency_key="mapping-1",
        )
    assert team_conflict.value.code == "idempotency_conflict"


def test_import_run_identity_survives_unknown_and_scoped_reconciliation():
    store = AtomicStore()
    operations = IntegrationOperations(store, identity=Identity())
    claim = operations.start_import(
        capability_id="integration.mapping.import.start", payload={"mapping_gid": "mapping-1"},
        owner_gid="actor-1", team_gid="team-1", idempotency_key="import-1",
        run=import_row(),
    )
    unknown = operations.outcome_unknown(claim.record, error_code="external_timeout")
    assert unknown.result == {"run_id": "run-1"}

    with pytest.raises(CapabilityBusinessError) as hidden:
        operations.reconcile(
            unknown.operation_id, "succeeded", owner_gid="actor-2", team_gid="team-1",
            expected_version=unknown.version, result={"imported_count": 4},
        )
    assert hidden.value.code == "resource_not_found"
    succeeded = operations.reconcile(
        unknown.operation_id, "succeeded", owner_gid="actor-1", team_gid="team-1",
        expected_version=unknown.version, result={"imported_count": 4},
    )
    assert succeeded.result == {"run_id": "run-1", "imported_count": 4}


class DuplicateKey(RuntimeError):
    pass


class ScriptedCursor:
    def __init__(self, connection):
        self.connection = connection
        self.rowcount = 1
        self.result = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        self.connection.statements.append((normalized, params))
        if self.connection.fail_on and self.connection.fail_on in normalized:
            raise self.connection.failure
        self.result = self.connection.results.pop(0) if normalized.startswith("SELECT") and self.connection.results else None

    def fetchone(self):
        return self.result

    def fetchall(self):
        return list(self.result or ())


class ScriptedConnection:
    def __init__(self, *, fail_on=None, failure=None, results=()):
        self.fail_on = fail_on
        self.failure = failure or RuntimeError("scripted failure")
        self.results = list(results)
        self.statements = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return ScriptedCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def connection_sequence(monkeypatch, *connections):
    queue = iter(connections)

    @contextmanager
    def connect():
        connection = next(queue)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    monkeypatch.setattr(
        "plugins.integration.integration_backend.infrastructure.repository.get_integration_conn", connect
    )


def operation_db_row(**changes):
    record = operation()
    row = {
        "operation_id": record.operation_id,
        "owner_gid": record.owner_gid,
        "team_gid": record.team_gid,
        "capability_id": record.capability_id,
        "idempotency_key": record.idempotency_key,
        "payload_hash": record.payload_hash,
        "status": record.status,
        "operation_version": record.version,
        "result_json": '{"run_id":"run-1"}',
        "error_code": None,
        "created_at": NOW,
        "updated_at": NOW,
    }
    row.update(changes)
    return row


def test_sql_operation_claim_recovers_duplicate_winner_after_rollback(monkeypatch):
    losing = ScriptedConnection(
        fail_on="INSERT INTO workmanship_int_operations",
        failure=DuplicateKey(1062, "duplicate idempotency scope"),
    )
    reload = ScriptedConnection(results=(operation_db_row(),))
    connection_sequence(monkeypatch, losing, reload)

    winner, replayed = IntegrationRepository().claim_operation(operation())

    assert replayed is True and winner.operation_id == "operation-1"
    assert losing.rollbacks == 1 and reload.commits == 1


def test_sql_mapping_and_fields_replace_in_one_transaction_and_roll_back_together(monkeypatch):
    connection = ScriptedConnection(
        fail_on="INSERT INTO workmanship_int_ext_field_mappings",
        failure=RuntimeError("field insert failed"),
    )
    connection_sequence(monkeypatch, connection)
    data = {
        "gid": "mapping-1", "expected_revision": 1, "owner_gid": "actor-1", "team_gid": "team-1",
        "field_mappings": [{
            "gid": "field-1", "revision": 2, "source_field": "part_no", "target_field": "code"
        }],
    }

    with pytest.raises(RuntimeError, match="field insert failed"):
        IntegrationRepository().update_mapping(data)

    sql = "\n".join(statement for statement, _ in connection.statements)
    assert "workmanship_int_ext_mappings" in sql
    assert "DELETE FROM workmanship_int_ext_field_mappings" in sql
    assert connection.rollbacks == 1 and connection.commits == 0


def test_sql_mapping_create_persists_one_field_identity_in_json_and_normalized_rows(monkeypatch):
    connection = ScriptedConnection()
    connection_sequence(monkeypatch, connection)
    IntegrationRepository().create_mapping({
        "gid": "mapping-1", "datasource_gid": "connector-1", "name": "Parts",
        "source_object": "parts", "target_domain": "knowledge",
        "target_capability_id": "knowledge.reference_dataset.publish", "target_major_version": 1,
        "minimum_catalog_release": "rel_20260828", "owner_gid": "actor-1", "team_gid": "team-1",
        "target_binding_id": "ontology:concept-part",
        "target_input_contract": "knowledge.reference_dataset.publish.v1",
        "target_resource_gid": "dataset-parts", "target_expected_version": 7,
        "field_mappings": [{
            "gid": "field-1", "revision": 1, "source_field": "part_no", "target_field": "code"
        }],
    })

    mapping_params = connection.statements[0][1]
    field_params = connection.statements[1][1]
    assert json.loads(mapping_params[12])[0]["gid"] == "field-1"
    assert field_params[:3] == ("field-1", "mapping-1", 1)


def _completed_mapping_operation(capability_id, result):
    accepted = operation(capability_id=capability_id, idempotency_key="mapping-command-1", result=None)
    return accepted, replace(accepted, status="succeeded", version=2, result=result)


def _mapping_create_data():
    return {
        "gid": "mapping-1", "datasource_gid": "connector-1", "name": "Parts",
        "source_object": "parts", "target_domain": "knowledge",
        "target_capability_id": "knowledge.reference_dataset.publish", "target_major_version": 1,
        "minimum_catalog_release": "rel_20260828", "owner_gid": "actor-1", "team_gid": "team-1",
        "target_binding_id": "ontology:concept-part",
        "target_input_contract": "knowledge.reference_dataset.publish.v1",
        "target_resource_gid": "dataset-parts", "target_expected_version": 7,
        "field_mappings": [{
            "gid": "field-1", "source_field": "part_no", "target_field": "code"
        }],
    }


@pytest.mark.parametrize(
    ("capability_id", "command", "data", "mutation_sql", "result"),
    (
        (
            "integration.mapping.create", "create", _mapping_create_data(),
            "INSERT INTO workmanship_int_ext_mappings",
            {"gid": "mapping-1", "revision": 1, "status": "active"},
        ),
        (
            "integration.field_mapping.batch.update", "replace_fields",
            {
                "mapping_gid": "mapping-1", "expected_revision": 1,
                "owner_gid": "actor-1", "team_gid": "team-1",
                "items": [{"gid": "field-1", "source_field": "part_no", "target_field": "code"}],
            },
            "UPDATE workmanship_int_ext_mappings SET field_mappings_json",
            {"mapping_gid": "mapping-1", "revision": 2, "updated_count": 1},
        ),
    ),
)
def test_sql_mapping_command_crash_rolls_back_then_retry_and_replay_are_byte_equivalent(
    monkeypatch, capability_id, command, data, mutation_sql, result,
):
    accepted, completed = _completed_mapping_operation(capability_id, result)
    crash = ScriptedConnection(
        fail_on="UPDATE workmanship_int_operations SET status",
        failure=RuntimeError("crash before idempotent outcome"),
    )
    retry = ScriptedConnection()
    duplicate = ScriptedConnection(
        fail_on="INSERT INTO workmanship_int_operations",
        failure=DuplicateKey(1062, "duplicate idempotency scope"),
    )
    reload = ScriptedConnection(results=(operation_db_row(
        capability_id=capability_id,
        idempotency_key="mapping-command-1",
        status="succeeded",
        operation_version=2,
        result_json=json.dumps(result, separators=(",", ":")),
    ),))
    connection_sequence(monkeypatch, crash, retry, duplicate, reload)
    repository = IntegrationRepository()

    with pytest.raises(RuntimeError, match="crash before idempotent outcome"):
        repository.execute_mapping_command(accepted, completed, command, data)

    first, replayed = repository.execute_mapping_command(accepted, completed, command, data)
    second, replayed_again = repository.execute_mapping_command(accepted, completed, command, data)

    crash_sql = "\n".join(statement for statement, _ in crash.statements)
    assert mutation_sql in crash_sql
    assert "UPDATE workmanship_int_operations SET status" in crash_sql
    assert crash.rollbacks == 1 and crash.commits == 0
    assert retry.commits == 1 and replayed is False
    assert duplicate.rollbacks == 1 and reload.commits == 1 and replayed_again is True
    assert json.dumps(first.result, separators=(",", ":"), ensure_ascii=False).encode() == json.dumps(
        second.result, separators=(",", ":"), ensure_ascii=False
    ).encode()


def test_sql_mapping_get_projects_normalized_fields_not_legacy_json(monkeypatch):
    mapping = {
        "gid": "mapping-1", "owner_gid": "actor-1", "team_gid": "team-1",
        "field_mappings_json": '[{"gid":"legacy-wrong"}]',
    }
    fields = [{
        "gid": "field-1", "revision": 2, "source_field": "part_no", "target_field": "code",
        "transform_expression": None,
    }]
    connection = ScriptedConnection(results=(mapping, fields))
    connection_sequence(monkeypatch, connection)

    result = IntegrationRepository().get_mapping({
        "gid": "mapping-1", "owner_gid": "actor-1", "team_gid": "team-1"
    })

    assert result["field_mappings"] == fields
    assert "workmanship_int_ext_field_mappings" in connection.statements[1][0]


def test_sql_operation_and_import_run_are_created_in_one_transaction_or_rolled_back(monkeypatch):
    connection = ScriptedConnection(
        fail_on="INSERT INTO workmanship_int_sync_runs",
        failure=RuntimeError("run insert failed"),
    )
    connection_sequence(monkeypatch, connection)

    with pytest.raises(RuntimeError, match="run insert failed"):
        IntegrationRepository().claim_import_operation(operation(), import_row())

    sql = "\n".join(statement for statement, _ in connection.statements)
    assert "INSERT INTO workmanship_int_operations" in sql
    assert "INSERT INTO workmanship_int_audit_events" in sql
    assert "INSERT INTO workmanship_int_sync_runs" in sql
    assert connection.rollbacks == 1 and connection.commits == 0


def test_sql_reconciliation_reads_and_updates_with_actor_team_scope(monkeypatch):
    read_connection = ScriptedConnection(results=(operation_db_row(),))
    update_connection = ScriptedConnection()
    connection_sequence(monkeypatch, read_connection, update_connection)
    repository = IntegrationRepository()

    record = repository.get_operation("operation-1", "actor-1", "team-1")
    repository.transition_operation(
        "operation-1", 1, replace(record, status="failed", version=2), "actor-1", "team-1"
    )

    for connection in (read_connection, update_connection):
        sql = "\n".join(statement for statement, _ in connection.statements)
        assert "owner_gid=%s" in sql and "team_gid=%s" in sql


def test_sql_import_replay_rejects_operation_without_atomic_run(monkeypatch):
    operation_connection = ScriptedConnection(results=(operation_db_row(),))
    missing_run_connection = ScriptedConnection(results=(None,))
    connection_sequence(monkeypatch, operation_connection, missing_run_connection)

    from plugins.integration.integration_backend.application.ports import IncompleteOperation

    with pytest.raises(IncompleteOperation):
        IntegrationRepository().find_import_operation(
            "actor-1", "integration.mapping.import.start", "import-1"
        )


class MappingRepository(AtomicStore):
    def __init__(self, *, connector_owner="actor-1"):
        super().__init__()
        self.connector = {
            "gid": "connector-1", "owner_gid": connector_owner, "team_gid": "team-1",
            "host": "8.8.8.8",
        }
        self.mapping = None
        self.fields = []

    def get_connector(self, data):
        if (
            data["gid"] == self.connector["gid"]
            and data["owner_gid"] == self.connector["owner_gid"]
            and data.get("team_gid") == self.connector["team_gid"]
        ):
            return dict(self.connector)
        return None

    def create_mapping(self, data):
        self.fields = [dict(item) for item in data["field_mappings"]]
        self.mapping = {**data, "revision": 1, "status": "active"}
        return dict(self.mapping)

    def find_operation(self, owner_gid, capability_id, idempotency_key):
        if (
            self.record is not None
            and self.record.owner_gid == owner_gid
            and self.record.capability_id == capability_id
            and self.record.idempotency_key == idempotency_key
        ):
            return self.record
        return None

    def execute_mapping_command(self, record, completed, command, data):
        existing = self.find_operation(record.owner_gid, record.capability_id, record.idempotency_key)
        if existing is not None:
            return existing, True
        assert command == "create"
        self.create_mapping(dict(data))
        self.record = completed
        return completed, False

    def get_mapping(self, data):
        if not self.mapping:
            return None
        if self.mapping["owner_gid"] != data["owner_gid"] or self.mapping.get("team_gid") != data.get("team_gid"):
            return None
        return {**self.mapping, "field_mappings": [dict(item) for item in self.fields]}

    def search_field_mappings(self, data):
        return [dict(item) for item in self.fields]

    def update_mapping(self, data):
        if self.mapping["revision"] != data["expected_revision"]:
            raise RuntimeError("unexpected revision")
        self.mapping["revision"] += 1
        self.fields = [dict(item, revision=self.mapping["revision"]) for item in data["field_mappings"]]
        return {"gid": data["gid"], "revision": self.mapping["revision"], "changed": True}


class AcceptingCatalog:
    def project_mapping_targets_for_ontology_objects(
        self, ontology_object_gids, *, actor_gid, team_gid
    ):
        if "concept-part" not in ontology_object_gids:
            return []
        return [{
            **self.resolve_mapping_target(
                "ontology:concept-part", actor_gid=actor_gid, team_gid=team_gid
            ),
            "ontology_object_gid": "concept-part",
        }]

    def resolve_mapping_target(self, binding_id, *, actor_gid, team_gid):
        assert actor_gid == "actor-1" and team_gid == "team-1"
        return {
            "binding_id": binding_id, "target_domain": "knowledge",
            "target_capability_id": "knowledge.reference_dataset.publish",
            "target_major_version": 1, "minimum_catalog_release": "rel_20260828",
            "input_contract": "knowledge.reference_dataset.publish.v1",
            "resource_gid": "dataset-parts", "expected_version": 7,
        }

    def require_stable(self, *_args):
        pass


def mapping_payload(**changes):
    payload = {
        "datasource_gid": "connector-1", "name": "Parts", "source_object": "parts",
        "target_binding_id": "ontology:concept-part",
        "field_mappings": [{"source_field": "part_no", "target_field": "code"}],
        "idempotency_key": "mapping-create-1",
    }
    payload.update(changes)
    return payload


def test_mapping_create_validates_owned_datasource_and_keeps_one_field_identity():
    repository = MappingRepository()
    application = IntegrationApplication(
        repository, catalog=AcceptingCatalog(), operation_identity=Identity()
    )
    created = asyncio.run(application.invoke("integration.mapping.create", mapping_payload(), CONTEXT))
    detail = asyncio.run(application.invoke("integration.mapping.get", {"gid": created["gid"]}, CONTEXT))
    searched = asyncio.run(application.invoke(
        "integration.field_mapping.search", {"mapping_gid": created["gid"]}, CONTEXT
    ))
    assert detail["field_mappings"] == searched["items"]
    assert detail["field_mappings"][0]["revision"] == 1

    updated = asyncio.run(application.invoke("integration.mapping.update", {
        "gid": created["gid"], "expected_revision": 1,
        "field_mappings": [{"source_field": "description", "target_field": "name"}],
    }, CONTEXT))
    detail = asyncio.run(application.invoke("integration.mapping.get", {"gid": created["gid"]}, CONTEXT))
    searched = asyncio.run(application.invoke(
        "integration.field_mapping.search", {"mapping_gid": created["gid"]}, CONTEXT
    ))
    assert updated["revision"] == 2
    assert detail["field_mappings"] == searched["items"]
    assert detail["field_mappings"][0]["revision"] == 2

    foreign = IntegrationApplication(
        MappingRepository(connector_owner="actor-2"), catalog=AcceptingCatalog(), operation_identity=Identity()
    )
    with pytest.raises(CapabilityBusinessError) as foreign_error:
        asyncio.run(foreign.invoke("integration.mapping.create", mapping_payload(), CONTEXT))
    assert foreign_error.value.code == "resource_not_found"


class RuntimeRepository(AtomicStore):
    def __init__(self):
        super().__init__()
        self.connector = {
            "gid": "connector-1", "revision": 1, "name": "ERP", "connector_type": "postgresql",
            "host": "8.8.8.8", "port": 5432, "database_name": "erp", "username": "reader",
            "credential_ref": "vault://credential", "status": "untested",
            "owner_gid": "actor-1", "team_gid": "team-1",
        }
        self.mapping = {
            "gid": "mapping-1", "revision": 1, "datasource_gid": "connector-1", "name": "Parts",
            "source_object": "parts", "target_domain": "knowledge",
            "target_capability_id": "knowledge.reference_dataset.publish", "target_major_version": 1,
            "minimum_catalog_release": "rel_20260828", "status": "active",
            "owner_gid": "actor-1", "team_gid": "team-1",
        }

    def get_connector(self, data):
        if data["gid"] == "connector-1" and data["owner_gid"] == "actor-1" and data.get("team_gid") == "team-1":
            return dict(self.connector)
        return None

    def get_mapping(self, data):
        return dict(self.mapping)


class SecretRuntime:
    async def test(self, *_args, **_kwargs):
        return {"reachable": False, "message": {"authorization": "Bearer top-secret-token"}}

    async def discover(self, *_args, **_kwargs):
        return {"objects": [
            {"name": {"authorization": "Bearer nested-secret"}, "kind": "table"},
            {"name": "parts", "kind": {"credential": "nested-secret"}},
        ]}

    async def source_columns(self, *_args, **_kwargs):
        return {"columns": [
            {"name": "part_no", "data_type": {"api_key": "nested-secret"}, "nullable": False}
        ]}

    async def preview(self, *_args, **_kwargs):
        return {
            "rows": [{
                "part": "P-1",
                "metadata": {"authorization": "Bearer nested-secret"},
                "session_token": "opaque-session-value",
                "cookie": "opaque-cookie-value",
                "private_key": "opaque-private-key-value",
                "passwd": "hunter2",
                "pwd": "hunter3",
                "access_key": "AKIA-test",
                "dsn": "postgresql://user:secret@example.test/db",
                "certificate": "-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----",
            }],
            "truncated": False,
        }


class BlockingSyncRuntime:
    def __init__(self):
        self.called = False

    def test(self, *_args, **_kwargs):
        self.called = True
        return {"reachable": True}


def test_runtime_boundary_rejects_sync_method_without_invoking_it():
    repository = RuntimeRepository()
    runtime = BlockingSyncRuntime()
    application = IntegrationApplication(
        repository, connector_runtime=runtime, operation_identity=Identity()
    )

    with pytest.raises(CapabilityBusinessError) as unavailable:
        asyncio.run(application.invoke(
            "integration.connector.connection.test", {"gid": "connector-1", "idempotency_key": "connection-test-fix-1"}, CONTEXT
        ))

    assert unavailable.value.code == "connector_runtime_unavailable"
    assert runtime.called is False


def test_runtime_results_are_recursively_redacted_before_return_and_persistence(monkeypatch):
    repository = RuntimeRepository()
    application = IntegrationApplication(
        repository, connector_runtime=SecretRuntime(), operation_identity=Identity()
    )
    tested = asyncio.run(application.invoke(
        "integration.connector.connection.test", {"gid": "connector-1", "idempotency_key": "connection-test-fix-2"}, CONTEXT
    ))
    assert tested["message"] == "[REDACTED]"
    assert repository.record.result["message"] == "[REDACTED]"

    repository.record = None
    previewed = asyncio.run(application.invoke(
        "integration.mapping.preview", {"gid": "mapping-1", "limit": 1}, CONTEXT
    ))
    metadata = next(cell for cell in previewed["rows"][0]["values"] if cell["field"] == "metadata")
    assert metadata == {"field": "metadata", "value": "[REDACTED]", "redacted": True}
    for field in ("session_token", "cookie", "private_key", "passwd", "pwd", "access_key", "dsn", "certificate"):
        cell = next(item for item in previewed["rows"][0]["values"] if item["field"] == field)
        assert cell == {"field": field, "value": "[REDACTED]", "redacted": True}
    assert "top-secret" not in str(repository.record.result)
    assert "opaque-" not in str(repository.record.result)
    assert "hunter" not in str(repository.record.result)
    assert "postgresql://" not in str(repository.record.result)
    assert "BEGIN PRIVATE KEY" not in str(repository.record.result)

    sql_connection = ScriptedConnection()
    connection_sequence(monkeypatch, sql_connection)
    persisted_record = repository.record
    IntegrationRepository().transition_operation(
        persisted_record.operation_id,
        persisted_record.version - 1,
        persisted_record,
        persisted_record.owner_gid,
        persisted_record.team_gid,
    )
    result_json = json.loads(sql_connection.statements[0][1][2])
    assert "opaque-" not in str(result_json)
    assert all(
        cell["value"] == "[REDACTED]"
        for cell in result_json["rows"][0]["values"]
        if cell["field"] in {"session_token", "cookie", "private_key"}
    )

    repository.record = None
    discovered = asyncio.run(application.invoke(
        "integration.connector.schema.discover", {"gid": "connector-1", "limit": 2}, CONTEXT
    ))
    assert discovered["objects"] == [{"name": "parts", "kind": "object"}]
    assert "nested-secret" not in str(repository.record.result)

    repository.record = None
    columns = asyncio.run(application.invoke(
        "integration.mapping.source_columns.discover", {"mapping_gid": "mapping-1", "limit": 1}, CONTEXT
    ))
    assert columns["columns"] == [{"name": "part_no", "data_type": "unknown", "nullable": False}]
    assert "nested-secret" not in str(repository.record.result)
