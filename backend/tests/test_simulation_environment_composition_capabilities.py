from __future__ import annotations

import asyncio

from backend.capabilities.models_next import CapabilityContext
from backend.capabilities.confirmation_next import confirmation_manager
from backend.capabilities.registry_next import CapabilityRegistry
from plugins.simulation.simulation_backend.capabilities import register_capabilities
from plugins.simulation.simulation_backend.capabilities.environment_composition import (
    EnvironmentCompositionProvider,
    REQUIRED_CONNECTOR_OPERATIONS,
)


def _model(suffix: str):
    return {
        "model_id": f"model-{suffix}", "version_id": f"version-{suffix}",
        "snapshot_hash": "sha256:" + suffix[0] * 64,
        "artifact_ref": {
            "artifact_id": f"artifact-{suffix}", "media_type": "model/step",
            "sha256": suffix[0] * 64, "byte_size": 100, "version": 1,
        },
    }


def _execution(product="P-10", resource="T-10"):
    return {
        "source": {"bop_version_gid": "bop-1", "revision": 7, "project_gid": "project-1"},
        "content_hash": "sha256:" + "a" * 64,
        "operations": [{
            "operation_id": "op-10", "sequence": 10, "predecessor_ids": [],
            "products": [{"product_ref": product, "action": "install"}],
            "resources": [{"resource_type": "tool", "code": resource}],
        }],
    }


def _document():
    return {
        "document_id": "BOM-1", "root_node_key": "bom-root",
        "source_identity": "tc://item/BOM-1/revision/A",
        "snapshot_hash": "sha256:" + "b" * 64,
        "nodes": [
            {"node_key": "bom-root", "parent_key": None, "product_ref": "ROOT", "child_order": 0},
            {"node_key": "bom-node-10", "parent_key": "bom-root", "product_ref": "P-10", "child_order": 1},
        ],
    }


def _payload():
    return {
        "name": "Line capture", "device_id": "device-1",
        "snapshot_request_id": "snapshot-1",
        "execution_plan_ref": {
            "version_gid": "bop-1", "revision": 7, "content_hash": "sha256:" + "a" * 64,
        },
        "capture_profile": {"format": "png", "width": 1920, "height": 1080, "background": "current"},
    }


class Repository:
    def __init__(self):
        self.manifests = {}

    def insert_manifest(self, manifest, context, *, name=None):
        key = manifest.environment_id, manifest.environment_version
        assert key not in self.manifests
        self.manifests[key] = manifest

    def get_manifest(self, environment_id, environment_version, context):
        return self.manifests.get((environment_id, environment_version))

    def search_manifests(self, context, *, limit=50):
        return tuple(self.manifests.values())[:limit]

    def archive(self, environment_id, context):
        return any(key[0] == environment_id for key in self.manifests)


class CraftPort:
    def __init__(self, execution=None): self.execution = execution or _execution()
    async def get_execution_plan(self, ref, context): return self.execution


class KnowledgePort:
    def __init__(self, *, unresolved=False): self.unresolved = unresolved
    async def resolve_resource_models(self, items, context):
        if self.unresolved:
            return {
                "resolved": [],
                "unresolved": [{"resource_type": "tool", "code": "T-10", "normalized_code": "t-10"}],
                "ambiguous": [], "mapping_snapshot_hash": "sha256:" + "c" * 64,
            }
        return {
            "resolved": [{"resource_type": "tool", "code": "T-10", "normalized_code": "t-10", "model_ref": _model("10")}],
            "unresolved": [], "ambiguous": [], "mapping_snapshot_hash": "sha256:" + "c" * 64,
        }


class ConnectorPort:
    async def get_health(self, device_id, context):
        return {
            "protocol_versions": ["ai00.connector.execution-plan.v1"],
            "bound_user_id": context.user_gid,
            "user_session_present": True, "session_host_ready": True, "system_awake": True,
            "adapters": [{
                "adapter_id": "ai00.vismockup", "adapter_major": 1,
                "product_id": "siemens.vismockup", "product_version": "14.0.0",
                "operations": [
                    {"operation_id": operation_id, "contract_hash": contract_hash}
                    for operation_id, contract_hash in REQUIRED_CONNECTOR_OPERATIONS.items()
                ],
            }],
        }


class SnapshotRepository:
    def get_request(self, request_id, context):
        if request_id != "snapshot-1": return None
        return {"snapshot_request_id": request_id, "device_id": "device-1", "status": "completed", "snapshot": _document()}


def _provider(*, unresolved=False):
    repository = Repository()
    provider = EnvironmentCompositionProvider(
        repository=repository, craft_port=CraftPort(),
        knowledge_port=KnowledgePort(unresolved=unresolved), connector_port=ConnectorPort(),
        snapshot_repository=SnapshotRepository(),
    )
    return provider, repository


def _context():
    return CapabilityContext(user_gid="user-1", team_gid="team-1", source="agent")


def test_compose_persists_one_manifest_when_all_bindings_resolve():
    provider, repository = _provider()

    output = asyncio.run(provider.compose(_payload(), _context())).data

    assert output["status"] == "composed"
    assert output["manifest_hash"].startswith("sha256:")
    assert len(repository.manifests) == 1


def test_compose_returns_every_problem_and_persists_nothing():
    provider, repository = _provider(unresolved=True)
    provider.craft_port = CraftPort(_execution(product="P-X"))

    output = asyncio.run(provider.compose(_payload(), _context())).data

    assert output["status"] == "unresolved"
    assert {item["source_code"] for item in output["problems"]} == {"P-X", "T-10"}
    assert repository.manifests == {}


def test_preflight_checks_exact_connector_contracts_without_queueing_work():
    provider, _ = _provider()
    composed = asyncio.run(provider.compose(_payload(), _context())).data

    report = asyncio.run(provider.preflight({
        "environment_id": composed["environment_id"],
        "environment_version": composed["environment_version"],
        "device_id": "device-1",
    }, _context())).data

    assert report == {"compatible": True, "problems": []}


def test_registration_adds_new_major_one_capabilities_without_changing_legacy_schema():
    registry = CapabilityRegistry()
    register_capabilities(registry, composition_provider=_provider()[0])

    assert registry.get("simulation.environment.compose", 1).descriptor.lifecycle_status == "stable"
    assert registry.get("simulation.environment.preflight", 1).descriptor.side_effect_level == "read"
    compose = registry.get("simulation.environment.compose", 1).descriptor
    assert {item.resource_type for item in compose.resource_selectors} == {"craft-bop-version", "device"}
    retryability = {item.code: item.retryable for item in compose.domain_errors}
    assert retryability["connector_offline"] is True
    assert retryability["adapter_contract_mismatch"] is False
    assert retryability["local_execution_outcome_unknown"] is False
    legacy = registry.get("simulation.environment.get", 1)
    assert set(legacy.spec.output_schema["properties"]) == {"environment_id", "name", "status", "source"}


def test_compose_contract_validates_through_registry_boundary():
    registry = CapabilityRegistry()
    register_capabilities(registry, composition_provider=_provider()[0])
    payload = _payload()
    token = confirmation_manager.issue(
        "simulation.environment.compose", 1, "user-1", payload,
    )
    context = CapabilityContext(
        user_gid="user-1", team_gid="team-1", source="agent",
        permissions=("simulation.use",), confirmation_token=token,
    )

    result = asyncio.run(registry.invoke(
        "simulation.environment.compose", payload, context, version=1,
    ))

    assert result.data["status"] == "composed"
    assert result.evidence[0].digest == result.data["manifest_hash"]
