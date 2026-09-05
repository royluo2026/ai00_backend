from __future__ import annotations

from typing import Any, Protocol

from .models import GraphDraft
from .reference_resolver import ResolvedCapabilityBinding


class PublishBlocked(RuntimeError):
    pass


class ReferenceResolver(Protocol):
    def resolve_many(self, refs: list[dict[str, str]], actor_gid: str) -> list[dict[str, Any]]: ...

    def resolve_capability_binding(
        self, version_gid: str, actor_gid: str
    ) -> ResolvedCapabilityBinding: ...


class OrchestrationService:
    def __init__(self, repository: Any, reference_resolver: ReferenceResolver):
        self.repository = repository
        self.reference_resolver = reference_resolver

    def publish(
        self, version_gid: str, *, expected_revision: int, actor_gid: str,
        tenant_gid: str, project_gid: str,
    ) -> Any:
        scope = {
            key: value for key, value in {
                "tenant_gid": tenant_gid, "project_gid": project_gid,
            }.items() if value is not None
        }
        graph: GraphDraft = self.repository.get_graph(
            version_gid, actor_gid=actor_gid, **scope,
        )
        self._validate_business_contract(graph)
        resolved_capabilities = {
            version: self.reference_resolver.resolve_capability_binding(version, actor_gid)
            for version in {binding.capability_version_gid for binding in graph.capability_bindings}
        }
        refs = [
            {"ref_type": binding.ref_type, "ref_gid": binding.ref_gid}
            for binding in graph.context_bindings
        ]
        resolved = self.reference_resolver.resolve_many(refs, actor_gid) if refs else []
        missing = [item.get("ref_gid", "unknown") for item in resolved if not item.get("resolved")]
        if missing:
            raise PublishBlocked(f"unresolved governed references: {', '.join(missing)}")
        trusted_bindings = []
        for binding in graph.capability_bindings:
            trusted = resolved_capabilities[binding.capability_version_gid]
            trusted_bindings.append({
                "binding_gid": binding.gid,
                **trusted,
                "timeout_seconds": binding.timeout_seconds,
                "retry_policy": binding.retry_policy,
                "fallback_policy": binding.fallback_policy,
            })
        return self.repository.publish_version(
            version_gid,
            expected_revision=expected_revision,
            actor_gid=actor_gid,
            resolved_bindings=trusted_bindings,
            **scope,
        )

    def delete_capability_binding(
        self, binding_gid: str, *, actor_gid: str,
        tenant_gid: str, project_gid: str,
    ) -> None:
        scope = {
            key: value for key, value in {
                "tenant_gid": tenant_gid, "project_gid": project_gid,
            }.items() if value is not None
        }
        self.repository.delete_binding(binding_gid, actor_gid=actor_gid, **scope)

    @staticmethod
    def _validate_business_contract(graph: GraphDraft) -> None:
        if not graph.nodes:
            raise PublishBlocked("business graph must contain at least one node")
        required = ("objective", "owner_ref", "inputs", "outputs", "acceptance_criteria")
        for node in graph.nodes:
            missing = [field for field in required if not getattr(node, field)]
            if missing:
                raise PublishBlocked(f"node {node.gid} missing {', '.join(missing)}")
