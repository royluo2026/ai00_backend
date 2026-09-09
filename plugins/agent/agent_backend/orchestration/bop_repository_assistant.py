"""Bounded Task Tool routing for BOP repository and private Simulation work."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable, Mapping


class BopRepositoryAssistantError(RuntimeError):
    pass


PROFILE_ROUTES = {
    "craft_repository": {
        "repository_diff_start": ("craft.bop.repository.diff.start", 1),
        "repository_diff_get": ("craft.bop.repository.diff.get", 1),
        "personal_sync_preview": ("craft.bop.managed_personal_space.sync.preview", 1),
        "proposal_create": ("craft.bop.change_proposal.create", 1),
        "proposal_submit": ("craft.bop.change_proposal.submit", 1),
        "proposal_get": ("craft.bop.change_proposal.get", 1),
        "fork_preview": ("craft.bop.repository.fork.preview", 1),
    },
    "simulation_private_environment": {
        "workspace_search": ("simulation.environment.workspace.search", 1),
        "workspace_get": ("simulation.environment.workspace.get", 1),
        "version_get": ("simulation.environment.workspace_version.get", 1),
        "export_preview": ("simulation.environment.workspace_version.export_for_import", 1),
    },
}


class BopRepositoryAssistant:
    """Invoke only a reviewed fixed route from one pinned development Catalog."""

    tool_id = "task.bop_repository_assistant"

    def __init__(self, *, invoke: Callable[..., Any], catalog_contains: Callable[[str, str, int], bool], clock=None):
        self.invoke = invoke
        self.catalog_contains = catalog_contains
        self.clock = clock or (lambda: datetime.now(UTC))

    def run(self, request: Mapping[str, Any], context) -> dict[str, Any]:
        profile, task_kind = str(request.get("profile") or ""), str(request.get("task_kind") or "")
        route = PROFILE_ROUTES.get(profile, {}).get(task_kind)
        if route is None:
            raise BopRepositoryAssistantError("operation_not_allowed")
        release = str(request.get("catalog_release") or "")
        if not release.startswith("rel_") or not self.catalog_contains(release, *route):
            raise BopRepositoryAssistantError("catalog_release_unavailable")
        delegation = getattr(context, "delegation", None)
        expires_at = getattr(delegation, "expires_at", None)
        allowed = set(getattr(delegation, "allowed_capability_ids", ()) or ())
        if delegation is None or expires_at is None or expires_at <= self.clock() or route[0] not in allowed:
            raise BopRepositoryAssistantError("delegation_expired")
        payload = request.get("payload")
        if not isinstance(payload, Mapping):
            raise BopRepositoryAssistantError("payload_invalid")
        result = self.invoke(route[0], route[1], dict(payload), context)
        if not isinstance(result, Mapping):
            raise BopRepositoryAssistantError("provider_result_invalid")
        ref_keys = ("operation_gid", "diff_gid", "proposal_gid", "preview_gid", "workspace_gid", "version_gid", "export_ref")
        refs = {key: result[key] for key in ref_keys if result.get(key) is not None}
        return {"profile": profile, "task_kind": task_kind, "capability_id": route[0],
                "major_version": route[1], "outcome_refs": refs,
                "summary": str(result.get("summary") or result.get("status") or "completed")[:500]}


__all__ = ["BopRepositoryAssistant", "BopRepositoryAssistantError", "PROFILE_ROUTES"]
