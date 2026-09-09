from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from plugins.agent.agent_backend.orchestration.bop_repository_assistant import (
    BopRepositoryAssistant, BopRepositoryAssistantError,
)


NOW = datetime(2026, 9, 9, tzinfo=UTC)


def context(*allowed):
    return SimpleNamespace(user_gid="10", team_gid="20", delegation=SimpleNamespace(
        expires_at=NOW + timedelta(minutes=5), allowed_capability_ids=allowed,
    ))


def tool(calls):
    return BopRepositoryAssistant(
        invoke=lambda cid, major, payload, ctx: calls.append((cid, major, payload, ctx)) or {"diff_gid": "90", "status": "ready", "tree": [1] * 10000},
        catalog_contains=lambda release, cid, major: release == "rel_dev" and major == 1,
        clock=lambda: NOW,
    )


def test_team_profile_never_advances_current_or_accepts_proposal():
    value = tool([])
    for task_kind in ("proposal_accept", "proposal_apply", "team_head_advance", "fork_apply"):
        with pytest.raises(BopRepositoryAssistantError, match="operation_not_allowed"):
            value.run({"profile": "craft_repository", "task_kind": task_kind}, context())


def test_routes_exact_catalog_version_and_returns_only_bounded_refs():
    calls = []
    result = tool(calls).run({"profile": "craft_repository", "task_kind": "repository_diff_start",
                              "catalog_release": "rel_dev", "payload": {"repository_gid": "1"}},
                             context("craft.bop.repository.diff.start"))
    assert calls[0][:3] == ("craft.bop.repository.diff.start", 1, {"repository_gid": "1"})
    assert result["outcome_refs"] == {"diff_gid": "90"}
    assert "tree" not in result


def test_rejects_unpinned_catalog_and_expired_or_missing_delegation():
    value = tool([])
    request = {"profile": "simulation_private_environment", "task_kind": "workspace_get",
               "catalog_release": "rel_wrong", "payload": {"workspace_gid": "1"}}
    with pytest.raises(BopRepositoryAssistantError, match="catalog_release_unavailable"):
        value.run(request, context("simulation.environment.workspace.get"))
    request["catalog_release"] = "rel_dev"
    with pytest.raises(BopRepositoryAssistantError, match="delegation_expired"):
        value.run(request, context())
