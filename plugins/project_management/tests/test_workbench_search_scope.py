from __future__ import annotations

import pytest

from backend.capability_v2.provider_contracts import CapabilityContext
from plugins.project_management.project_management_backend.capabilities import reviewed
from plugins.project_management.project_management_backend.application.service import ProjectManagementApplication
from plugins.project_management.project_management_backend.infrastructure.repository import ProjectManagementRepository


@pytest.mark.parametrize("item_type,table,alias", [
    ("task", "workmanship_proj_tasks", "t"),
    ("issue", "workmanship_proj_issues", "i"),
])
def test_workbench_search_sql_requires_scoped_visibility_and_bounds_results(item_type, table, alias):
    captured = {}
    repository = ProjectManagementRepository.__new__(ProjectManagementRepository)
    repository.fetch_all = lambda sql, params: captured.update(sql=sql, params=params) or []

    repository.search_work_items(item_type, {"page_size": 200}, {"user_gid": "user-1"})

    sql = captured["sql"]
    assert f"FROM {table} {alias}" in sql
    assert f"{alias}.owner_user_gid=%s" in sql
    assert f"{alias}.share_scope='global'" in sql
    assert f"{alias}.share_scope='team'" not in sql
    assert f"{alias}.share_scope='project'" not in sql
    assert sql.endswith("LIMIT 200")
    assert captured["params"] == ("user-1",)

    repository.search_work_items(item_type, {"project_gid": "project-1", "page_size": 200}, {
        "user_gid": "user-1", "team_member_gids": ["user-1", "user-2"],
        "project_gids": ["project-1"],
    })

    sql = captured["sql"]
    assert f"{alias}.share_scope='team' AND {alias}.owner_user_gid IN (%s,%s)" in sql
    assert f"{alias}.share_scope='project' AND {alias}.project_gid IN (%s)" in sql
    assert f"{alias}.project_gid=%s" in sql
    assert captured["params"] == ("user-1", "user-1", "user-2", "project-1", "project-1")

    repository.search_work_items(item_type, {"q": "焊接", "page_size": 200}, {"user_gid": "user-1"})
    assert f"{alias}.title LIKE %s" in captured["sql"]
    assert captured["sql"].endswith("LIMIT 200")
    assert captured["params"] == ("user-1", "%焊接%")

    repository.search_work_items("task", {
        "list_gid": "list-1", "status": "pending", "q": "焊接", "page_size": 200,
    }, {"user_gid": "user-1"})
    assert "(t.owner_user_gid=%s OR t.share_scope='global')" in captured["sql"]
    assert "t.list_gid=%s" in captured["sql"]
    assert "t.status=%s" in captured["sql"]
    assert "t.title LIKE %s" in captured["sql"]
    assert captured["sql"].endswith("LIMIT 200")
    assert captured["params"] == ("user-1", "pending", "list-1", "%焊接%")


def test_task_list_navigation_sql_keeps_user_scope_when_filtering_task_lists():
    captured = {}
    repository = ProjectManagementRepository.__new__(ProjectManagementRepository)
    repository.fetch_all = lambda sql, params: captured.update(sql=sql, params=params) or []
    repository.search_lists({"item_type": "task", "q": "焊接"}, {"user_gid": "user-1"})
    sql = captured["sql"]
    assert "deleted_at IS NULL" in sql
    assert "(owner_type='user' AND owner_gid=%s)" in sql
    assert "visibility='public'" in sql
    assert "item_type=%s" in sql
    assert "name LIKE %s" in sql
    assert captured["params"] == ("user-1", "task", "%焊接%")


def test_atomic_project_search_replaces_client_scope_with_authenticated_scope(monkeypatch):
    captured = {}
    monkeypatch.setattr(reviewed, "build_access_scope", lambda user: {
        "user_gid": user["gid"], "team_gids": [user["team_id"]], "is_admin": False,
    })
    monkeypatch.setattr(reviewed.project_outcome_port, "invoke", lambda capability_id, payload, context:
        captured.update(capability_id=capability_id, payload=payload, context=context) or {"success": True, "data": []})
    context = CapabilityContext(user_gid="actor-1", team_gid="team-1")

    reviewed._atomic_handler("project.project.read", "projects.search")({
        "arguments": {"include_deleted": False, "include_archived": False,
                      "scope": {"user_gid": "forged-admin", "is_admin": True}},
    }, context)

    assert captured["capability_id"] == "project.project.read"
    assert captured["context"] is context
    assert captured["payload"]["arguments"]["scope"] == {
        "user_gid": "actor-1", "team_gids": ["team-1"], "is_admin": False,
    }
    assert captured["payload"]["arguments"]["include_deleted"] is False


def test_atomic_list_search_replaces_client_scope_with_authenticated_scope(monkeypatch):
    captured = {}
    monkeypatch.setattr(reviewed, "build_access_scope", lambda user: {
        "user_gid": user["gid"], "team_gids": [user["team_id"]], "is_admin": False,
    })
    monkeypatch.setattr(reviewed.project_outcome_port, "invoke", lambda capability_id, payload, context:
        captured.update(capability_id=capability_id, payload=payload) or {"success": True, "data": []})

    reviewed._atomic_handler("project.list.read", "lists.search")({
        "arguments": {"scope": {"user_gid": "forged-admin", "is_admin": True}},
    }, CapabilityContext(user_gid="actor-1", team_gid="team-1"))

    assert captured["capability_id"] == "project.list.read"
    assert captured["payload"]["arguments"]["scope"] == {
        "user_gid": "actor-1", "team_gids": ["team-1"], "is_admin": False,
    }


def test_project_search_sql_restricts_non_admin_visibility_and_excludes_inactive_rows():
    captured = {}
    repository = ProjectManagementRepository.__new__(ProjectManagementRepository)
    repository.fetch_all = lambda sql, params: captured.update(sql=sql, params=params) or []

    repository.search_projects({"include_deleted": False, "include_archived": False}, {
        "user_gid": "actor-1", "is_admin": False, "team_gids": ["team-1"],
        "project_gids": ["project-1"],
    })

    assert "p.owner_gid=%s" in captured["sql"]
    assert "p.share_scope='team' AND p.team_id IN (%s)" in captured["sql"]
    assert "p.share_scope IN ('team','project') AND p.gid IN (%s)" in captured["sql"]
    assert "p.is_deleted=FALSE" in captured["sql"]
    assert "p.is_archived=FALSE" in captured["sql"]
    assert captured["params"] == ("actor-1", "team-1", "project-1")


def test_atomic_follows_list_uses_authenticated_user_not_caller_identity():
    captured = {}
    repository = ProjectManagementRepository.__new__(ProjectManagementRepository)
    repository.list_follows = lambda user_gid, item_type: captured.update(user_gid=user_gid, item_type=item_type) or []
    application = ProjectManagementApplication(repository)
    context = CapabilityContext(user_gid="actor-1", team_gid="team-1")

    result = application.invoke("project.follow.read", {"operation": "follows.list", "arguments": {
        "item_type": None, "user_gid": "forged-user",
    }}, context)

    assert result == {"success": True, "data": []}
    assert captured == {"user_gid": "actor-1", "item_type": None}
