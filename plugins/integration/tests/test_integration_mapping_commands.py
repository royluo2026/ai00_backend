import asyncio
import json
from dataclasses import replace

import pytest

from backend.capability_v2.provider_contracts import CapabilityBusinessError
from plugins.integration.tests.test_integration_owner_services import (
    CONTEXT,
    Catalog,
    MemoryRepository,
    _seed_connector_and_mapping,
    app,
    mapping_payload,
)


class BoundCatalog:
    def __init__(self, binding=None):
        self.binding = binding
        self.stable_calls = []

    def resolve_mapping_target(self, binding_id):
        if binding_id != "ontology:concept-part" or self.binding is None:
            raise LookupError(binding_id)
        return dict(self.binding)

    def require_stable(self, capability_id, major_version, minimum_release):
        self.stable_calls.append((capability_id, major_version, minimum_release))


VALID_BINDING = {
    "binding_id": "ontology:concept-part",
    "target_domain": "knowledge",
    "target_capability_id": "knowledge.reference_data.change.apply",
    "target_major_version": 1,
    "minimum_catalog_release": "rel_7803705d3df421f9f4381d37c3500731",
    "input_contract": "knowledge.reference_dataset.publish.v1",
    "resource_gid": "dataset-parts",
    "expected_version": 7,
}


def bound_mapping_payload(**changes):
    value = {
        "datasource_gid": "connector-1",
        "name": "Parts",
        "source_object": "parts",
        "target_binding_id": "ontology:concept-part",
        "field_mappings": [{"source_field": "part_no", "target_field": "code"}],
        "idempotency_key": "mapping-create-bound-1",
    }
    value.update(changes)
    return value


def error_code(error):
    assert isinstance(error.value, CapabilityBusinessError)
    return error.value.code


def test_mapping_create_rejects_non_integer_target_version_and_duplicate_field_identity():
    repository = MemoryRepository()
    _seed_connector_and_mapping(repository)
    repository.mappings.clear()
    repository.field_mappings.clear()
    application = app(repository, catalog=Catalog())

    with pytest.raises(CapabilityBusinessError) as boolean_version:
        asyncio.run(application.invoke(
            "integration.mapping.create",
            mapping_payload(target_major_version=True),
            CONTEXT,
        ))
    assert error_code(boolean_version) == "invalid_input"

    duplicate = {"source_field": "part_no", "target_field": "code"}
    with pytest.raises(CapabilityBusinessError) as duplicate_identity:
        asyncio.run(application.invoke(
            "integration.mapping.create",
            mapping_payload(
                idempotency_key="mapping-create-duplicate",
                field_mappings=[duplicate, duplicate],
            ),
            CONTEXT,
        ))
    assert error_code(duplicate_identity) == "invalid_input"
    assert repository.mappings == {}


def test_mapping_create_resolves_a_finite_binding_and_import_persists_valid_target_invocation():
    repository = MemoryRepository()
    _seed_connector_and_mapping(repository)
    repository.mappings.clear()
    repository.field_mappings.clear()
    catalog = BoundCatalog(VALID_BINDING)
    application = app(repository, catalog=catalog)

    created = asyncio.run(application.invoke(
        "integration.mapping.create", bound_mapping_payload(), CONTEXT
    ))
    assert created["target_capability_id"] == "knowledge.reference_data.change.apply"
    stored = repository.mappings[created["gid"]]
    assert stored["target_binding_id"] == "ontology:concept-part"
    assert stored["target_input_contract"] == "knowledge.reference_dataset.publish.v1"
    assert stored["target_resource_gid"] == "dataset-parts"
    assert stored["target_expected_version"] == 7
    assert catalog.stable_calls == [(
        "knowledge.reference_data.change.apply", 1, "rel_7803705d3df421f9f4381d37c3500731"
    )]

    started = asyncio.run(application.invoke(
        "integration.mapping.import.start",
        {"mapping_gid": created["gid"], "idempotency_key": "import-bound-1"},
        CONTEXT,
    ))
    run = repository.imports[0]
    assert run["run_id"] == started["run_id"]
    assert run["target_invocation"] == {
        "capability_id": "knowledge.reference_data.change.apply",
        "major_version": 1,
        "minimum_catalog_release": "rel_7803705d3df421f9f4381d37c3500731",
        "payload": {
            "dataset_gid": "dataset-parts",
            "expected_version": 7,
            "schema": {"fields": [{"name": "code", "source_field": "part_no"}]},
            "rows": [],
        },
        "dispatch_state": "awaiting_rows",
    }


@pytest.mark.parametrize(
    "catalog, expected_code",
    [
        (BoundCatalog(), "target_binding_unavailable"),
        (BoundCatalog({**VALID_BINDING, "input_contract": "arbitrary.python.v1"}), "target_binding_incompatible"),
    ],
)
def test_mapping_create_rejects_unbound_or_incompatible_ontology_targets(catalog, expected_code):
    repository = MemoryRepository()
    _seed_connector_and_mapping(repository)
    repository.mappings.clear()
    repository.field_mappings.clear()

    with pytest.raises(CapabilityBusinessError) as rejected:
        asyncio.run(app(repository, catalog=catalog).invoke(
            "integration.mapping.create", bound_mapping_payload(), CONTEXT
        ))
    assert error_code(rejected) == expected_code
    assert repository.mappings == {}


def test_mapping_create_rejects_sql_and_persists_only_closed_restricted_fields():
    repository = MemoryRepository()
    _seed_connector_and_mapping(repository)
    repository.mappings.clear()
    repository.field_mappings.clear()
    application = app(repository, catalog=Catalog())

    with pytest.raises(CapabilityBusinessError) as sql:
        asyncio.run(application.invoke(
            "integration.mapping.create",
            mapping_payload(filter_sql="status = 'active'"),
            CONTEXT,
        ))
    assert error_code(sql) == "invalid_input"

    created = asyncio.run(application.invoke(
        "integration.mapping.create",
        mapping_payload(field_mappings=[{
            "source_field": "part_no",
            "target_field": "prop:part_number",
            "transform_expression": "upper(source.part_no)",
        }]),
        CONTEXT,
    ))
    stored = repository.field_mappings[created["gid"]][0]
    assert set(stored) == {
        "gid", "revision", "source_field", "target_field", "transform_expression",
    }
    assert stored["revision"] == 1


def test_field_batch_is_bounded_revision_locked_atomic_and_byte_replayable():
    repository = MemoryRepository()
    _seed_connector_and_mapping(repository)
    application = app(repository, catalog=Catalog())

    with pytest.raises(CapabilityBusinessError) as empty:
        asyncio.run(application.invoke(
            "integration.field_mapping.batch.update",
            {"mapping_gid": "mapping-1", "expected_revision": 1, "items": [], "idempotency_key": "empty"},
            CONTEXT,
        ))
    assert error_code(empty) == "invalid_input"

    items = [
        {"source_field": "part_no", "target_field": "code"},
        {"source_field": "description", "target_field": "prop:description"},
    ]
    payload = {
        "mapping_gid": "mapping-1",
        "expected_revision": 1,
        "items": items,
        "idempotency_key": "batch-1",
    }
    first = asyncio.run(application.invoke("integration.field_mapping.batch.update", payload, CONTEXT))
    replay = asyncio.run(application.invoke("integration.field_mapping.batch.update", payload, CONTEXT))
    assert json.dumps(first, separators=(",", ":"), ensure_ascii=False).encode() == json.dumps(
        replay, separators=(",", ":"), ensure_ascii=False
    ).encode()
    assert first["revision"] == 2
    assert [item["revision"] for item in first["items"]] == [2, 2]
    assert len({item["gid"] for item in first["items"]}) == 2

    before = [dict(item) for item in repository.field_mappings["mapping-1"]]
    with pytest.raises(CapabilityBusinessError) as conflict:
        asyncio.run(application.invoke(
            "integration.field_mapping.batch.update",
            {**payload, "expected_revision": True, "idempotency_key": "batch-boolean-revision"},
            CONTEXT,
        ))
    assert error_code(conflict) == "invalid_input"
    assert repository.field_mappings["mapping-1"] == before


def test_import_retry_reuses_one_durable_run_for_accepted_and_unknown_outcomes():
    repository = MemoryRepository()
    _seed_connector_and_mapping(repository)
    application = app(repository, catalog=Catalog())
    payload = {"mapping_gid": "mapping-1", "idempotency_key": "import-1"}

    accepted = asyncio.run(application.invoke("integration.mapping.import.start", payload, CONTEXT))
    accepted_replay = asyncio.run(application.invoke("integration.mapping.import.start", payload, CONTEXT))
    assert accepted_replay == accepted
    assert len(repository.imports) == 1

    record = repository.operations[accepted["operation_ref"]["operation_id"]]
    application.operations.outcome_unknown(record, error_code="dispatcher_timeout")
    unknown_replay = asyncio.run(application.invoke("integration.mapping.import.start", payload, CONTEXT))
    assert unknown_replay["run_id"] == accepted["run_id"]
    assert unknown_replay["operation_ref"]["status"] == "outcome_unknown"
    assert len(repository.imports) == 1


class CrashBoundaryRepository(MemoryRepository):
    def __init__(self, command):
        super().__init__()
        self.command = command
        self.crash_once = True

    def create_mapping(self, _data):
        raise AssertionError("mapping create must use the atomic command unit of work")

    def replace_field_mappings(self, _data):
        raise AssertionError("field batch must use the atomic command unit of work")

    def execute_mapping_command(self, record, completed, command, data):
        existing = self.find_operation(record.owner_gid, record.capability_id, record.idempotency_key)
        if existing is not None:
            return existing, True
        mappings_before = {key: dict(value) for key, value in self.mappings.items()}
        fields_before = {key: [dict(item) for item in value] for key, value in self.field_mappings.items()}
        try:
            if command == "create":
                MemoryRepository.create_mapping(self, data)
            elif command == "replace_fields":
                MemoryRepository.replace_field_mappings(self, data)
            else:
                raise AssertionError(command)
            if self.crash_once:
                self.crash_once = False
                raise RuntimeError("crash before idempotent success commit")
            self._create_operation(completed)
            return completed, False
        except Exception:
            self.mappings = mappings_before
            self.field_mappings = fields_before
            raise


def test_mapping_create_mutation_and_success_outcome_share_one_crash_safe_unit_of_work():
    repository = CrashBoundaryRepository("create")
    _seed_connector_and_mapping(repository)
    repository.mappings.clear()
    repository.field_mappings.clear()
    application = app(repository, catalog=BoundCatalog(VALID_BINDING))
    payload = bound_mapping_payload(idempotency_key="atomic-create-1")

    with pytest.raises(RuntimeError, match="crash before idempotent success commit"):
        asyncio.run(application.invoke("integration.mapping.create", payload, CONTEXT))
    assert repository.mappings == {}
    assert repository.operations == {}

    recovered = asyncio.run(application.invoke("integration.mapping.create", payload, CONTEXT))
    replay = asyncio.run(application.invoke("integration.mapping.create", payload, CONTEXT))
    assert json.dumps(recovered, separators=(",", ":"), ensure_ascii=False).encode() == json.dumps(
        replay, separators=(",", ":"), ensure_ascii=False
    ).encode()
    assert len(repository.mappings) == 1
    assert repository.operations[recovered_operation_id(repository)].status == "succeeded"


def recovered_operation_id(repository):
    assert len(repository.operations) == 1
    return next(iter(repository.operations))


def test_field_batch_mutation_and_success_outcome_share_one_crash_safe_unit_of_work():
    repository = CrashBoundaryRepository("replace_fields")
    _seed_connector_and_mapping(repository)
    repository.mappings["mapping-1"].update({
        "target_binding_id": VALID_BINDING["binding_id"],
        "target_input_contract": VALID_BINDING["input_contract"],
        "target_resource_gid": VALID_BINDING["resource_gid"],
        "target_expected_version": VALID_BINDING["expected_version"],
    })
    original_fields = [{"gid": "field-old", "revision": 1, "source_field": "old", "target_field": "code"}]
    repository.field_mappings["mapping-1"] = [dict(item) for item in original_fields]
    application = app(repository, catalog=BoundCatalog(VALID_BINDING))
    payload = {
        "mapping_gid": "mapping-1",
        "expected_revision": 1,
        "items": [{"source_field": "part_no", "target_field": "code"}],
        "idempotency_key": "atomic-batch-1",
    }

    with pytest.raises(RuntimeError, match="crash before idempotent success commit"):
        asyncio.run(application.invoke("integration.field_mapping.batch.update", payload, CONTEXT))
    assert repository.mappings["mapping-1"]["revision"] == 1
    assert repository.field_mappings["mapping-1"] == original_fields
    assert repository.operations == {}

    recovered = asyncio.run(application.invoke("integration.field_mapping.batch.update", payload, CONTEXT))
    replay = asyncio.run(application.invoke("integration.field_mapping.batch.update", payload, CONTEXT))
    assert json.dumps(recovered, separators=(",", ":"), ensure_ascii=False).encode() == json.dumps(
        replay, separators=(",", ":"), ensure_ascii=False
    ).encode()
    assert repository.mappings["mapping-1"]["revision"] == 2
    assert repository.operations[recovered_operation_id(repository)].status == "succeeded"
