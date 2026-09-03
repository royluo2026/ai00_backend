"""Governed composition and compatibility preflight for Connector environments."""
from __future__ import annotations

from typing import Any, Mapping

from backend.capability_v2.provider_contracts import (
    CapabilityBusinessError,
    CapabilityContext,
    CapabilityOutput,
    CapabilityRisk,
    CapabilitySpec,
    EvidenceRef,
)
from backend.domain_ports.craft import CraftExecutionPlanPort
from backend.domain_ports.digital_model import ActiveDocumentSnapshotPort
from backend.domain_ports.knowledge import ResourceModelMappingPort

from ..data.environment_repository import EnvironmentManifestRepository, repository
from ..data.document_snapshot_repository import repository as document_snapshot_repository
from ..domain.environment_manifest import REQUIRED_CONNECTOR_OPERATIONS, compose_manifest
from ..application.runtime_ports import (
    craft_execution_port, connector_port, knowledge_mapping_port,
)


class _UnavailableCraftPort:
    def get_execution_plan(self, reference, context):
        raise CapabilityBusinessError("execution_plan_unavailable", "Craft execution-plan port is unavailable", retryable=True)


class _UnavailableKnowledgePort:
    def resolve_resource_models(self, items, context):
        raise CapabilityBusinessError("source_resolver_unavailable", "Knowledge mapping port is unavailable", retryable=True)


class _UnavailableConnectorPort:
    def get_document_snapshot(self, device_id, context):
        raise CapabilityBusinessError("active_document_unavailable", "Connector document port is unavailable", retryable=True)

    def get_health(self, device_id, context):
        raise CapabilityBusinessError("connector_offline", "Connector health port is unavailable", retryable=True)


def _version(value: str) -> tuple[int, ...]:
    try:
        parts = tuple(int(part) for part in value.split("."))
    except (AttributeError, ValueError) as exc:
        raise CapabilityBusinessError("connector_version_incompatible", "Connector reported an invalid product version") from exc
    return parts + (0,) * max(0, 4 - len(parts))


def _resources(execution: Mapping[str, Any]) -> list[dict[str, str]]:
    unique = {
        (str(item["resource_type"]), str(item["code"]))
        for operation in execution.get("operations", ())
        for item in operation.get("resources", ())
    }
    return [{"resource_type": resource_type, "code": code} for resource_type, code in sorted(unique)]


class EnvironmentCompositionProvider:
    def __init__(
        self,
        *,
        repository: EnvironmentManifestRepository,
        craft_port: CraftExecutionPlanPort,
        knowledge_port: ResourceModelMappingPort,
        connector_port: ActiveDocumentSnapshotPort,
        snapshot_repository=document_snapshot_repository,
    ) -> None:
        self.repository = repository
        self.craft_port = craft_port
        self.knowledge_port = knowledge_port
        self.connector_port = connector_port
        self.snapshot_repository = snapshot_repository

    def compose(self, payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
        reference = dict(payload["execution_plan_ref"])
        execution = dict(self.craft_port.get_execution_plan(reference, context))
        source = execution.get("source") or {}
        actual = (
            source.get("bop_version_gid"), source.get("revision"), execution.get("content_hash")
        )
        expected = (reference["version_gid"], reference["revision"], reference["content_hash"])
        if actual != expected:
            raise CapabilityBusinessError(
                "environment_source_changed", "Craft execution plan no longer matches the pinned reference",
                details={"expected": expected, "actual": actual},
            )
        snapshot_request_id = str(payload.get("snapshot_request_id") or "")
        snapshot_row = self.snapshot_repository.get_request(snapshot_request_id, context)
        if not snapshot_row or snapshot_row.get("status") != "completed" or not snapshot_row.get("snapshot"):
            raise CapabilityBusinessError(
                "active_document_snapshot_required",
                "A confirmed asynchronous VisMockup document snapshot is required",
                retryable=True,
            )
        if snapshot_row.get("device_id") != str(payload["device_id"]):
            raise CapabilityBusinessError("bom_identity_mismatch", "The snapshot belongs to another Connector")
        document = snapshot_row["snapshot"]
        mappings = self.knowledge_port.resolve_resource_models(_resources(execution), context)
        result = compose_manifest(execution, document, mappings, payload["capture_profile"])
        problems = [item.model_dump(mode="json") for item in result.problems]
        if result.manifest is None:
            return CapabilityOutput(data={"status": "unresolved", "problems": problems})
        self.repository.insert_manifest(result.manifest, context, name=str(payload["name"]).strip())
        data = result.manifest.model_dump(mode="json")
        return CapabilityOutput(
            data={"status": "composed", "problems": [], **data},
            evidence=(EvidenceRef(
                kind="simulation.environment.manifest",
                reference=f"simulation://environment/{result.manifest.environment_id}/v{result.manifest.environment_version}",
                digest=result.manifest.manifest_hash,
            ),),
        )

    def get_manifest(self, payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
        manifest = self.repository.get_manifest(
            str(payload["environment_id"]), int(payload["environment_version"]), context,
        )
        if manifest is None:
            raise CapabilityBusinessError("simulation_environment_not_found", "Simulation environment manifest not found")
        return CapabilityOutput(data=manifest.model_dump(mode="json"), evidence=(EvidenceRef(
            kind="simulation.environment.manifest",
            reference=f"simulation://environment/{manifest.environment_id}/v{manifest.environment_version}",
            digest=manifest.manifest_hash,
        ),))

    def search(self, payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
        manifests = self.repository.search_manifests(context, limit=int(payload.get("limit") or 50))
        return CapabilityOutput(data={
            "items": [item.model_dump(mode="json") for item in manifests], "total": len(manifests),
        })

    def archive(self, payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
        environment_id = str(payload["environment_id"])
        if not self.repository.archive(environment_id, context):
            raise CapabilityBusinessError("simulation_environment_not_found", "Simulation environment not found")
        return CapabilityOutput(data={"environment_id": environment_id, "status": "archived"})

    def preflight(self, payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
        manifest = self.repository.get_manifest(
            str(payload["environment_id"]), int(payload["environment_version"]), context,
        )
        if manifest is None:
            raise CapabilityBusinessError("simulation_environment_not_found", "Simulation environment manifest not found")
        raw_health = self.connector_port.get_health(str(payload["device_id"]), context)
        health = raw_health.model_dump(mode="json") if hasattr(raw_health, "model_dump") else dict(raw_health)
        requirement = manifest.connector_requirement
        problems: list[dict[str, str | None]] = []

        def add(code: str, expected: Any, actual: Any) -> None:
            problems.append({"code": code, "expected": None if expected is None else str(expected), "actual": None if actual is None else str(actual)})

        if requirement.protocol not in health.get("protocol_versions", ()):
            add("connector_version_incompatible", requirement.protocol, ",".join(health.get("protocol_versions", ())))
        if health.get("bound_user_id") != context.user_gid:
            add("bound_user_mismatch", context.user_gid, health.get("bound_user_id"))
        if not health.get("user_session_present") or not health.get("session_host_ready"):
            add("interactive_session_missing", "ready", "missing")
        if not health.get("system_awake"):
            add("connector_offline", "awake", "not_awake")
        adapter = next((
            item for item in health.get("adapters", ())
            if item.get("adapter_id") == requirement.adapter_id and item.get("adapter_major") == requirement.adapter_major
        ), None)
        if adapter is None:
            add("adapter_unavailable", f"{requirement.adapter_id}@{requirement.adapter_major}", None)
        else:
            product_version = str(adapter.get("product_version") or "")
            if adapter.get("product_id") != requirement.product_id or not (
                _version(requirement.minimum_product_version) <= _version(product_version)
                < _version(requirement.maximum_product_version_exclusive)
            ):
                add(
                    "connector_version_incompatible",
                    f"{requirement.product_id}>={requirement.minimum_product_version},<{requirement.maximum_product_version_exclusive}",
                    f"{adapter.get('product_id')}@{product_version}",
                )
            advertised = {item.get("operation_id"): item.get("contract_hash") for item in adapter.get("operations", ())}
            for operation in requirement.operations:
                if advertised.get(operation.operation_id) != operation.contract_hash:
                    add("adapter_contract_mismatch", f"{operation.operation_id}:{operation.contract_hash}", advertised.get(operation.operation_id))
        problems.sort(key=lambda item: (str(item["code"]), str(item["expected"]), str(item["actual"])))
        return CapabilityOutput(data={"compatible": not problems, "problems": problems})


default_provider = EnvironmentCompositionProvider(
    repository=repository,
    craft_port=craft_execution_port,
    knowledge_port=knowledge_mapping_port,
    connector_port=connector_port,
    snapshot_repository=document_snapshot_repository,
)


def specs(provider: EnvironmentCompositionProvider = default_provider):
    common = {
        "owner": "simulation", "version": 1, "permissions": ("simulation.use",),
        "plugin_callable": True, "tags": ("simulation", "connector_environment"),
    }
    return (
        (CapabilitySpec(id="simulation.environment.compose", description="Compose an immutable Connector environment from pinned owning-domain sources.", risk=CapabilityRisk.WRITE, confirmation="user", **common), provider.compose),
        (CapabilitySpec(id="simulation.environment.manifest.get", description="Read one immutable Connector environment manifest.", risk=CapabilityRisk.READ, confirmation="none", **common), provider.get_manifest),
        (CapabilitySpec(id="simulation.environment.manifest.search", description="Search visible Connector environment manifests.", risk=CapabilityRisk.READ, confirmation="none", **common), provider.search),
        (CapabilitySpec(id="simulation.environment.manifest.archive", description="Archive a Connector environment identity without mutating its manifests.", risk=CapabilityRisk.WRITE, confirmation="user", **common), provider.archive),
        (CapabilitySpec(id="simulation.environment.preflight", description="Check exact Connector and VisMockup compatibility without queuing work.", risk=CapabilityRisk.READ, confirmation="none", **common), provider.preflight),
    )


__all__ = ["EnvironmentCompositionProvider", "REQUIRED_CONNECTOR_OPERATIONS", "default_provider", "specs"]
