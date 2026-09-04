"""Agent-owned Capability handlers for the orchestration center."""
from __future__ import annotations

from typing import Any

from .models import GraphDraft
from .metrics import (
    RepositoryWorkloadEvidenceResolver,
    WorkloadMeasurement,
    calculate_automation_ratio_from_evidence,
    calculate_effective_intelligent_work_rate,
)
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


def make_handler(
    capability_id: str, *, repository: OrchestrationRepository,
    resolver: CatalogReferenceResolver,
    authorization_checker_factory=None,
):
    service = OrchestrationService(repository, resolver)
    runtime = OrchestrationRuntime(repository)

    def scope(payload: dict[str, Any], context) -> dict[str, str]:
        effective = getattr(context, "effective_identity", None)
        tenant_gid = getattr(getattr(effective, "tenant", None), "tenant_id", None)
        if not tenant_gid or payload.get("tenant_gid") not in {None, tenant_gid}:
            raise PermissionError("tenant scope must come from authenticated Gateway identity")
        project_gid = payload.get("project_gid")
        if not project_gid:
            raise PermissionError("project scope is required")
        # The fixed Gateway resolves project membership/ABAC before invoking
        # the provider.  Require its server-derived resource reference here;
        # a project_gid appearing only in the request body is never sufficient.
        authorized_refs = set(getattr(context, "resource_refs", ()) or ())
        if f"project:{project_gid}" not in authorized_refs:
            raise PermissionError("project membership is not authorized")
        return {"tenant_gid": tenant_gid, "project_gid": project_gid}

    if capability_id == "agent.orchestration.panorama.read":
        return lambda payload, context: {
            "items": repository.list_panoramas_for_user(
                context.user_gid, **scope(payload, context), limit=payload.get("limit", 50),
            )
        }
    if capability_id == "agent.orchestration.graph.read":
        return lambda payload, context: {"graph": repository.get_graph(
            payload["version_gid"], actor_gid=context.user_gid, **scope(payload, context),
        ).model_dump(mode="json")}
    if capability_id == "agent.orchestration.graph.save":
        def save(payload, context):
            graph = GraphDraft.model_validate(payload["graph"])
            return {"revision": repository.save_graph(
                payload["version_gid"], graph,
                expected_revision=payload["expected_revision"], actor_gid=context.user_gid,
                **scope(payload, context),
            )}
        return save
    if capability_id == "agent.orchestration.version.publish":
        def publish(payload, context):
            publish_service = service
            if authorization_checker_factory is not None:
                publish_service = OrchestrationService(
                    repository,
                    resolver.for_authorization(authorization_checker_factory(context)),
                )
            return publish_service.publish(
                payload["version_gid"], expected_revision=payload["expected_revision"],
                actor_gid=context.user_gid, **scope(payload, context),
            )
        return publish
    if capability_id == "agent.orchestration.binding.delete":
        def delete(payload, context):
            service.delete_capability_binding(
                payload["binding_gid"], actor_gid=context.user_gid, **scope(payload, context),
            )
            return {"deleted": True, "binding_gid": payload["binding_gid"]}
        return delete
    if capability_id == "agent.orchestration.run.start":
        return lambda payload, context: {"run_gid": runtime.start(
            panorama_gid=payload["panorama_gid"], version_gid=payload["version_gid"],
            frozen_context=payload.get("frozen_context", {}), actor_gid=context.user_gid,
            **scope(payload, context),
        )}
    if capability_id == "agent.orchestration.run.transition":
        def transition(payload, context):
            identity = getattr(context, "effective_identity", None)
            consumer_type = getattr(getattr(identity, "consumer", None), "type", None)
            actor_type = getattr(consumer_type, "value", consumer_type) or "user"
            return runtime.advance(
                payload["run_gid"], payload["target_status"],
                authorized_principal_gid=context.user_gid, actor_type=actor_type,
                actor_gid=context.user_gid, payload=payload.get("payload", {}), **scope(payload, context),
            )
        return transition
    if capability_id == "agent.orchestration.metric.read":
        def metric(payload, context):
            bounded_scope = scope(payload, context)
            snapshot = repository.get_metric_for_user(
                payload["panorama_gid"], payload["period_key"], context.user_gid, **bounded_scope,
            )
            selectors = repository.list_workload_measurements_for_user(
                payload["panorama_gid"], payload["period_key"], context.user_gid, **bounded_scope,
            )
            if not selectors:
                # A projected snapshot is not evidence.  It may be returned
                # only when it is an explicit zero baseline; positive values
                # require selector rows whose source hashes/trust were checked
                # by RepositoryWorkloadEvidenceResolver below.
                if any(float(snapshot.get(key) or 0) > 0 for key in (
                    "total_workload_hours", "effective_agent_workload_hours",
                    "effective_intelligent_work_rate", "automation_ratio",
                )):
                    raise PermissionError("trusted workload evidence unavailable")
                return snapshot
            evidence_resolver = RepositoryWorkloadEvidenceResolver(
                repository, actor_gid=context.user_gid, **bounded_scope,
            )
            rate = calculate_effective_intelligent_work_rate(
                [WorkloadMeasurement.model_validate(item) for item in selectors],
                evidence_resolver=evidence_resolver,
            )
            automation = calculate_automation_ratio_from_evidence(
                evidence_resolver=repository, **bounded_scope,
            )
            return {
                "panorama_gid": snapshot["panorama_gid"], "version_gid": snapshot["version_gid"],
                "period_key": snapshot["period_key"],
                "total_workload_hours": float(rate.total_workload_hours),
                "effective_agent_workload_hours": float(rate.effective_agent_workload_hours),
                "effective_intelligent_work_rate": float(rate.rate),
                "automated_workflow_count": automation.automated_workflow_count,
                "total_workflow_count": automation.total_workflow_count,
                "automation_ratio": float(automation.rate),
                "calculated_at": snapshot["calculated_at"],
            }
        return metric
    raise KeyError(f"unknown orchestration capability: {capability_id}")


__all__ = ["ORCHESTRATION_CAPABILITIES", "make_handler"]

