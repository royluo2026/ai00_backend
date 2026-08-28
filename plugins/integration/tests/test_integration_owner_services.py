import asyncio
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from datetime import UTC, datetime

import pytest

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext
from plugins.integration.integration_backend.application.service import IntegrationApplication
from plugins.integration.integration_backend.infrastructure.repository import IntegrationRepository


CONTEXT = CapabilityContext(user_gid="actor-1", team_gid="team-1", request_id="request-1")


class MemoryRepository:
    def __init__(self):
        self.connectors = {}
        self.mappings = {}
        self.field_mappings = {}
        self.imports = []
        self.operations = {}
        self.operation_scopes = {}
        self.operation_statuses = []
        self.bindings = {}

    @staticmethod
    def _visible(row, data):
        return row["owner_gid"] == data["owner_gid"] and row.get("team_gid") == data.get("team_gid")

    def create_connector(self, data):
        gid = f"connector-{len(self.connectors) + 1}"
        row = {**data, "gid": gid, "revision": 1, "status": "untested"}
        self.connectors[gid] = row
        return dict(row)

    def get_connector(self, data):
        row = self.connectors.get(data["gid"])
        return dict(row) if row and self._visible(row, data) else None

    def update_connector(self, data):
        from plugins.integration.integration_backend.application.ports import ResourceNotFound, RevisionConflict

        row = self.connectors.get(data["gid"])
        if not row or not self._visible(row, data):
            raise ResourceNotFound("connector")
        if row["revision"] != data["expected_revision"]:
            raise RevisionConflict("connector")
        row.update({key: value for key, value in data.items() if key not in {"gid", "expected_revision", "idempotency_key"}})
        row["revision"] += 1
        return dict(row)

    def archive_connector(self, data):
        return {"gid": data["gid"], "archived": True}

    def search_connectors(self, data):
        return [dict(row) for row in self.connectors.values() if self._visible(row, data)][: data.get("limit", 100)]

    def create_mapping(self, data):
        gid = data.get("gid") or f"mapping-{len(self.mappings) + 1}"
        row = {**data, "gid": gid, "revision": 1, "status": "active"}
        self.mappings[gid] = row
        self.field_mappings[gid] = [dict(item) for item in data.get("field_mappings", ())]
        return dict(row)

    def get_mapping(self, data):
        row = self.mappings.get(data["gid"])
        if row and self._visible(row, data):
            return {**row, "field_mappings": [dict(item) for item in self.field_mappings.get(data["gid"], ())]}
        return None

    def search_mappings(self, data):
        return [dict(row) for row in self.mappings.values() if self._visible(row, data)][: data.get("limit", 100)]

    def search_field_mappings(self, data):
        if not self.get_mapping({**data, "gid": data["mapping_gid"]}):
            return None
        return [dict(row) for row in self.field_mappings.get(data["mapping_gid"], ())][: data.get("limit", 100)]

    def replace_field_mappings(self, data):
        from plugins.integration.integration_backend.application.ports import ResourceNotFound, RevisionConflict

        row = self.mappings.get(data["mapping_gid"])
        if not row or not self._visible(row, data):
            raise ResourceNotFound("mapping")
        if row["revision"] != data["expected_revision"]:
            raise RevisionConflict("mapping")
        row["revision"] += 1
        items = [dict(item, revision=row["revision"]) for item in data["items"]]
        self.field_mappings[data["mapping_gid"]] = items
        return {"mapping_gid": data["mapping_gid"], "revision": row["revision"], "updated_count": len(items), "items": items}

    def execute_mapping_command(self, record, completed, command, data):
        existing = self.find_operation(record.owner_gid, record.capability_id, record.idempotency_key)
        if existing is not None:
            return existing, True
        if command == "create":
            self.create_mapping(dict(data))
        elif command == "replace_fields":
            self.replace_field_mappings(dict(data))
        else:
            raise AssertionError(command)
        self._create_operation(completed)
        return completed, False

    def execute_binding_command(self, record, target, *, expected_revision, mapping_gid, mapping_expected_revision):
        existing_op = self.find_operation(record.owner_gid, record.capability_id, record.idempotency_key)
        if existing_op is not None:
            return existing_op, True
        binding_key = (record.team_gid, target["binding_id"])
        current = self.bindings.get(binding_key)
        if current and current["revision"] != expected_revision:
            from plugins.integration.integration_backend.application.ports import RevisionConflict
            raise RevisionConflict("target binding")
        revision = int(current["revision"] if current else 0) + 1
        result = {key: target[key] for key in (
            "binding_id", "ontology_object_gid", "target_domain", "target_capability_id",
            "target_major_version", "minimum_catalog_release", "resource_gid", "expected_version",
        )} | {"revision": revision}
        self.bindings[binding_key] = {**target, "revision": revision, "owner_gid": record.owner_gid, "team_gid": record.team_gid}
        if mapping_gid:
            mapping = self.mappings.get(mapping_gid)
            if not mapping or not self._visible(mapping, {"owner_gid": record.owner_gid, "team_gid": record.team_gid}) or mapping["revision"] != mapping_expected_revision:
                from plugins.integration.integration_backend.application.ports import RevisionConflict
                raise RevisionConflict("mapping")
            mapping.update({
                "target_binding_id": target["binding_id"], "target_domain": target["target_domain"],
                "target_capability_id": target["target_capability_id"], "target_major_version": target["target_major_version"],
                "minimum_catalog_release": target["minimum_catalog_release"], "target_input_contract": target["input_contract"],
                "target_resource_gid": target["resource_gid"], "target_expected_version": target["expected_version"],
                "status": "active", "revision": mapping_expected_revision + 1,
            })
            result.update(mapping_gid=mapping_gid, mapping_revision=mapping_expected_revision + 1)
        completed = replace(record, status="succeeded", version=record.version + 1, result=result)
        self._create_operation(completed)
        return completed, False

    def update_mapping(self, data):
        from plugins.integration.integration_backend.application.ports import ResourceNotFound, RevisionConflict

        row = self.mappings.get(data["gid"])
        if not row or not self._visible(row, data):
            raise ResourceNotFound("mapping")
        if row["revision"] != data["expected_revision"]:
            raise RevisionConflict("mapping")
        row["revision"] += 1
        self.field_mappings[data["gid"]] = [
            dict(item, revision=row["revision"]) for item in data.get("field_mappings", ())
        ]
        return {"gid": data["gid"], "revision": row["revision"], "changed": True}

    def archive_mapping(self, data):
        return {"gid": data["gid"], "archived": True}

    def claim_import_operation(self, record, run):
        winner, replayed = self.claim_operation(record)
        if not replayed:
            self.imports.append(dict(run))
        return winner, replayed

    def find_operation(self, owner_gid, capability_id, idempotency_key):
        operation_id = self.operation_scopes.get((owner_gid, capability_id, idempotency_key))
        return self.operations.get(operation_id)

    def find_import_operation(self, owner_gid, capability_id, idempotency_key):
        record = self.find_operation(owner_gid, capability_id, idempotency_key)
        if record is None:
            return None
        if not any(run["operation_id"] == record.operation_id for run in self.imports):
            from plugins.integration.integration_backend.application.ports import IncompleteOperation

            raise IncompleteOperation(record.operation_id)
        return record

    def _create_operation(self, record):
        self.operations[record.operation_id] = record
        self.operation_scopes[(record.owner_gid, record.capability_id, record.idempotency_key)] = record.operation_id
        self.operation_statuses.append(record.status)
        return record

    def claim_operation(self, record):
        existing = self.find_operation(record.owner_gid, record.capability_id, record.idempotency_key)
        if existing is not None:
            return existing, True
        return self._create_operation(record), False

    def get_operation(self, operation_id, owner_gid, team_gid):
        record = self.operations.get(operation_id)
        if record and record.owner_gid == owner_gid and record.team_gid == team_gid:
            return record
        return None

    def transition_operation(self, operation_id, expected_version, replacement, owner_gid, team_gid):
        current = self.get_operation(operation_id, owner_gid, team_gid)
        if current is None:
            from plugins.integration.integration_backend.application.ports import RevisionConflict

            raise RevisionConflict("operation")
        if current.version != expected_version:
            from plugins.integration.integration_backend.application.ports import RevisionConflict

            raise RevisionConflict("operation")
        self.operations[operation_id] = replacement
        self.operation_statuses.append(replacement.status)
        return replacement


class FixedIdentity:
    def __init__(self):
        self.counter = 0

    def new_id(self, kind):
        self.counter += 1
        return f"{kind}-{self.counter}"

    def now(self):
        return datetime(2026, 8, 28, tzinfo=UTC)


class Vault:
    def __init__(self):
        self.calls = []

    def consume(self, handle, actor_gid, team_gid):
        self.calls.append((handle, actor_gid, team_gid))
        return "vault://integration/credential-1"


class Catalog:
    def __init__(self, reject=False):
        self.reject = reject
        self.calls = []

    def require_stable(self, capability_id, major_version, minimum_release):
        self.calls.append((capability_id, major_version, minimum_release))
        if self.reject:
            raise ValueError("target is not a stable Catalog entry")

    def validate_mapping_target(self, candidate):
        self.require_stable(candidate["target_capability_id"], candidate["target_major_version"], candidate["minimum_catalog_release"])
        if candidate["target_domain"] != "knowledge":
            raise ValueError("target_binding_owner_mismatch")
        return dict(candidate)

    def resolve_mapping_target(self, binding_id, *, actor_gid, team_gid):
        if (actor_gid, team_gid) != ("actor-1", "team-1"):
            raise ValueError("target binding is outside principal scope")
        if binding_id != "ontology:concept-part":
            raise ValueError("target binding is unavailable")
        return {
            "binding_id": binding_id,
            "target_domain": "knowledge",
            "target_capability_id": "knowledge.reference_dataset.publish",
            "target_major_version": 1,
            "minimum_catalog_release": "rel_7803705d3df421f9f4381d37c3500731",
            "input_contract": "knowledge.reference_dataset.publish.v1",
            "resource_gid": "dataset-parts",
            "expected_version": 7,
        }

    def project_mapping_targets_for_ontology_objects(
        self, ontology_object_gids, *, actor_gid, team_gid
    ):
        if (actor_gid, team_gid) != ("actor-1", "team-1"):
            return []
        if "concept-part" not in ontology_object_gids:
            return []
        return [{
            **self.resolve_mapping_target(
                "ontology:concept-part", actor_gid=actor_gid, team_gid=team_gid
            ),
            "ontology_object_gid": "concept-part",
        }]

    def upsert_mapping_target(self, **data):
        return {**data, "expected_version": data["target_expected_version"], "revision": 1}


class Runtime:
    def __init__(self, failure=None):
        self.calls = []
        self.failure = failure

    async def test(self, connector, *, timeout_seconds, result_limit):
        self.calls.append(("test", connector, timeout_seconds, result_limit))
        if self.failure:
            raise self.failure
        return {"reachable": True, "latency_ms": 12, "password": "must-not-leak"}

    async def discover(self, connector, *, timeout_seconds, result_limit):
        self.calls.append(("discover", connector, timeout_seconds, result_limit))
        if self.failure:
            raise self.failure
        return {"objects": [
            {"name": "parts", "kind": "table", "credentials": "must-not-leak"},
            {"name": "suppliers", "kind": "view"},
            {"name": "ignored", "kind": "table"},
        ]}

    async def source_columns(self, connector, mapping, *, timeout_seconds, result_limit):
        self.calls.append(("source_columns", connector, mapping, timeout_seconds, result_limit))
        if self.failure:
            raise self.failure
        return {"columns": [{"name": "part_no", "data_type": "text", "nullable": False, "secret": "x"}]}

    async def preview(self, connector, mapping, *, timeout_seconds, result_limit):
        self.calls.append(("preview", connector, mapping, timeout_seconds, result_limit))
        if self.failure:
            raise self.failure
        return {"rows": [{"part_no": "P-1", "password": "must-not-leak"}], "truncated": False}


def app(repository=None, *, vault=None, catalog=None, runtime=None):
    repository = repository or MemoryRepository()
    return IntegrationApplication(
        repository,
        credential_enrollment=vault,
        catalog=catalog,
        connector_runtime=runtime,
        operation_identity=FixedIdentity(),
    )


def connector_payload(**changes):
    value = {
        "name": "ERP",
        "connector_type": "postgresql",
        "host": "8.8.8.8",
        "port": 5432,
        "database_name": "erp",
        "username": "reader",
        "credential_enrollment_handle": "enroll-once-1",
        "idempotency_key": "connector-create-1",
    }
    value.update(changes)
    return value


def mapping_payload(**changes):
    value = {
        "datasource_gid": "connector-1",
        "name": "Parts",
        "source_object": "parts",
        "target_binding_id": "ontology:concept-part",
        "field_mappings": [{"source_field": "part_no", "target_field": "code", "transform_expression": "upper(source.part_no)"}],
        "idempotency_key": "mapping-create-1",
    }
    value.update(changes)
    return value


def assert_code(error, code):
    assert isinstance(error.value, CapabilityBusinessError)
    assert error.value.code == code


def test_connector_handle_is_consumed_once_and_only_reference_is_persisted_on_replay():
    repository, vault = MemoryRepository(), Vault()
    application = app(repository, vault=vault)

    first = asyncio.run(application.invoke("integration.connector.create", connector_payload(), CONTEXT))
    replay = asyncio.run(application.invoke("integration.connector.create", connector_payload(), CONTEXT))

    assert first == replay
    assert vault.calls == [("enroll-once-1", "actor-1", "team-1")]
    stored = repository.connectors[first["gid"]]
    assert stored["owner_gid"] == "actor-1" and stored["team_gid"] == "team-1"
    assert stored["credential_ref"] == "vault://integration/credential-1"
    assert "credential_enrollment_handle" not in stored
    assert "credential_ref" not in first

    with pytest.raises(CapabilityBusinessError) as conflict:
        asyncio.run(application.invoke("integration.connector.create", connector_payload(name="Other"), CONTEXT))
    assert_code(conflict, "idempotency_conflict")


@pytest.mark.parametrize("forbidden", ["password", "credentials", "filter_sql", "config", "unknown"])
def test_owner_boundary_rejects_undeclared_connector_fields(forbidden):
    with pytest.raises(CapabilityBusinessError) as invalid:
        asyncio.run(app(vault=Vault()).invoke("integration.connector.create", connector_payload(**{forbidden: "x"}), CONTEXT))
    assert_code(invalid, "invalid_input")


def test_connector_update_enforces_team_scope_and_optimistic_revision():
    repository = MemoryRepository()
    application = app(repository, vault=Vault())
    created = asyncio.run(application.invoke("integration.connector.create", connector_payload(), CONTEXT))

    updated = asyncio.run(application.invoke(
        "integration.connector.update",
        {"gid": created["gid"], "expected_revision": 1, "name": "ERP 2", "idempotency_key": "update-1"},
        CONTEXT,
    ))
    assert updated["revision"] == 2

    with pytest.raises(CapabilityBusinessError) as stale:
        asyncio.run(application.invoke(
            "integration.connector.update",
            {"gid": created["gid"], "expected_revision": 1, "name": "ERP 3", "idempotency_key": "update-2"},
            CONTEXT,
        ))
    assert_code(stale, "version_conflict")

    with pytest.raises(CapabilityBusinessError) as hidden:
        asyncio.run(application.invoke(
            "integration.connector.update",
            {"gid": created["gid"], "expected_revision": 2, "name": "ERP 3", "idempotency_key": "update-3"},
            CapabilityContext(user_gid="actor-1", team_gid="team-2"),
        ))
    assert_code(hidden, "resource_not_found")


def test_connector_write_translates_network_policy_rejection():
    repository = MemoryRepository()
    with pytest.raises(CapabilityBusinessError) as rejected:
        asyncio.run(app(repository, vault=Vault()).invoke(
            "integration.connector.create", connector_payload(host="127.0.0.1"), CONTEXT
        ))
    assert_code(rejected, "network_policy_rejected")
    assert repository.operation_statuses == ["accepted", "failed"]


def test_mapping_create_requires_stable_exact_catalog_target_and_restricted_transforms():
    repository, catalog = MemoryRepository(), Catalog()
    _seed_connector_and_mapping(repository)
    repository.mappings.clear()
    repository.field_mappings.clear()
    application = app(repository, catalog=catalog)

    created = asyncio.run(application.invoke("integration.mapping.create", mapping_payload(), CONTEXT))
    assert created["target_capability_id"] == "knowledge.reference_dataset.publish"
    assert catalog.calls == [("knowledge.reference_dataset.publish", 1, "rel_7803705d3df421f9f4381d37c3500731")]

    rejecting_repository = MemoryRepository()
    _seed_connector_and_mapping(rejecting_repository)
    rejecting_repository.mappings.clear()
    rejecting_repository.field_mappings.clear()
    rejecting = app(rejecting_repository, catalog=Catalog(reject=True))
    with pytest.raises(CapabilityBusinessError) as unavailable:
        asyncio.run(rejecting.invoke("integration.mapping.create", mapping_payload(), CONTEXT))
    assert_code(unavailable, "target_capability_unavailable")

    with pytest.raises(CapabilityBusinessError) as expression:
        asyncio.run(application.invoke(
            "integration.mapping.create",
            mapping_payload(idempotency_key="mapping-create-2", field_mappings=[{
                "source_field": "part_no", "target_field": "code", "transform_expression": "__import__('os')"
            }]),
            CONTEXT,
        ))
    assert_code(expression, "invalid_input")


def _seed_connector_and_mapping(repository):
    repository.connectors["connector-1"] = {
        "gid": "connector-1", "revision": 1, "name": "ERP", "connector_type": "postgresql",
        "host": "8.8.8.8", "port": 5432, "database_name": "erp", "username": "reader",
        "credential_ref": "vault://integration/credential-1", "status": "untested",
        "owner_gid": "actor-1", "team_gid": "team-1",
    }
    repository.mappings["mapping-1"] = {
        "gid": "mapping-1", "revision": 1, "datasource_gid": "connector-1", "name": "Parts",
        "source_object": "parts", "target_domain": "knowledge",
        "target_capability_id": "knowledge.reference_dataset.publish", "target_major_version": 1,
        "minimum_catalog_release": "rel_7803705d3df421f9f4381d37c3500731", "status": "active",
        "target_binding_id": "ontology:concept-part",
        "target_input_contract": "knowledge.reference_dataset.publish.v1",
        "target_resource_gid": "dataset-parts", "target_expected_version": 7,
        "owner_gid": "actor-1", "team_gid": "team-1",
    }


def test_runtime_calls_are_network_checked_bounded_redacted_and_durable():
    repository, runtime = MemoryRepository(), Runtime()
    _seed_connector_and_mapping(repository)
    application = app(repository, runtime=runtime)

    discovered = asyncio.run(application.invoke(
        "integration.connector.schema.discover", {"gid": "connector-1", "limit": 2}, CONTEXT
    ))

    assert discovered["objects"] == [{"name": "parts", "kind": "table"}, {"name": "suppliers", "kind": "view"}]
    assert discovered["operation_ref"]["status"] == "succeeded"
    assert runtime.calls[0][2:] == (15, 2)
    assert repository.operation_statuses == ["accepted", "succeeded"]
    assert "credential_ref" not in str(discovered) and "credentials" not in str(discovered)

    repository.connectors["connector-1"]["host"] = "127.0.0.1"
    with pytest.raises(CapabilityBusinessError) as rejected:
        asyncio.run(application.invoke("integration.connector.connection.test", {"gid": "connector-1", "idempotency_key": "connection-test-1"}, CONTEXT))
    assert_code(rejected, "network_policy_rejected")
    assert len(runtime.calls) == 1


def test_runtime_timeout_is_persisted_as_unknown_and_failure_as_failed():
    repository = MemoryRepository()
    _seed_connector_and_mapping(repository)
    timed_out = app(repository, runtime=Runtime(TimeoutError("deadline")))

    result = asyncio.run(timed_out.invoke("integration.mapping.preview", {"gid": "mapping-1", "limit": 1}, CONTEXT))
    assert result == {
        "rows": [], "truncated": False,
        "operation_ref": {"operation_id": "operation-1", "status": "outcome_unknown", "version": 2},
    }
    assert repository.operation_statuses == ["accepted", "outcome_unknown"]

    failed_repository = MemoryRepository()
    _seed_connector_and_mapping(failed_repository)
    failed = app(failed_repository, runtime=Runtime(ValueError("runtime rejected request")))
    with pytest.raises(CapabilityBusinessError) as unavailable:
        asyncio.run(failed.invoke("integration.mapping.preview", {"gid": "mapping-1", "limit": 1}, CONTEXT))
    assert_code(unavailable, "connector_runtime_unavailable")
    assert failed_repository.operation_statuses == ["accepted", "failed"]


def test_field_mapping_batch_is_all_or_nothing_revision_locked_and_idempotent():
    repository, catalog = MemoryRepository(), Catalog()
    _seed_connector_and_mapping(repository)
    application = app(repository, catalog=catalog)
    payload = {
        "mapping_gid": "mapping-1", "expected_revision": 1, "idempotency_key": "field-batch-1",
        "items": [{"source_field": "part_no", "target_field": "code", "transform_expression": "upper(source.part_no)"}],
    }

    first = asyncio.run(application.invoke("integration.field_mapping.batch.update", payload, CONTEXT))
    replay = asyncio.run(application.invoke("integration.field_mapping.batch.update", payload, CONTEXT))

    assert first == replay
    assert first["updated_count"] == 1 and first["revision"] == 2
    assert first["items"][0]["gid"].startswith("field_mapping-")
    assert catalog.calls == [("knowledge.reference_dataset.publish", 1, "rel_7803705d3df421f9f4381d37c3500731")]

    with pytest.raises(CapabilityBusinessError) as stale:
        asyncio.run(application.invoke(
            "integration.field_mapping.batch.update",
            {**payload, "idempotency_key": "field-batch-2", "expected_revision": 1},
            CONTEXT,
        ))
    assert_code(stale, "version_conflict")


def test_import_start_is_durable_accepted_and_replayed_without_duplicate_run():
    repository, catalog = MemoryRepository(), Catalog()
    _seed_connector_and_mapping(repository)
    application = app(repository, catalog=catalog)
    payload = {"mapping_gid": "mapping-1", "idempotency_key": "import-1"}

    first = asyncio.run(application.invoke("integration.mapping.import.start", payload, CONTEXT))
    replay = asyncio.run(application.invoke("integration.mapping.import.start", payload, CONTEXT))

    assert first == replay
    assert first["operation_ref"]["status"] == "accepted"
    assert len(repository.imports) == 1
    assert repository.imports[0]["target_capability_id"] == "knowledge.reference_dataset.publish"
    assert catalog.calls == [("knowledge.reference_dataset.publish", 1, "rel_7803705d3df421f9f4381d37c3500731")]


def test_import_replay_preserves_run_identity_across_unknown_failed_and_reconciled_states():
    repository, catalog = MemoryRepository(), Catalog()
    _seed_connector_and_mapping(repository)
    application = app(repository, catalog=catalog)
    payload = {"mapping_gid": "mapping-1", "idempotency_key": "import-states-1"}
    accepted = asyncio.run(application.invoke("integration.mapping.import.start", payload, CONTEXT))
    record = repository.operations[accepted["operation_ref"]["operation_id"]]

    unknown = application.operations.outcome_unknown(record, error_code="external_timeout")
    unknown_replay = asyncio.run(application.invoke("integration.mapping.import.start", payload, CONTEXT))
    assert unknown_replay["run_id"] == accepted["run_id"]
    assert unknown_replay["operation_ref"]["status"] == "outcome_unknown"

    reconciled = application.operations.reconcile(
        unknown.operation_id, "succeeded", owner_gid="actor-1", team_gid="team-1",
        expected_version=unknown.version, result={"imported_count": 4},
    )
    reconciled_replay = asyncio.run(application.invoke("integration.mapping.import.start", payload, CONTEXT))
    assert reconciled.result["run_id"] == accepted["run_id"]
    assert reconciled_replay["run_id"] == accepted["run_id"]
    assert reconciled_replay["operation_ref"]["status"] == "succeeded"

    failed_repository = MemoryRepository()
    _seed_connector_and_mapping(failed_repository)
    failed_application = app(failed_repository, catalog=Catalog())
    failed_accepted = asyncio.run(failed_application.invoke(
        "integration.mapping.import.start", {**payload, "idempotency_key": "import-states-2"}, CONTEXT
    ))
    failed_record = failed_repository.operations[failed_accepted["operation_ref"]["operation_id"]]
    failed_application.operations.failed(failed_record, error_code="target_rejected")
    failed_replay = asyncio.run(failed_application.invoke(
        "integration.mapping.import.start", {**payload, "idempotency_key": "import-states-2"}, CONTEXT
    ))
    assert failed_replay["run_id"] == failed_accepted["run_id"]
    assert failed_replay["operation_ref"]["status"] == "failed"


def test_unknown_operation_can_only_be_reconciled_with_expected_version():
    try:
        from plugins.integration.integration_backend.application.operations import IntegrationOperations
    except ModuleNotFoundError:
        pytest.fail("Integration durable operations are missing")

    repository = MemoryRepository()
    operations = IntegrationOperations(repository, identity=FixedIdentity())
    claim = operations.start(
        capability_id="integration.mapping.import.start", payload={"mapping_gid": "mapping-1"},
        owner_gid="actor-1", team_gid="team-1", idempotency_key="import-1",
    )
    unknown = operations.outcome_unknown(claim.record, error_code="external_timeout")
    succeeded = operations.reconcile(
        unknown.operation_id, "succeeded", owner_gid="actor-1", team_gid="team-1",
        expected_version=unknown.version, result={"imported_count": 4}
    )
    assert succeeded.status == "succeeded" and succeeded.result == {"imported_count": 4}

    with pytest.raises(CapabilityBusinessError) as stale:
        operations.reconcile(
            unknown.operation_id, "failed", owner_gid="actor-1", team_gid="team-1",
            expected_version=unknown.version, error_code="late_failure",
        )
    assert_code(stale, "version_conflict")


class RecordingCursor:
    def __init__(self, connection):
        self.connection = connection
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=()):
        self.connection.statements.append((" ".join(sql.split()), params))

    def fetchone(self):
        return None

    def fetchall(self):
        return []


class RecordingConnection:
    def __init__(self):
        self.statements = []

    def cursor(self):
        return RecordingCursor(self)

    def commit(self):
        pass


def test_sql_repository_scopes_search_by_actor_and_team_and_caps_results(monkeypatch):
    connection = RecordingConnection()

    @contextmanager
    def connections():
        yield connection

    monkeypatch.setattr(
        "plugins.integration.integration_backend.infrastructure.repository.get_integration_conn",
        connections,
    )
    IntegrationRepository().search_connectors({"owner_gid": "actor-1", "team_gid": "team-1", "limit": 999})

    sql, params = connection.statements[-1]
    assert "owner_gid=%s" in sql and "team_gid=%s" in sql
    assert params == ("actor-1", "team-1", 200)


def test_sql_repository_persists_operation_and_audit_transitions(monkeypatch):
    from plugins.integration.integration_backend.application.operations import IntegrationOperation

    connection = RecordingConnection()

    @contextmanager
    def connections():
        yield connection

    monkeypatch.setattr(
        "plugins.integration.integration_backend.infrastructure.repository.get_integration_conn",
        connections,
    )
    now = datetime(2026, 8, 28, tzinfo=UTC)
    record = IntegrationOperation(
        operation_id="operation-1", owner_gid="actor-1", team_gid="team-1",
        capability_id="integration.mapping.import.start", idempotency_key="import-1",
        payload_hash="a" * 64, status="accepted", version=1, result={"run_id": "run-1"},
        error_code=None, created_at=now, updated_at=now,
    )
    repository = IntegrationRepository()
    repository.claim_operation(record)
    repository.transition_operation(
        "operation-1", 1, replace(record, status="outcome_unknown", version=2), "actor-1", "team-1"
    )

    sql = "\n".join(statement for statement, _ in connection.statements)
    assert "workmanship_int_operations" in sql
    assert sql.count("workmanship_int_audit_events") == 2
    assert "credential_enrollment_handle" not in sql and "password" not in sql


def test_sql_import_run_pins_target_version_release_and_idempotency(monkeypatch):
    from plugins.integration.integration_backend.application.operations import IntegrationOperation

    connection = RecordingConnection()

    @contextmanager
    def connections():
        yield connection

    monkeypatch.setattr(
        "plugins.integration.integration_backend.infrastructure.repository.get_integration_conn",
        connections,
    )
    now = datetime(2026, 8, 28, tzinfo=UTC)
    record = IntegrationOperation(
        operation_id="operation-1", owner_gid="actor-1", team_gid="team-1",
        capability_id="integration.mapping.import.start", idempotency_key="import-1",
        payload_hash="a" * 64, status="accepted", version=1, result={"run_id": "run-1"},
        error_code=None, created_at=now, updated_at=now,
    )
    IntegrationRepository().claim_import_operation(record, {
        "run_id": "run-1", "mapping_gid": "mapping-1", "operation_id": "operation-1",
        "status": "accepted", "target_capability_id": "knowledge.reference_dataset.publish",
        "target_major_version": 1, "catalog_release": "rel_20260828", "owner_gid": "actor-1",
        "team_gid": "team-1", "idempotency_key": "import-1", "target_invocation": {},
    })

    sql, params = connection.statements[-1]
    assert "target_major_version" in sql and "idempotency_key" in sql
    assert params[5:7] == (1, "rel_20260828") and params[-1] == "import-1"


def test_forward_migration_adds_scoped_operations_audit_and_field_revisions():
    root = Path(__file__).parents[3]
    sql = (root / "backend/db/migrations/domains/integration/0002_integration_structural_operations.sql").read_text(encoding="utf-8")

    assert "workmanship_int_operations" in sql and "workmanship_int_audit_events" in sql
    assert "UNIQUE KEY `uq_int_operation_idempotency` (`owner_gid`,`capability_id`,`idempotency_key`)" in sql
    assert "ADD COLUMN IF NOT EXISTS `revision`" in sql
    assert "ADD COLUMN IF NOT EXISTS `target_major_version`" in sql
    assert "ADD COLUMN IF NOT EXISTS `idempotency_key`" in sql
    assert "credential_enrollment_handle" not in sql and "password" not in sql and "credentials" not in sql
