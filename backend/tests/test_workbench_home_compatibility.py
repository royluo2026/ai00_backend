from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.capability_v2.gateway import get_default_gateway
from backend.capability_v2.identity import AuthenticatedPrincipal
from backend.platform_sdk.auth import get_authenticated_principal, get_current_user
import backend.routers.workbench_home as workbench_home


class RecordingGateway:
    catalog_release = "rel_workbench_test"

    def __init__(self, fail_ids=(), failure_code="provider_unavailable"):
        self.envelopes = []
        self.fail_ids = set(fail_ids)
        self.failure_code = failure_code

    async def invoke(self, envelope):
        self.envelopes.append(envelope)
        if envelope.capability_id in self.fail_ids:
            code = self.failure_code
            return SimpleNamespace(ok=False, data=None, error=SimpleNamespace(code=code, model_dump=lambda **_: {"code": code}))
        responses = {
            "project.project.read.atomic.projects_search": {
                "success": True,
                "data": [{"gid": "project-1", "name": "Alpha"}],
            },
            "project.follow.read.atomic.follows_list": {
                "success": True,
                "data": [
                    {
                        "gid": "follow-1",
                        "item_type": "task",
                        "item_gid": "task-1",
                        "item_title": "Prepare BOP",
                        "notify_on": ["status_change"],
                        "created_at": "2026-08-14T00:00:00+00:00",
                    }
                ],
            },
            "project.task.read.atomic.tasks_search": {
                "success": True,
                "data": [
                    {
                        "item_type": "task",
                        "gid": "task-1",
                        "title": "Prepare BOP",
                        "status": "pending",
                        "list_gid": "task-list-1",
                    }
                ],
            },
            "project.issue.read.atomic.issues_search": {
                "success": True,
                "data": [
                    {
                        "item_type": "issue",
                        "gid": "issue-1",
                        "title": "Resolve clash",
                        "status": "open",
                        "list_gid": "issue-list-1",
                    }
                ],
            },
        }
        return SimpleNamespace(
            ok=True,
            data={"data": responses[envelope.capability_id]},
            error=None,
        )


def _client(monkeypatch):
    application = FastAPI()
    application.include_router(workbench_home.router)
    gateway = RecordingGateway()
    principal = AuthenticatedPrincipal(
        user_id="user-1",
        authentication_method="jwt",
        authenticated_at=datetime(2026, 8, 14, tzinfo=UTC),
    )
    user = {
        "gid": "user-1",
        "team_id": "team-1",
        "org_role": "member",
    }
    scope = {
        "user_gid": "user-1",
        "team_gids": ["team-1"],
        "team_member_gids": ["user-1"],
        "project_gids": ["project-1"],
        "is_admin": False,
    }
    monkeypatch.setattr(
        workbench_home, "build_access_scope", lambda value: scope, raising=False
    )
    application.dependency_overrides[get_current_user] = lambda: user
    application.dependency_overrides[get_authenticated_principal] = lambda: principal
    application.dependency_overrides[get_default_gateway] = lambda: gateway
    return application, gateway, scope


def test_home_composes_projects_and_follows_through_capability_gateway(monkeypatch):
    application, gateway, scope = _client(monkeypatch)

    with TestClient(application) as client:
        response = client.get(
            "/api/workbench/home",
            headers={"X-Request-ID": "request-home-1"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "today_items": [],
        "my_contexts": [
            {
                "project_gid": "project-1",
                "project_name": "Alpha",
                "role": "member",
                "section_gid": None,
            }
        ],
        "alerts": [],
        "recent_follows": [
            {
                "gid": "follow-1",
                "item_type": "task",
                "item_gid": "task-1",
                "item_title": "Prepare BOP",
                "notify_on": ["status_change"],
                "created_at": "2026-08-14T00:00:00+00:00",
            }
        ],
    }
    assert [item.capability_id for item in gateway.envelopes] == [
        "project.project.read.atomic.projects_search",
        "project.follow.read.atomic.follows_list",
    ]
    assert gateway.envelopes[0].payload == {
        "arguments": {
            "include_deleted": False,
            "include_archived": False,
            "scope": scope,
        },
    }
    assert gateway.envelopes[1].payload == {"arguments": {"item_type": None}}


def test_panel1_composes_task_and_issue_sources_through_capability_gateway(monkeypatch):
    application, gateway, scope = _client(monkeypatch)

    with TestClient(application) as client:
        response = client.get(
            "/api/workbench/panel1",
            params={
                "sources": "task,issue",
                "task_lists": "task-list-1",
                "issue_lists": "issue-list-1",
            },
            headers={"X-Request-ID": "request-panel-1"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "item_type": "task",
                "gid": "task-1",
                "title": "Prepare BOP",
                "status": "pending",
                "list_gid": "task-list-1",
            },
            {
                "item_type": "issue",
                "gid": "issue-1",
                "title": "Resolve clash",
                "status": "open",
                "list_gid": "issue-list-1",
            },
        ],
        "total": 2,
    }
    assert [item.capability_id for item in gateway.envelopes] == [
        "project.task.read.atomic.tasks_search",
        "project.issue.read.atomic.issues_search",
    ]
    assert gateway.envelopes[0].payload == {
        "arguments": {
            "project_gid": None,
            "status": None,
            "list_gid": "task-list-1",
            "scheduled_date_from": None,
            "q": None,
            "page_size": 200,
            "scope": scope,
        },
    }
    assert gateway.envelopes[1].payload == {
        "arguments": {
            "project_gid": None,
            "status": None,
            "list_gid": "issue-list-1",
            "q": None,
            "page_size": 200,
            "scope": scope,
        },
    }


def test_bff_transport_failure_fails_closed_with_constituent_audit_detail(monkeypatch):
    application, gateway, _scope = _client(monkeypatch)
    gateway.fail_ids.add("project.project.read.atomic.projects_search")

    with TestClient(application) as client:
        response = client.get("/api/workbench/home")

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "provider_unavailable",
        "constituent_capability_id": "project.project.read.atomic.projects_search",
    }
    assert [item.capability_id for item in gateway.envelopes] == [
        "project.project.read.atomic.projects_search",
    ]


def test_bff_contract_failure_is_not_silently_omitted(monkeypatch):
    application, gateway, _scope = _client(monkeypatch)
    gateway.fail_ids.add("project.project.read.atomic.projects_search")
    gateway.failure_code = "output_contract_invalid"

    with TestClient(application) as client:
        response = client.get("/api/workbench/home")

    assert response.status_code == 502
    assert response.json()["detail"] == {
        "code": "output_contract_invalid",
        "constituent_capability_id": "project.project.read.atomic.projects_search",
    }


def test_bff_authorization_failure_is_explicit_and_auditable(monkeypatch):
    application, gateway, _scope = _client(monkeypatch)
    gateway.fail_ids.add("project.project.read.atomic.projects_search")
    gateway.failure_code = "permission_denied"

    with TestClient(application) as client:
        response = client.get("/api/workbench/home")

    assert response.status_code == 403
    assert response.json()["detail"] == {
        "code": "permission_denied",
        "constituent_capability_id": "project.project.read.atomic.projects_search",
    }
