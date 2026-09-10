"""Governed manual VisMockup checkpoint capabilities."""
from __future__ import annotations

import hashlib
import json

from backend.capability_v2.provider_contracts import (
    CapabilityBusinessError, CapabilityOutput, CapabilityRisk, CapabilitySpec, EvidenceRef,
)
from backend.base.bop_edit_authorization import check_bop_edit

from ..data.vm_checkpoint_repository import VmCheckpointRepositoryError, repository
from ..data.workspace_repository import WorkspaceRepository


def _default_may_create_shared(workspace, context):
    if str(workspace["owner_gid"]) == str(context.user_gid) or "super_admin" in set(context.active_roles or ()):
        return True
    project_gid = workspace.get("primary_project_gid")
    if not project_gid:
        return False
    decision = check_bop_edit(tenant_gid=str(context.team_gid), user_gid=str(context.user_gid),
                              active_roles=tuple(context.active_roles or ()), project_gid=str(project_gid), line_gid=None)
    return decision.get("reason") == "project_manager"


def _evidence(data, digest=None):
    digest = digest or "sha256:" + hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
    return (EvidenceRef(kind="simulation.vm_checkpoint",
                        reference=f"simulation://vm-checkpoint/{data.get('checkpoint_gid', 'search')}", digest=digest),)


class VmCheckpointProvider:
    def __init__(self, checkpoint_repository=repository, workspace_repository=None, *, may_create_shared=None):
        self.repository = checkpoint_repository
        self.workspaces = workspace_repository or WorkspaceRepository()
        self.may_create_shared = may_create_shared or _default_may_create_shared

    @staticmethod
    def _scope(context):
        user_gid, tenant_gid = str(context.user_gid or ""), str(context.team_gid or "")
        if not user_gid or not tenant_gid:
            raise CapabilityBusinessError("workspace_identity_required", "workspace_identity_required")
        return user_gid, tenant_gid

    def _workspace(self, workspace_gid, context):
        user_gid, tenant_gid = self._scope(context)
        row = self.workspaces.get(str(workspace_gid or ""), tenant_gid=tenant_gid, owner_gid=user_gid)
        if not row:
            raise CapabilityBusinessError("workspace_not_found", "workspace_not_found")
        return row, user_gid, tenant_gid

    def create(self, payload, context):
        workspace, user_gid, tenant_gid = self._workspace(payload.get("workspace_gid"), context)
        scope = str(payload.get("scope") or "")
        if scope not in {"personal", "shared_baseline"}:
            raise CapabilityBusinessError("vm_checkpoint_scope_invalid", "vm_checkpoint_scope_invalid")
        if scope == "shared_baseline" and not self.may_create_shared(workspace, context):
            raise CapabilityBusinessError("vm_checkpoint_shared_forbidden", "vm_checkpoint_shared_forbidden")
        name, note = str(payload.get("name") or "").strip(), str(payload.get("note") or "").strip()
        if not name or len(name) > 255 or len(note) > 4000:
            raise CapabilityBusinessError("vm_checkpoint_description_invalid", "vm_checkpoint_description_invalid")
        try:
            data = self.repository.create_from_request(
                snapshot_request_id=str(payload.get("snapshot_request_id") or ""),
                snapshot_hash=str(payload.get("snapshot_hash") or ""), workspace_gid=str(workspace["workspace_gid"]),
                tenant_gid=tenant_gid, created_by=user_gid, scope=scope, name=name, note=note,
                idempotency_key=str(payload.get("idempotency_key") or ""),
            )
        except (VmCheckpointRepositoryError, RuntimeError) as exc:
            raise CapabilityBusinessError(str(exc), str(exc), retryable=str(exc) == "vm_snapshot_projection_required") from exc
        return CapabilityOutput(data=data, evidence=_evidence(data, str(payload["snapshot_hash"])))

    def search(self, payload, context):
        workspace, user_gid, tenant_gid = self._workspace(payload.get("workspace_gid"), context)
        page_size, cursor = payload.get("page_size", 50), payload.get("cursor")
        if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= 200:
            raise CapabilityBusinessError("page_size_invalid", "page_size_invalid")
        if cursor in (None, ""): offset = 0
        elif isinstance(cursor, str) and cursor.isdecimal(): offset = int(cursor)
        else: raise CapabilityBusinessError("cursor_invalid", "cursor_invalid")
        data = self.repository.search(workspace_gid=str(workspace["workspace_gid"]), tenant_gid=tenant_gid,
                                      created_by=user_gid, offset=offset, page_size=page_size,
                                      include_archived=bool(payload.get("include_archived", False)))
        return CapabilityOutput(data=data, evidence=_evidence(data))

    def archive(self, payload, context):
        workspace, user_gid, tenant_gid = self._workspace(payload.get("workspace_gid"), context)
        try:
            data = self.repository.archive(checkpoint_gid=str(payload.get("checkpoint_gid") or ""),
                workspace_gid=str(workspace["workspace_gid"]), tenant_gid=tenant_gid, created_by=user_gid,
                expected_row_version=payload.get("expected_row_version"),
                allow_shared=self.may_create_shared(workspace, context),
                idempotency_key=str(payload.get("idempotency_key") or ""))
        except (VmCheckpointRepositoryError, RuntimeError) as exc:
            raise CapabilityBusinessError(str(exc), str(exc), retryable="conflict" in str(exc)) from exc
        return CapabilityOutput(data=data, evidence=_evidence(data))


default_provider = VmCheckpointProvider()


def specs(provider=default_provider):
    common = dict(owner="simulation", version=1, permissions=("simulation.use",), plugin_callable=True,
                  tags=("simulation", "vm_versioning", "experimental"))
    return (
        (CapabilitySpec(id="simulation.vm_checkpoint.create", description="Create a governed personal checkpoint or authorized shared VM baseline from an exact completed snapshot.", risk=CapabilityRisk.WRITE, confirmation="user", **common), provider.create),
        (CapabilitySpec(id="simulation.vm_checkpoint.search", description="Search caller-visible personal and shared VM checkpoints.", risk=CapabilityRisk.READ, confirmation="none", **common), provider.search),
        (CapabilitySpec(id="simulation.vm_checkpoint.archive", description="Archive a governed VM checkpoint without deleting its evidence.", risk=CapabilityRisk.WRITE, confirmation="user", **common), provider.archive),
    )


__all__ = ["VmCheckpointProvider", "default_provider", "specs"]
