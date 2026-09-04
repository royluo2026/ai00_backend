"""Agent-owned Capability handlers for the orchestration center."""
from __future__ import annotations

from typing import Any

from .models import GraphDraft
from .reference_resolver import CatalogReferenceResolver
from .repository import OrchestrationRepository
from .service import OrchestrationService
from .runtime import OrchestrationRuntime


ORCHESTRATION_CAPABILITIES = frozenset({
    "agent.orchestration.panorama.read", "agent.orchestration.graph.read",
    "agent.orchestration.graph.save", "agent.orchestration.version.publish",
    "agent.orchestration.binding.delete", "agent.orchestration.run.start",
    "agent.orchestration.run.transition", "agent.orchestration.metric.read",
})


def make_handler(capability_id: str, *, repository: OrchestrationRepository, resolver: CatalogReferenceResolver):
    service = OrchestrationService(repository, resolver)
    runtime = OrchestrationRuntime(repository)

    def scope(payload: dict[str, Any]) -> dict[str, str]:
        return {"tenant_gid": payload["tenant_gid"], "project_gid": payload["project_gid"]}

    if capability_id == "agent.orchestration.panorama.read":
        return lambda payload, context: {
            "items": repository.list_panoramas_for_user(
                context.user_gid, **scope(payload), limit=payload.get("limit", 50),
            )
        }
    if capability_id == "agent.orchestration.graph.read":
        return lambda payload, context: repository.get_graph(
            payload["version_gid"], actor_gid=context.user_gid, **scope(payload),
        ).model_dump(mode="json")
    if capability_id == "agent.orchestration.graph.save":
        def save(payload, context):
            graph = GraphDraft.model_validate(payload["graph"])
            return {"revision": repository.save_graph(
                payload["version_gid"], graph,
                expected_revision=payload["expected_revision"], actor_gid=context.user_gid,
                **scope(payload),
            )}
        return save
    if capability_id == "agent.orchestration.version.publish":
        def publish(payload, context):
            return service.publish(
                payload["version_gid"], expected_revision=payload["expected_revision"],
                actor_gid=context.user_gid, **scope(payload),
            )
        return publish
    if capability_id == "agent.orchestration.binding.delete":
        def delete(payload, context):
            service.delete_capability_binding(
                payload["binding_gid"], actor_gid=context.user_gid, **scope(payload),
            )
            return {"deleted": True, "binding_gid": payload["binding_gid"]}
        return delete
    if capability_id == "agent.orchestration.run.start":
        return lambda payload, context: {"run_gid": runtime.start(
            panorama_gid=payload["panorama_gid"], version_gid=payload["version_gid"],
            frozen_context=payload.get("frozen_context", {}), actor_gid=context.user_gid,
            **scope(payload),
        )}
    if capability_id == "agent.orchestration.run.transition":
        return lambda payload, context: runtime.advance(
            payload["run_gid"], payload["target_status"],
            authorized_principal_gid=context.user_gid, actor_type=payload.get("actor_type", "agent"),
            actor_gid=context.user_gid, payload=payload.get("payload", {}), **scope(payload),
        )
    if capability_id == "agent.orchestration.metric.read":
        return lambda payload, context: repository.get_metric_for_user(
            payload["panorama_gid"], payload["period_key"], context.user_gid, **scope(payload),
        )
    raise KeyError(f"unknown orchestration capability: {capability_id}")


__all__ = ["ORCHESTRATION_CAPABILITIES", "make_handler"]
