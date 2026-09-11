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


_BOP_DEPTH = {"station": 1, "role": 2, "process": 3, "operation": 4}
_BOP_KIND_DEPTH = {"line": 0, "line_process": 0, "station": 1, "station_process": 1,
                   "role": 2, "operator_process": 2, "process": 3, "operation": 4}


def build_bop_projection_plan(execution: dict[str, Any], *, workspace_gid: str,
                              expected_workspace_version: int, line_gid: str | None,
                              fork_depth: str, hierarchy_name: str) -> dict[str, Any]:
    """Build a deterministic Simulation projection without copying Craft-owned refs as tree nodes."""
    if fork_depth not in {"all", *_BOP_DEPTH}:
        raise CapabilityBusinessError("fork_depth_invalid", "fork_depth_invalid")
    source = dict(execution.get("source") or {})
    content_hash = str(execution.get("content_hash") or "")
    if not content_hash.startswith("sha256:") or len(content_hash) != 71:
        raise CapabilityBusinessError("bop_projection_hash_invalid", "bop_projection_hash_invalid")
    raw_nodes = [dict(item) for item in execution.get("nodes") or []]
    by_gid = {str(item.get("node_id") or ""): item for item in raw_nodes}
    if not by_gid or "" in by_gid:
        raise CapabilityBusinessError("bop_projection_node_invalid", "bop_projection_node_invalid")
    scoped: set[str]
    selected_line = str(line_gid or "")
    if selected_line:
        selected = by_gid.get(selected_line)
        if not selected or _BOP_KIND_DEPTH.get(str(selected.get("kind") or "")) != 0:
            raise CapabilityBusinessError("bop_projection_line_not_found", "bop_projection_line_not_found")
        scoped, pending = {selected_line}, [selected_line]
        children: dict[str, list[str]] = {}
        for gid_value, item in by_gid.items():
            children.setdefault(str(item.get("parent_id") or ""), []).append(gid_value)
        while pending:
            parent = pending.pop()
            for child in children.get(parent, []):
                if child not in scoped:
                    scoped.add(child); pending.append(child)
    else:
        scoped = set(by_gid)
    limit = 99 if fork_depth == "all" else _BOP_DEPTH[fork_depth]
    included = {gid_value for gid_value in scoped
                if _BOP_KIND_DEPTH.get(str(by_gid[gid_value].get("kind") or ""), limit + 1) <= limit}
    nodes = []
    for gid_value in sorted(included, key=lambda value: (int(by_gid[value].get("sequence") or 0), value)):
        item = by_gid[gid_value]
        parent = str(item.get("parent_id") or "")
        nodes.append({"source_gid": gid_value, "parent_source_gid": parent if parent in included else None,
                      "node_type": str(item.get("kind") or "unknown"),
                      "name": str(item.get("name") or gid_value)[:255],
                      "position": int(item.get("sequence") or 0)})
    scoped_rows = [by_gid[value] for value in scoped]
    model_references = sorted(({"source_node_gid": str(item["node_id"]), "reference": str(ref)}
        for item in scoped_rows for ref in (item.get("part_refs") or [])),
        key=lambda value: (value["source_node_gid"], value["reference"]))
    resource_references = sorted(({"source_node_gid": str(item["node_id"]),
        "resource_type": key.removesuffix("_refs"), "reference": str(ref)}
        for item in scoped_rows for key in ("tool_refs", "fixture_refs", "equipment_refs")
        for ref in (item.get(key) or [])),
        key=lambda value: (value["source_node_gid"], value["resource_type"], value["reference"]))
    plan = {"workspace_gid": str(workspace_gid), "expected_workspace_version": int(expected_workspace_version),
            "source_project_gid": str(source.get("project_gid") or ""),
            "source_version_gid": str(source.get("bop_version_gid") or ""),
            "source_revision": int(source.get("revision") or 0), "source_content_hash": content_hash,
            "line_gid": selected_line or None, "fork_depth": fork_depth,
            "hierarchy_name": str(hierarchy_name or "").strip(), "nodes": nodes,
            "node_count": len(nodes), "model_references": model_references,
            "resource_references": resource_references,
            "model_reference_count": len(model_references),
            "resource_reference_count": len(resource_references), "conflicts": []}
    if not plan["hierarchy_name"]:
        raise CapabilityBusinessError("hierarchy_name_invalid", "hierarchy_name_invalid")
    canonical = json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    plan["plan_hash"] = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return plan


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

    async def create_placement(self, payload, context):
        tenant_gid, actor_gid = _scope(context); hierarchy_gid = str(payload.get("hierarchy_gid") or "")
        source_kind = str(payload.get("source_kind") or "")
        source_ref = dict(payload.get("source_ref") or {})
        if source_kind == "resource":
            client = getattr(context, "domain_client", None)
            identity = getattr(context, "effective_identity", None)
            if client is None or identity is None:
                raise CapabilityBusinessError("domain_client_unavailable", "domain_client_unavailable")
            request_id = str(context.request_id or payload.get("idempotency_key") or "resource-placement")
            projection = await client.invoke(
                DomainInvocation(capability_id="craft.resource_requirement.get", major_version=1,
                                 payload={"gid": str(source_ref.get("resource_gid") or "")}),
                identity, CorrelationRef(request_id=request_id, trace_id=request_id),
            )
            if not projection.ok:
                code = projection.error.code if projection.error else "resource_projection_failed"
                raise CapabilityBusinessError(code, code, retryable=True)
            resource = dict(projection.data or {})
            if str(resource.get("status") or "") != "active":
                raise CapabilityBusinessError("resource_not_active", "resource_not_active")
            source_ref = {
                "resource_gid": str(resource.get("gid") or ""),
                "resource_type": str(resource.get("resource_type") or ""),
                "resource_code": str(resource.get("code") or ""),
                "resource_name": str(resource.get("name") or ""),
                "resource_version": str(resource.get("resource_version") or ""),
            }
            source_ref["source_projection_hash"] = "sha256:" + hashlib.sha256(json.dumps(
                source_ref, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            ).encode("utf-8")).hexdigest()
        try: data = self.repository.add_placement(hierarchy_gid=hierarchy_gid, target_node_gid=str(payload.get("target_node_gid") or ""), parent_placement_gid=payload.get("parent_placement_gid"), source_kind=source_kind, source_ref=source_ref, transform=payload.get("transform") or [], expected_hierarchy_version=payload.get("expected_row_version"), actor_gid=actor_gid, tenant_gid=tenant_gid, display_name=str(payload.get("display_name") or ""), idempotency_key=str(payload.get("idempotency_key") or ""))
        except WorkspaceRepositoryError as exc: raise CapabilityBusinessError(str(exc), str(exc), retryable=str(exc) == "version_conflict") from exc
        return _output(data, "placement_created", hierarchy_gid)

    def _mutate_placement(self,operation,payload,context):
        tenant_gid,actor_gid=_scope(context);placement_gid=str(payload.get("placement_gid") or "")
        try:data=self.repository.mutate_placement(placement_gid=placement_gid,expected_hierarchy_version=payload.get("expected_row_version"),operation=operation,values={"parent_placement_gid":payload.get("parent_placement_gid")} if operation=="move" else {},actor_gid=actor_gid,tenant_gid=tenant_gid,idempotency_key=str(payload.get("idempotency_key") or ""))
        except WorkspaceRepositoryError as exc:raise CapabilityBusinessError(str(exc),str(exc),retryable=str(exc)=="version_conflict") from exc
        return _output(data,f"placement_{operation}d",placement_gid)

    def move_placement(self,payload,context):return self._mutate_placement("move",payload,context)
    def remove_placement(self,payload,context):return self._mutate_placement("remove",payload,context)

    async def _bop_plan(self, payload, context):
        tenant_gid, actor_gid = _scope(context)
        client, identity = getattr(context, "domain_client", None), getattr(context, "effective_identity", None)
        if client is None or identity is None:
            raise CapabilityBusinessError("domain_client_unavailable", "domain_client_unavailable")
        workspace_gid = str(payload.get("workspace_gid") or "")
        workspace = self.repository.get(workspace_gid, tenant_gid=tenant_gid, owner_gid=actor_gid)
        if not workspace or not workspace.get("is_owner"):
            raise CapabilityBusinessError("workspace_not_found", "workspace_not_found")
        if int(workspace.get("row_version") or 0) != int(payload.get("expected_row_version") or 0):
            raise CapabilityBusinessError("version_conflict", "version_conflict", retryable=True)
        request_id = str(context.request_id or "bop-projection")
        outcome = await client.invoke(DomainInvocation(
            capability_id="craft.bop.execution_structure.get", major_version=1,
            payload={"version_gid": str(payload.get("version_gid") or "")}),
            identity, CorrelationRef(request_id=request_id, trace_id=request_id))
        if not outcome.ok:
            code = outcome.error.code if outcome.error else "bop_execution_structure_failed"
            raise CapabilityBusinessError(code, code, retryable=True)
        return build_bop_projection_plan(dict(outcome.data or {}), workspace_gid=workspace_gid,
            expected_workspace_version=int(payload.get("expected_row_version") or 0),
            line_gid=payload.get("line_gid"), fork_depth=str(payload.get("fork_depth") or ""),
            hierarchy_name=str(payload.get("hierarchy_name") or ""))

    async def preview_bop_projection(self, payload, context):
        plan = await self._bop_plan(payload, context)
        return _output(plan, "bop_projection_previewed", str(plan["source_version_gid"]))

    async def apply_bop_projection(self, payload, context):
        tenant_gid, actor_gid = _scope(context)
        plan = await self._bop_plan(payload, context)
        if str(payload.get("plan_hash") or "") != plan["plan_hash"]:
            raise CapabilityBusinessError("bop_projection_plan_changed", "bop_projection_plan_changed", retryable=True)
        try:
            data = self.repository.insert_bop_projection(workspace_gid=plan["workspace_gid"], plan=plan,
                expected_workspace_version=plan["expected_workspace_version"], actor_gid=actor_gid,
                tenant_gid=tenant_gid, idempotency_key=str(payload.get("idempotency_key") or ""))
        except WorkspaceRepositoryError as exc:
            raise CapabilityBusinessError(str(exc), str(exc), retryable=str(exc) == "version_conflict") from exc
        return _output(data, "bop_projection_applied", str(data["hierarchy_gid"]))


def specs(provider: AlternateHierarchyProvider | None = None):
    selected = provider or AlternateHierarchyProvider(); gid={"type":"string","pattern":"^[1-9][0-9]*$"}; key={"type":"string","minLength":1,"maxLength":191}; nullable_gid={"anyOf":[gid,{"type":"null"}]}; sha={"type":"string","pattern":"^(sha256:)?[0-9a-f]{64}$"}
    common=dict(owner="simulation",permissions=("simulation.use",),plugin_callable=True,tags=("simulation","alternate_hierarchy","experimental"))
    hierarchy={"type":"object","required":["hierarchy_gid","workspace_gid","name","source_bop_repository_gid","source_bop_version_gid","source_bop_fork_run_gid","source_bop_content_hash","projection_identity","status","sort_order","row_version"],"properties":{"hierarchy_gid":gid,"workspace_gid":gid,"name":{"type":"string"},"source_bop_repository_gid":nullable_gid,"source_bop_version_gid":nullable_gid,"source_bop_fork_run_gid":nullable_gid,"source_bop_content_hash":{"anyOf":[sha,{"type":"null"}]},"projection_identity":{"anyOf":[{"type":"string"},{"type":"null"}]},"status":{"type":"string"},"sort_order":{"type":"integer","minimum":0},"row_version":{"type":"integer","minimum":1}},"additionalProperties":False}
    create_output={"type":"object","required":["hierarchy_gid","root_node_gid","workspace_gid","name","row_version"],"properties":{"hierarchy_gid":gid,"root_node_gid":gid,"workspace_gid":gid,"name":{"type":"string"},"row_version":{"type":"integer","minimum":1}},"additionalProperties":False}
    placement_output={"type":"object","required":["placement_gid","hierarchy_gid","workspace_gid","row_version","hierarchy_row_version"],"properties":{"placement_gid":gid,"hierarchy_gid":gid,"workspace_gid":gid,"row_version":{"type":"integer","minimum":1},"hierarchy_row_version":{"type":"integer","minimum":2}},"additionalProperties":False}
    mutation_output={"type":"object","required":["workspace_gid","workspace_row_version","cache_revision_hash","operation"],"properties":{"hierarchy_gid":gid,"placement_gid":gid,"workspace_gid":gid,"row_version":{"type":"integer","minimum":2},"hierarchy_row_version":{"type":"integer","minimum":2},"workspace_row_version":{"type":"integer","minimum":2},"cache_revision_hash":{"type":"string","pattern":"^sha256:[0-9a-f]{64}$"},"operation":{"type":"string","enum":["update","archive","move","remove"]}},"additionalProperties":False}
    cas={"expected_row_version":{"type":"integer","minimum":1},"idempotency_key":key}
    bop_preview_input={"type":"object","required":["workspace_gid","version_gid","line_gid","fork_depth","hierarchy_name","expected_row_version"],"properties":{"workspace_gid":gid,"version_gid":gid,"line_gid":{"anyOf":[gid,{"type":"null"}]},"fork_depth":{"type":"string","enum":["all","operation","process","role","station"]},"hierarchy_name":{"type":"string","minLength":1,"maxLength":255},"expected_row_version":{"type":"integer","minimum":1}},"additionalProperties":False}
    bop_node={"type":"object","required":["source_gid","parent_source_gid","node_type","name","position"],"properties":{"source_gid":gid,"parent_source_gid":{"anyOf":[gid,{"type":"null"}]},"node_type":{"type":"string","minLength":1,"maxLength":32},"name":{"type":"string","minLength":1,"maxLength":255},"position":{"type":"integer","minimum":0}},"additionalProperties":False}
    model_ref={"type":"object","required":["source_node_gid","reference"],"properties":{"source_node_gid":gid,"reference":{"type":"string","minLength":1,"maxLength":255}},"additionalProperties":False}
    resource_ref={"type":"object","required":["source_node_gid","resource_type","reference"],"properties":{"source_node_gid":gid,"resource_type":{"type":"string","enum":["tool","fixture","equipment"]},"reference":{"type":"string","minLength":1,"maxLength":255}},"additionalProperties":False}
    bop_plan_output={"type":"object","required":["workspace_gid","expected_workspace_version","source_project_gid","source_version_gid","source_revision","source_content_hash","line_gid","fork_depth","hierarchy_name","nodes","node_count","model_references","resource_references","model_reference_count","resource_reference_count","conflicts","plan_hash"],"properties":{"workspace_gid":gid,"expected_workspace_version":{"type":"integer","minimum":1},"source_project_gid":gid,"source_version_gid":gid,"source_revision":{"type":"integer","minimum":1},"source_content_hash":sha,"line_gid":{"anyOf":[gid,{"type":"null"}]},"fork_depth":{"type":"string","enum":["all","operation","process","role","station"]},"hierarchy_name":{"type":"string"},"nodes":{"type":"array","maxItems":10000,"items":bop_node},"node_count":{"type":"integer","minimum":0},"model_references":{"type":"array","maxItems":10000,"items":model_ref},"resource_references":{"type":"array","maxItems":10000,"items":resource_ref},"model_reference_count":{"type":"integer","minimum":0},"resource_reference_count":{"type":"integer","minimum":0},"conflicts":{"type":"array","maxItems":1000,"items":{"type":"object","required":["code"],"properties":{"code":{"type":"string"},"detail":{"type":"string"}},"additionalProperties":False}},"plan_hash":sha},"additionalProperties":False}
    bop_apply_output={"type":"object","required":["hierarchy_gid","workspace_gid","name","row_version","workspace_row_version","status","node_count"],"properties":{"hierarchy_gid":gid,"workspace_gid":gid,"name":{"type":"string"},"row_version":{"type":"integer","minimum":1},"workspace_row_version":{"type":"integer","minimum":2},"status":{"const":"active"},"node_count":{"type":"integer","minimum":0}},"additionalProperties":False}
    return (
        (CapabilitySpec(id="simulation.environment.alternate_hierarchy.search",version=1,description="Search editable alternate hierarchies in one readable environment.",risk="read",confirmation="none",input_schema={"type":"object","required":["workspace_gid"],"properties":{"workspace_gid":gid},"additionalProperties":False},output_schema={"type":"object","required":["items"],"properties":{"items":{"type":"array","items":hierarchy}},"additionalProperties":False},**common),selected.search),
        (CapabilitySpec(id="simulation.environment.alternate_hierarchy.get",version=1,description="Read one alternate hierarchy, its editable node tree, separated source references, and placements.",risk="read",confirmation="none",input_schema={"type":"object","required":["hierarchy_gid"],"properties":{"hierarchy_gid":gid},"additionalProperties":False},output_schema={"type":"object","required":["hierarchy_gid","workspace_gid","name","status","projection_identity","row_version","source_refs","nodes","placements"],"properties":{"hierarchy_gid":gid,"workspace_gid":gid,"name":{"type":"string"},"status":{"type":"string"},"projection_identity":{"anyOf":[{"type":"string"},{"type":"null"}]},"row_version":{"type":"integer","minimum":1},"source_refs":{"type":"object","required":["model_references","resource_references"],"properties":{"model_references":{"type":"array","items":{"type":"object"}},"resource_references":{"type":"array","items":{"type":"object"}}},"additionalProperties":False},"nodes":{"type":"array","items":{"type":"object","required":["node_gid","workspace_gid","hierarchy_gid","parent_gid","node_type","name","sort_order","source_bop_node_gid","row_version"],"properties":{"node_gid":gid,"workspace_gid":gid,"hierarchy_gid":gid,"parent_gid":{"anyOf":[gid,{"type":"null"}]},"node_type":{"type":"string"},"name":{"type":"string"},"sort_order":{"type":"integer"},"source_bop_node_gid":{"anyOf":[gid,{"type":"null"}]},"row_version":{"type":"integer","minimum":1}},"additionalProperties":False}},"placements":{"type":"array","items":{"type":"object"}}},"additionalProperties":False},**common),selected.get),
        (CapabilitySpec(id="simulation.environment.alternate_hierarchy.create",version=1,description="Create one editable alternate hierarchy with an atomic root node; BOP-derived hierarchies must use the governed fork bootstrap capability.",risk="write",confirmation="none",idempotent=True,input_schema={"type":"object","required":["workspace_gid","name","expected_row_version","idempotency_key"],"properties":{"workspace_gid":gid,"name":{"type":"string","minLength":1,"maxLength":255},"expected_row_version":{"type":"integer","minimum":1},"idempotency_key":key},"additionalProperties":False},output_schema=create_output,**common),selected.create),
        (CapabilitySpec(id="simulation.environment.alternate_hierarchy.bootstrap_from_bop_fork",version=1,description="Repairably bootstrap one editable alternate hierarchy from an immutable governed Craft fork projection.",risk="write",confirmation="none",idempotent=True,input_schema={"type":"object","required":["workspace_gid","fork_run_gid","name","expected_row_version","idempotency_key"],"properties":{"workspace_gid":gid,"fork_run_gid":gid,"name":{"type":"string","minLength":1,"maxLength":255},"expected_row_version":{"type":"integer","minimum":1},"idempotency_key":key},"additionalProperties":False},output_schema={"type":"object","required":["hierarchy_gid","workspace_gid","name","row_version","workspace_row_version","status","node_count"],"properties":{"hierarchy_gid":gid,"workspace_gid":gid,"name":{"type":"string"},"row_version":{"type":"integer","minimum":1},"workspace_row_version":{"type":"integer","minimum":2},"status":{"const":"active"},"node_count":{"type":"integer","minimum":0}},"additionalProperties":False},**common),selected.bootstrap_from_bop_fork),
        (CapabilitySpec(id="simulation.environment.alternate_hierarchy.update",version=1,description="Rename one owned alternate hierarchy with optimistic concurrency.",risk="write",confirmation="none",idempotent=True,input_schema={"type":"object","required":["hierarchy_gid","name",*cas],"properties":{"hierarchy_gid":gid,"name":{"type":"string","minLength":1,"maxLength":255},**cas},"additionalProperties":False},output_schema=mutation_output,**common),selected.update),
        (CapabilitySpec(id="simulation.environment.alternate_hierarchy.archive",version=1,description="Archive one owned alternate hierarchy and retain its audit history.",risk="write",confirmation="user",idempotent=True,input_schema={"type":"object","required":["hierarchy_gid",*cas],"properties":{"hierarchy_gid":gid,**cas},"additionalProperties":False},output_schema=mutation_output,**common),selected.archive),
        (CapabilitySpec(id="simulation.environment.placement.create",version=1,description="Place a model-document occurrence or resource reference under one hierarchy node.",risk="write",confirmation="none",idempotent=True,input_schema={"type":"object","required":["hierarchy_gid","target_node_gid","source_kind","source_ref","transform","expected_row_version","idempotency_key"],"properties":{"hierarchy_gid":gid,"target_node_gid":gid,"parent_placement_gid":{"anyOf":[gid,{"type":"null"}]},"source_kind":{"type":"string","enum":["vm_occurrence","plmxml","jt","resource"]},"source_ref":{"type":"object","maxProperties":16,"additionalProperties":{"type":"string"}},"transform":{"type":"array","minItems":16,"maxItems":16,"items":{"type":"number"}},"display_name":{"type":"string","maxLength":255},"expected_row_version":{"type":"integer","minimum":1},"idempotency_key":key},"additionalProperties":False},output_schema=placement_output,**common),selected.create_placement),
        (CapabilitySpec(id="simulation.environment.placement.move",version=1,description="Move one placement without copying its source model.",risk="write",confirmation="none",idempotent=True,input_schema={"type":"object","required":["placement_gid",*cas],"properties":{"placement_gid":gid,"parent_placement_gid":nullable_gid,**cas},"additionalProperties":False},output_schema=mutation_output,**common),selected.move_placement),
        (CapabilitySpec(id="simulation.environment.placement.remove",version=1,description="Soft-remove one placement subtree from an alternate hierarchy.",risk="write",confirmation="user",idempotent=True,input_schema={"type":"object","required":["placement_gid",*cas],"properties":{"placement_gid":gid,**cas},"additionalProperties":False},output_schema=mutation_output,**common),selected.remove_placement),
        (CapabilitySpec(id="simulation.environment.bop_projection.preview",version=1,description="Preview a deterministic BOP skeleton projection from the exact published Craft execution structure without copying product or resource references as hierarchy nodes.",risk="read",confirmation="none",input_schema=bop_preview_input,output_schema=bop_plan_output,**common),selected.preview_bop_projection),
        (CapabilitySpec(id="simulation.environment.bop_projection.apply",version=1,description="Atomically insert the exact previewed BOP process skeleton as one alternate hierarchy after revalidating the Craft source and plan hash.",risk="write",confirmation="user",idempotent=True,input_schema={"type":"object","required":[*bop_preview_input["required"],"plan_hash","idempotency_key"],"properties":{**bop_preview_input["properties"],"plan_hash":sha,"idempotency_key":key},"additionalProperties":False},output_schema=bop_apply_output,**common),selected.apply_bop_projection),
    )


__all__ = ["AlternateHierarchyProvider", "build_bop_projection_plan", "specs"]
