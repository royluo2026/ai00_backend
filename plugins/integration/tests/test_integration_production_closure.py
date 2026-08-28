from __future__ import annotations

import asyncio
import pytest
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

from backend.capability_v2.contracts import (
    ActorIdentity, CapabilityStatus, ConsumerDescriptor, ConsumerIdentity, ConsumerType,
    CorrelationRef, TenantIdentity,
)
from backend.capability_v2.domain_client import DomainCapabilityClient
from backend.capability_v2.provider_contracts import CapabilityContext

from plugins.integration.integration_backend.application.service import IntegrationApplication
from plugins.integration.integration_backend.capabilities.descriptors import INTEGRATION_CAPABILITY_IDS
from plugins.integration.integration_backend.infrastructure.target_catalog import IntegrationTargetCatalog


def test_production_composition_exposes_import_dispatcher():
    from plugins.integration.integration_backend.capabilities import wiring

    assert callable(getattr(wiring, "build_import_dispatcher", None))


def test_target_catalog_has_no_direct_steady_state_binding_writer():
    assert not hasattr(IntegrationTargetCatalog, "upsert_mapping_target")


def test_binding_writer_is_a_first_class_integration_capability():
    assert "integration.mapping_target.upsert" in INTEGRATION_CAPABILITY_IDS


def test_binding_upsert_is_actor_team_scoped_revisioned_and_idempotent():
    from plugins.integration.tests.test_integration_owner_services import CONTEXT, MemoryRepository, app

    class Catalog:
        def __init__(self):
            self.calls = []

        def validate_mapping_target(self, data):
            self.calls.append(data)
            return dict(data)

    payload = {
        "binding_id": "ontology:concept-part", "ontology_object_gid": "concept-part",
        "target_domain": "knowledge", "target_capability_id": "knowledge.reference_dataset.publish",
        "target_major_version": 1, "minimum_catalog_release": "rel_7803705d3df421f9f4381d37c3500731",
        "input_contract": "knowledge.reference_dataset.publish.v1", "resource_gid": "dataset-parts",
        "target_expected_version": 7, "idempotency_key": "binding-upsert-1",
    }
    catalog = Catalog()
    application = app(MemoryRepository(), catalog=catalog)

    first = asyncio.run(application.invoke("integration.mapping_target.upsert", payload, CONTEXT))
    replay = asyncio.run(application.invoke("integration.mapping_target.upsert", payload, CONTEXT))

    actor_two = CapabilityContext(user_gid="actor-2", team_gid="team-1", request_id="request-2")
    actor_two_payload = {
        **payload, "resource_gid": "dataset-parts-v2", "target_expected_version": 8,
        "expected_revision": 1, "idempotency_key": "binding-upsert-actor-2",
    }
    rebound = asyncio.run(application.invoke(
        "integration.mapping_target.upsert", actor_two_payload, actor_two,
    ))
    rebound_replay = asyncio.run(application.invoke(
        "integration.mapping_target.upsert", actor_two_payload, actor_two,
    ))

    assert replay == first
    assert rebound_replay == rebound and rebound["revision"] == 2
    assert application.repository.bindings[("team-1", "ontology:concept-part")]["owner_gid"] == "actor-1"
    assert len(catalog.calls) == 4
    assert catalog.calls[0]["target_domain"] == "knowledge"


def test_preview_uses_canonical_detector_for_aliases_uris_and_pem():
    samples = (
        {"passwd": "hunter2"},
        {"pwd": "hunter2"},
        {"access_key": "AKIA-test"},
        "postgresql://user:secret@example.test/db",
        "-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----",
    )
    assert all(IntegrationApplication._secret_exposed(value) for value in samples)


def test_governed_binding_writer_rebinds_legacy_mapping_and_conflicts_on_changed_replay():
    from plugins.integration.tests.test_integration_owner_services import CONTEXT, Catalog, MemoryRepository, app

    repository = MemoryRepository()
    repository.mappings["legacy-1"] = {
        "gid": "legacy-1", "owner_gid": "actor-1", "team_gid": "team-1", "revision": 3,
        "status": "binding_required", "datasource_gid": "connector-1", "name": "legacy", "source_object": "parts",
    }
    payload = {
        "binding_id": "ontology:concept-part", "ontology_object_gid": "concept-part",
        "target_domain": "knowledge", "target_capability_id": "knowledge.reference_dataset.publish",
        "target_major_version": 1, "minimum_catalog_release": "rel_7803705d3df421f9f4381d37c3500731",
        "input_contract": "knowledge.reference_dataset.publish.v1", "resource_gid": "dataset-parts",
        "target_expected_version": 7, "mapping_gid": "legacy-1", "mapping_expected_revision": 3,
        "idempotency_key": "binding-rebind-1",
    }
    application = app(repository, catalog=Catalog())

    result = asyncio.run(application.invoke("integration.mapping_target.upsert", payload, CONTEXT))
    replay = asyncio.run(application.invoke("integration.mapping_target.upsert", payload, CONTEXT))

    assert result["mapping_revision"] == 4 and replay == result
    assert repository.mappings["legacy-1"]["status"] == "active"
    with pytest.raises(Exception, match="idempotency"):
        asyncio.run(application.invoke(
            "integration.mapping_target.upsert", {**payload, "resource_gid": "dataset-other"}, CONTEXT
        ))


def test_production_composed_dispatcher_claims_started_run_once_and_reaches_domain_client():
    from plugins.integration.integration_backend.capabilities.wiring import (
        IntegrationProviderAdapters, build_import_dispatcher,
    )
    from plugins.integration.tests.test_integration_mapping_commands import BoundCatalog, VALID_BINDING
    from plugins.integration.tests.test_integration_owner_services import (
        CONTEXT, MemoryRepository, _seed_connector_and_mapping, app,
    )

    class Repository(MemoryRepository):
        def claim_next_import_run(self, worker_id):
            for run in self.imports:
                if run["status"] == "accepted":
                    run.update(status="claimed", claim_token=f"{worker_id}:1")
                    return dict(run)
            return None

        def transition_import_run(self, **data):
            run = next(item for item in self.imports if item["run_id"] == data["run_id"])
            assert run["claim_token"] == data["claim_token"]
            run["status"] = data["status"]
            operation = self.operations[run["operation_id"]]
            self.operations[run["operation_id"]] = replace(
                operation, status=data["status"], version=operation.version + 1,
                result={**dict(operation.result or {}), **dict(data.get("result") or {})},
                error_code=data.get("error_code"),
            )
            return {"run_id": run["run_id"], "status": run["status"]}

        def mark_target_invocation(self, **data):
            run = next(item for item in self.imports if item["run_id"] == data["run_id"])
            run.update(target_invocation=data["target_invocation"], target_dispatched_at=datetime.now(UTC),
                       target_idempotency_key=data["target_idempotency_key"])
            return {"target_dispatched_at": run["target_dispatched_at"], "target_idempotency_key": run["target_idempotency_key"]}

    class Catalog(BoundCatalog):
        def upsert_mapping_target(self, **_data):
            raise AssertionError("not used")

    class Runtime:
        async def preview(self, connector, mapping, *, timeout_seconds, result_limit):
            assert connector["gid"] == "connector-1" and mapping["gid"] == "mapping-1"
            assert (timeout_seconds, result_limit) == (15, 200)
            return {"rows": [{"part_no": "P-1"}]}

    class Client(DomainCapabilityClient):
        def __init__(self):
            self.calls = []

        async def invoke(self, invocation, identity, correlation, deadline=None):
            self.calls.append((invocation, identity, correlation))
            return SimpleNamespace(ok=True, status=CapabilityStatus.COMPLETED, data={"version_no": 8})

    repository = Repository()
    _seed_connector_and_mapping(repository)
    repository.field_mappings["mapping-1"] = [
        {"source_field": "part_no", "target_field": "code"}
    ]
    catalog, client = Catalog(VALID_BINDING), Client()
    started = asyncio.run(app(repository, runtime=Runtime(), catalog=catalog).invoke(
        "integration.mapping.import.start",
        {"mapping_gid": "mapping-1", "idempotency_key": "import-worker-1"},
        CONTEXT,
    ))
    identity = ConsumerIdentity(
        actor=ActorIdentity(user_id="actor-1", authentication_method="persisted-operation", authenticated_at=datetime.now(UTC)),
        tenant=TenantIdentity(tenant_id="team-1", membership="service"),
        consumer=ConsumerDescriptor(type=ConsumerType.WORKER, consumer_id="domain.integration"),
    )
    dispatcher = build_import_dispatcher(lambda: IntegrationProviderAdapters(
        repository=repository, credential_enrollment=object(), catalog=catalog,
        connector_runtime=Runtime(), target_client=client, worker_identity_factory=lambda _run: identity,
    ))

    terminal = asyncio.run(dispatcher.dispatch_next(
        worker_id="worker-1", correlation=CorrelationRef(request_id="req-1", trace_id="trace-1")
    ))

    assert terminal == {"run_id": started["run_id"], "status": "succeeded"}
    assert asyncio.run(dispatcher.dispatch_next(
        worker_id="worker-2", correlation=CorrelationRef(request_id="req-2", trace_id="trace-2")
    )) is None
    invocation = client.calls[0][0]
    assert invocation.payload["rows"] == [{"key": "1", "values": [{"field": "code", "value": "P-1"}]}]
