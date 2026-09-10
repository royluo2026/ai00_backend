"""Governed immutable VM difference reports."""
from __future__ import annotations

import hashlib
import json

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityOutput, CapabilityRisk, CapabilitySpec, EvidenceRef

from ..data.vm_diff_repository import VmDiffRepositoryError, repository
from ..domain.vm_diff import compare_vm_snapshots


def _evidence(data):
    digest = "sha256:" + hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
    return (EvidenceRef(kind="simulation.vm_diff_report", reference=f"simulation://vm-diff/{data.get('report_gid', 'items')}", digest=digest),)


class VmDiffProvider:
    def __init__(self, diff_repository=repository): self.repository = diff_repository

    @staticmethod
    def _scope(context):
        user, tenant = str(context.user_gid or ""), str(context.team_gid or "")
        if not user or not tenant: raise CapabilityBusinessError("workspace_identity_required", "workspace_identity_required")
        return user, tenant

    def generate(self, payload, context):
        user, tenant = self._scope(context)
        before = self.repository.load_checkpoint_snapshot(str(payload.get("before_checkpoint_gid") or ""), tenant_gid=tenant, created_by=user)
        after = self.repository.load_checkpoint_snapshot(str(payload.get("after_checkpoint_gid") or ""), tenant_gid=tenant, created_by=user)
        if not before or not after: raise CapabilityBusinessError("vm_checkpoint_not_found", "vm_checkpoint_not_found")
        if before["workspace_gid"] != after["workspace_gid"]: raise CapabilityBusinessError("vm_diff_workspace_mismatch", "vm_diff_workspace_mismatch")
        algorithm = str(payload.get("algorithm_version") or "vm-diff-v1")
        diff = compare_vm_snapshots(before["observations"], after["observations"], algorithm_version=algorithm)
        try:
            data = self.repository.persist_report(workspace_gid=before["workspace_gid"], tenant_gid=tenant, created_by=user,
                before_snapshot_gid=before["snapshot_gid"], after_snapshot_gid=after["snapshot_gid"],
                algorithm_version=algorithm, report_kind=str(payload.get("report_kind") or "manual"), diff=diff,
                idempotency_key=str(payload.get("idempotency_key") or ""))
        except (VmDiffRepositoryError, RuntimeError) as exc:
            raise CapabilityBusinessError(str(exc), str(exc)) from exc
        return CapabilityOutput(data=data, evidence=_evidence(data))

    def get(self, payload, context):
        user, tenant = self._scope(context)
        data = self.repository.get_report(str(payload.get("report_gid") or ""), tenant_gid=tenant, created_by=user)
        if not data: raise CapabilityBusinessError("vm_diff_report_not_found", "vm_diff_report_not_found")
        return CapabilityOutput(data=data, evidence=_evidence(data))

    def search_items(self, payload, context):
        user, tenant = self._scope(context); page_size = payload.get("page_size", 200); cursor = payload.get("cursor")
        if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= 200:
            raise CapabilityBusinessError("page_size_invalid", "page_size_invalid")
        if cursor in (None, ""): offset = 0
        elif isinstance(cursor, str) and cursor.isdecimal(): offset = int(cursor)
        else: raise CapabilityBusinessError("cursor_invalid", "cursor_invalid")
        try: data = self.repository.search_items(str(payload.get("report_gid") or ""), tenant_gid=tenant,
            created_by=user, offset=offset, page_size=page_size)
        except (VmDiffRepositoryError, RuntimeError) as exc: raise CapabilityBusinessError(str(exc), str(exc)) from exc
        return CapabilityOutput(data=data, evidence=_evidence(data))


default_provider = VmDiffProvider()


def specs(provider=default_provider):
    common = dict(owner="simulation", version=1, permissions=("simulation.use",), plugin_callable=True,
                  tags=("simulation", "vm_versioning", "experimental"))
    return (
        (CapabilitySpec(id="simulation.vm_diff_report.generate", description="Generate one immutable node-level difference report from two visible VM checkpoints.", risk=CapabilityRisk.WRITE, confirmation="user", **common), provider.generate),
        (CapabilitySpec(id="simulation.vm_diff_report.get", description="Read one caller-visible immutable VM difference report summary.", risk=CapabilityRisk.READ, confirmation="none", **common), provider.get),
        (CapabilitySpec(id="simulation.vm_diff_item.search", description="Page through atomic caller-visible VM difference items.", risk=CapabilityRisk.READ, confirmation="none", **common), provider.search_items),
    )


__all__ = ["VmDiffProvider", "default_provider", "specs"]
