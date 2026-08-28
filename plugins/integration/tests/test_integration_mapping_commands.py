import asyncio
import json

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
    assert json.dumps(first, sort_keys=True, separators=(",", ":")) == json.dumps(
        replay, sort_keys=True, separators=(",", ":")
    )
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
