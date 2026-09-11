"""Atomic governed access to editable VisMockup alternate hierarchies."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.capability_v2.contracts import CorrelationRef
from backend.capability_v2.domain_client import DomainInvocation

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext, CapabilityOutput, CapabilitySpec, EvidenceRef

from ..data.workspace_repository import WorkspaceRepository, WorkspaceRepositoryError


def _scope(context: CapabilityContext) -> tuple[str, str]:
    tenant_gid, actor_gid = str(context.team_gid or ""), str(context.user_gid or "")
    if not tenant_gid or not actor_gid:
        raise CapabilityBusinessError("workspace_identity_required", "workspace_identity_required")
    return tenant_gid, actor_gid


def _output(data: Any, action: str, identity: str) -> CapabilityOutput:
    body = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return CapabilityOutput(data=data, evidence=(EvidenceRef(kind="simulation.environment.alternate_hierarchy",
        reference=f"simulation://alternate-hierarchy/{identity}", digest="sha256:" + hashlib.sha256(body.encode()).hexdigest(), summary=action),))


class AlternateHierarchyProvider:
    def __init__(self, repository: WorkspaceRepository | None = None) -> None: self.repository = repository or WorkspaceRepository()

    def search(self, payload, context):
        tenant_gid, actor_gid = _scope(context); workspace_gid = str(payload.get("workspace_gid") or "")
        try: return _output(self.repository.search_alternate_hierarchies(workspace_gid=workspace_gid, tenant_gid=tenant_gid, actor_gid=actor_gid), "alternate_hierarchies_searched", workspace_gid)
        except WorkspaceRepositoryError as exc: raise CapabilityBusinessError(str(exc), str(exc)) from exc

    def get(self, payload, context):
        tenant_gid, actor_gid = _scope(context); hierarchy_gid = str(payload.get("hierarchy_gid") or "")
        try: row = self.repository.get_alternate_hierarchy(hierarchy_gid=hierarchy_gid, tenant_gid=tenant_gid, actor_gid=actor_gid)
        except WorkspaceRepositoryError as exc: raise CapabilityBusinessError(str(exc), str(exc)) from exc
        if not row: raise CapabilityBusinessError("alternate_hierarchy_not_found", "alternate_hierarchy_not_found")
        return _output(row, "alternate_hierarchy_loaded", hierarchy_gid)

    def create(self, payload, context):
        tenant_gid, actor_gid = _scope(context); workspace_gid = str(payload.get("workspace_gid") or "")
        try: data = self.repository.create_alternate_hierarchy(workspace_gid=workspace_gid, name=str(payload.get("name") or ""), source_bop_version_gid=None, expected_workspace_version=payload.get("expected_row_version"), actor_gid=actor_gid, tenant_gid=tenant_gid, idempotency_key=str(payload.get("idempotency_key") or ""))
        except WorkspaceRepositoryError as exc: raise CapabilityBusinessError(str(exc), str(exc), retryable=str(exc) == "version_conflict") from exc
        return _output(data, "alternate_hierarchy_created", str(data["hierarchy_gid"]))

    async def bootstrap_from_bop_fork(self, payload, context):
        tenant_gid, actor_gid = _scope(context)
        client = getattr(context, "domain_client", None)
        identity = getattr(context, "effective_identity", None)
        if client is None or identity is None:
            raise CapabilityBusinessError("domain_client_unavailable", "domain_client_unavailable")
        request_id = str(context.request_id or payload.get("idempotency_key") or "bop-bootstrap")
        projection = await client.invoke(
            DomainInvocation(capability_id="craft.bop.fork_projection.get", major_version=1,
                             payload={"fork_run_gid": str(payload.get("fork_run_gid") or "")}),
            identity, CorrelationRef(request_id=request_id, trace_id=request_id),
        )
        if not projection.ok:
            code = projection.error.code if projection.error else "bop_fork_projection_failed"
            raise CapabilityBusinessError(code, code, retryable=True)
        try:
            data = self.repository.bootstrap_alternate_hierarchy(
                workspace_gid=str(payload.get("workspace_gid") or ""), name=str(payload.get("name") or ""),
                projection=projection.data, expected_workspace_version=payload.get("expected_row_version"),
                actor_gid=actor_gid, tenant_gid=tenant_gid,
                idempotency_key=str(payload.get("idempotency_key") or ""),
            )
        except WorkspaceRepositoryError as exc:
            raise CapabilityBusinessError(str(exc), str(exc), retryable=str(exc) in {"version_conflict", "bop_bootstrap_pending"}) from exc
        return _output(data, "alternate_hierarchy_bootstrapped", str(data["hierarchy_gid"]))

    def _mutate_hierarchy(self, operation, payload, context):
        tenant_gid,actor_gid=_scope(context);hierarchy_gid=str(payload.get("hierarchy_gid") or "")
        try:data=self.repository.mutate_alternate_hierarchy(hierarchy_gid=hierarchy_gid,expected_hierarchy_version=payload.get("expected_row_version"),operation=operation,values={"name":payload.get("name")} if operation=="update" else {},actor_gid=actor_gid,tenant_gid=tenant_gid,idempotency_key=str(payload.get("idempotency_key") or ""))
        except WorkspaceRepositoryError as exc:raise CapabilityBusinessError(str(exc),str(exc),retryable=str(exc)=="version_conflict") from exc
        return _output(data,f"alternate_hierarchy_{operation}d",hierarchy_gid)

    def update(self,payload,context):return self._mutate_hierarchy("update",payload,context)
    def archive(self,payload,context):return self._mutate_hierarchy("archive",payload,context)

    def create_placement(self, payload, context):
        tenant_gid, actor_gid = _scope(context); hierarchy_gid = str(payload.get("hierarchy_gid") or "")
        try: data = self.repository.add_placement(hierarchy_gid=hierarchy_gid, target_node_gid=str(payload.get("target_node_gid") or ""), parent_placement_gid=payload.get("parent_placement_gid"), source_kind=str(payload.get("source_kind") or ""), source_ref=payload.get("source_ref") or {}, transform=payload.get("transform") or [], expected_hierarchy_version=payload.get("expected_row_version"), actor_gid=actor_gid, tenant_gid=tenant_gid, display_name=str(payload.get("display_name") or ""), idempotency_key=str(payload.get("idempotency_key") or ""))
        except WorkspaceRepositoryError as exc: raise CapabilityBusinessError(str(exc), str(exc), retryable=str(exc) == "version_conflict") from exc
        return _output(data, "placement_created", hierarchy_gid)

    def _mutate_placement(self,operation,payload,context):
        tenant_gid,actor_gid=_scope(context);placement_gid=str(payload.get("placement_gid") or "")
        try:data=self.repository.mutate_placement(placement_gid=placement_gid,expected_hierarchy_version=payload.get("expected_row_version"),operation=operation,values={"parent_placement_gid":payload.get("parent_placement_gid")} if operation=="move" else {},actor_gid=actor_gid,tenant_gid=tenant_gid,idempotency_key=str(payload.get("idempotency_key") or ""))
        except WorkspaceRepositoryError as exc:raise CapabilityBusinessError(str(exc),str(exc),retryable=str(exc)=="version_conflict") from exc
        return _output(data,f"placement_{operation}d",placement_gid)

    def move_placement(self,payload,context):return self._mutate_placement("move",payload,context)
    def remove_placement(self,payload,context):return self._mutate_placement("remove",payload,context)


def specs(provider: AlternateHierarchyProvider | None = None):
    selected = provider or AlternateHierarchyProvider(); gid={"type":"string","pattern":"^[1-9][0-9]*$"}; key={"type":"string","minLength":1,"maxLength":191}; nullable_gid={"anyOf":[gid,{"type":"null"}]}; sha={"type":"string","pattern":"^(sha256:)?[0-9a-f]{64}$"}
    common=dict(owner="simulation",permissions=("simulation.use",),plugin_callable=True,tags=("simulation","alternate_hierarchy","experimental"))
    hierarchy={"type":"object","required":["hierarchy_gid","workspace_gid","name","source_bop_repository_gid","source_bop_version_gid","source_bop_fork_run_gid","source_bop_content_hash","projection_identity","status","sort_order","row_version"],"properties":{"hierarchy_gid":gid,"workspace_gid":gid,"name":{"type":"string"},"source_bop_repository_gid":nullable_gid,"source_bop_version_gid":nullable_gid,"source_bop_fork_run_gid":nullable_gid,"source_bop_content_hash":{"anyOf":[sha,{"type":"null"}]},"projection_identity":{"anyOf":[{"type":"string"},{"type":"null"}]},"status":{"type":"string"},"sort_order":{"type":"integer","minimum":0},"row_version":{"type":"integer","minimum":1}},"additionalProperties":False}
    create_output={"type":"object","required":["hierarchy_gid","workspace_gid","name","row_version"],"properties":{"hierarchy_gid":gid,"workspace_gid":gid,"name":{"type":"string"},"row_version":{"type":"integer","minimum":1}},"additionalProperties":False}
    placement_output={"type":"object","required":["placement_gid","hierarchy_gid","workspace_gid","row_version","hierarchy_row_version"],"properties":{"placement_gid":gid,"hierarchy_gid":gid,"workspace_gid":gid,"row_version":{"type":"integer","minimum":1},"hierarchy_row_version":{"type":"integer","minimum":2}},"additionalProperties":False}
    mutation_output={"type":"object","required":["workspace_gid","workspace_row_version","cache_revision_hash","operation"],"properties":{"hierarchy_gid":gid,"placement_gid":gid,"workspace_gid":gid,"row_version":{"type":"integer","minimum":2},"hierarchy_row_version":{"type":"integer","minimum":2},"workspace_row_version":{"type":"integer","minimum":2},"cache_revision_hash":{"type":"string","pattern":"^sha256:[0-9a-f]{64}$"},"operation":{"type":"string","enum":["update","archive","move","remove"]}},"additionalProperties":False}
    cas={"expected_row_version":{"type":"integer","minimum":1},"idempotency_key":key}
    return (
        (CapabilitySpec(id="simulation.environment.alternate_hierarchy.search",version=1,description="Search editable alternate hierarchies in one readable environment.",risk="read",confirmation="none",input_schema={"type":"object","required":["workspace_gid"],"properties":{"workspace_gid":gid},"additionalProperties":False},output_schema={"type":"object","required":["items"],"properties":{"items":{"type":"array","items":hierarchy}},"additionalProperties":False},**common),selected.search),
        (CapabilitySpec(id="simulation.environment.alternate_hierarchy.get",version=1,description="Read one alternate hierarchy and its placements.",risk="read",confirmation="none",input_schema={"type":"object","required":["hierarchy_gid"],"properties":{"hierarchy_gid":gid},"additionalProperties":False},output_schema={"type":"object","required":["hierarchy_gid","workspace_gid","name","status","projection_identity","row_version","placements"],"properties":{"hierarchy_gid":gid,"workspace_gid":gid,"name":{"type":"string"},"status":{"type":"string"},"projection_identity":{"anyOf":[{"type":"string"},{"type":"null"}]},"row_version":{"type":"integer","minimum":1},"placements":{"type":"array","items":{"type":"object"}}},"additionalProperties":False},**common),selected.get),
        (CapabilitySpec(id="simulation.environment.alternate_hierarchy.create",version=1,description="Create one empty editable alternate hierarchy; BOP-derived hierarchies must use the governed fork bootstrap capability.",risk="write",confirmation="none",idempotent=True,input_schema={"type":"object","required":["workspace_gid","name","expected_row_version","idempotency_key"],"properties":{"workspace_gid":gid,"name":{"type":"string","minLength":1,"maxLength":255},"expected_row_version":{"type":"integer","minimum":1},"idempotency_key":key},"additionalProperties":False},output_schema=create_output,**common),selected.create),
        (CapabilitySpec(id="simulation.environment.alternate_hierarchy.bootstrap_from_bop_fork",version=1,description="Repairably bootstrap one editable alternate hierarchy from an immutable governed Craft fork projection.",risk="write",confirmation="none",idempotent=True,input_schema={"type":"object","required":["workspace_gid","fork_run_gid","name","expected_row_version","idempotency_key"],"properties":{"workspace_gid":gid,"fork_run_gid":gid,"name":{"type":"string","minLength":1,"maxLength":255},"expected_row_version":{"type":"integer","minimum":1},"idempotency_key":key},"additionalProperties":False},output_schema={"type":"object","required":["hierarchy_gid","workspace_gid","name","row_version","workspace_row_version","status","node_count"],"properties":{"hierarchy_gid":gid,"workspace_gid":gid,"name":{"type":"string"},"row_version":{"type":"integer","minimum":1},"workspace_row_version":{"type":"integer","minimum":2},"status":{"const":"active"},"node_count":{"type":"integer","minimum":0}},"additionalProperties":False},**common),selected.bootstrap_from_bop_fork),
        (CapabilitySpec(id="simulation.environment.alternate_hierarchy.update",version=1,description="Rename one owned alternate hierarchy with optimistic concurrency.",risk="write",confirmation="none",idempotent=True,input_schema={"type":"object","required":["hierarchy_gid","name",*cas],"properties":{"hierarchy_gid":gid,"name":{"type":"string","minLength":1,"maxLength":255},**cas},"additionalProperties":False},output_schema=mutation_output,**common),selected.update),
        (CapabilitySpec(id="simulation.environment.alternate_hierarchy.archive",version=1,description="Archive one owned alternate hierarchy and retain its audit history.",risk="write",confirmation="user",idempotent=True,input_schema={"type":"object","required":["hierarchy_gid",*cas],"properties":{"hierarchy_gid":gid,**cas},"additionalProperties":False},output_schema=mutation_output,**common),selected.archive),
        (CapabilitySpec(id="simulation.environment.placement.create",version=1,description="Place a model-document occurrence or resource reference under one hierarchy node.",risk="write",confirmation="none",idempotent=True,input_schema={"type":"object","required":["hierarchy_gid","target_node_gid","source_kind","source_ref","transform","expected_row_version","idempotency_key"],"properties":{"hierarchy_gid":gid,"target_node_gid":gid,"parent_placement_gid":{"anyOf":[gid,{"type":"null"}]},"source_kind":{"type":"string","enum":["vm_occurrence","plmxml","jt","resource"]},"source_ref":{"type":"object","maxProperties":16,"additionalProperties":{"type":"string"}},"transform":{"type":"array","minItems":16,"maxItems":16,"items":{"type":"number"}},"display_name":{"type":"string","maxLength":255},"expected_row_version":{"type":"integer","minimum":1},"idempotency_key":key},"additionalProperties":False},output_schema=placement_output,**common),selected.create_placement),
        (CapabilitySpec(id="simulation.environment.placement.move",version=1,description="Move one placement without copying its source model.",risk="write",confirmation="none",idempotent=True,input_schema={"type":"object","required":["placement_gid",*cas],"properties":{"placement_gid":gid,"parent_placement_gid":nullable_gid,**cas},"additionalProperties":False},output_schema=mutation_output,**common),selected.move_placement),
        (CapabilitySpec(id="simulation.environment.placement.remove",version=1,description="Soft-remove one placement subtree from an alternate hierarchy.",risk="write",confirmation="user",idempotent=True,input_schema={"type":"object","required":["placement_gid",*cas],"properties":{"placement_gid":gid,**cas},"additionalProperties":False},output_schema=mutation_output,**common),selected.remove_placement),
    )


__all__ = ["AlternateHierarchyProvider", "specs"]
