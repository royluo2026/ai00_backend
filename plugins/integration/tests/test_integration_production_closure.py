from __future__ import annotations

import inspect
import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

from backend.capability_v2.contracts import (
    ActorIdentity, CapabilityStatus, ConsumerDescriptor, ConsumerIdentity, ConsumerType,
    CorrelationRef, TenantIdentity,
)
from backend.capability_v2.domain_client import DomainCapabilityClient

from plugins.integration.integration_backend.application.service import IntegrationApplication
from plugins.integration.integration_backend.capabilities.descriptors import INTEGRATION_CAPABILITY_IDS
from plugins.integration.integration_backend.infrastructure.target_catalog import IntegrationTargetCatalog


def test_production_composition_exposes_import_dispatcher():
    from plugins.integration.integration_backend.capabilities import wiring

    assert callable(getattr(wiring, "build_import_dispatcher", None))


def test_target_catalog_has_governed_binding_writer():
    signature = inspect.signature(IntegrationTargetCatalog.upsert_mapping_target)
    assert {"actor_gid", "team_gid", "expected_revision", "idempotency_key"} <= set(signature.parameters)


def test_binding_writer_is_a_first_class_integration_capability():
    assert "integration.mapping_target.upsert" in INTEGRATION_CAPABILITY_IDS


def test_binding_upsert_is_actor_team_scoped_revisioned_and_idempotent():
    from plugins.integration.tests.test_integration_owner_services import CONTEXT, MemoryRepository, app

    class Catalog:
        def __init__(self):
            self.calls = []

        def upsert_mapping_target(self, **data):
            self.calls.append(data)
            return {
                "binding_id": data["binding_id"], "ontology_object_gid": data["ontology_object_gid"],
                "target_domain": data["target_domain"], "target_capability_id": data["target_capability_id"],
                "target_major_version": data["target_major_version"],
                "minimum_catalog_release": data["minimum_catalog_release"],
                "resource_gid": data["resource_gid"], "expected_version": data["target_expected_version"],
                "revision": 1,
            }

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

    assert replay == first
    assert len(catalog.calls) == 1
    assert (catalog.calls[0]["actor_gid"], catalog.calls[0]["team_gid"]) == ("actor-1", "team-1")


def test_preview_uses_canonical_detector_for_aliases_uris_and_pem():
    samples = (
        {"passwd": "hunter2"},
        {"pwd": "hunter2"},
        {"access_key": "AKIA-test"},
        "postgresql://user:secret@example.test/db",
        "-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----",
    )
    assert all(IntegrationApplication._secret_exposed(value) for value in samples)


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
        actor=ActorIdentity(service_id="integration-sync", authentication_method="service-token", authenticated_at=datetime.now(UTC)),
        tenant=TenantIdentity(tenant_id="team-1", membership="service"),
        consumer=ConsumerDescriptor(type=ConsumerType.WORKER, consumer_id="domain.integration"),
    )
    dispatcher = build_import_dispatcher(lambda: IntegrationProviderAdapters(
        repository=repository, credential_enrollment=object(), catalog=catalog,
        connector_runtime=Runtime(), target_client=client, worker_identity=identity,
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
