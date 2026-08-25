from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.capability_v2.identity import AuthenticatedPrincipal
from backend.capability_v2.gateway import get_default_gateway
from backend.capability_v2.gateway import CapabilityGatewayService
from backend.platform_sdk.auth import get_authenticated_principal, get_current_user
from plugins.craft.craft_backend.routers.change_logs import router as change_logs_router
import plugins.craft.craft_backend.routers.collab as collab_router_module
import plugins.craft.craft_backend.routers.share_links as share_links_router_module
from plugins.craft.craft_backend.routers.item_entries import router as item_entries_router
from plugins.project_management.project_management_backend.api.compatibility import (
    build_web_compatibility_envelope,
)
from plugins.project_management.project_management_backend.application.service import SUPPORTED_OPERATIONS


class GatewayRelease:
    catalog_release = "rel_project_test"


class RecordingGateway(GatewayRelease):
    def __init__(self):
        self.envelopes = []

    async def invoke(self, envelope):
        self.envelopes.append(envelope)
        operation = envelope.payload.get("operation")
        if operation is None and ".atomic." in envelope.capability_id:
            suffix = envelope.capability_id.split(".atomic.", 1)[1]
            operation = next(
                (candidate for operations in SUPPORTED_OPERATIONS.values() for candidate in operations
                 if candidate.replace(".", "_") == suffix),
                suffix,
            )
        arguments = envelope.payload.get("arguments", envelope.payload)
        if operation == "item_entries.replace":
            data = {
                "success": True,
                "count": len(arguments["entries"]),
                "entries": arguments["entries"],
            }
        elif operation == "item_entries.delete":
            data = {"success": True}
        elif operation == "change_logs.search":
            data = [
                {
                    "gid": "change-1",
                    "item_type": "task",
                    "item_gid": "task-1",
                    "list_gid": "list-1",
                    "changed_by": "user-1",
                }
            ]
        elif operation == "collaboration.sessions.list":
            data = {"success": True, "data": []}
        elif operation == "collaboration.sessions.create":
            data = {"success": True, "data": {"gid": "session-2"}}
        elif operation in {"collaboration.sessions.join", "collaboration.sessions.end"}:
            data = {"success": True}
        elif operation == "share_links.resolve":
            data = {"target_type": "list", "target_gid": "list-1", "item_type": None, "display_name": "Plan", "current_permission": "read", "can_request": False}
        else:
            data = {"entries": []}
        return SimpleNamespace(
            ok=True,
            data={"data": data},
            error=None,
        )


def _envelope_operation(envelope):
    if envelope.payload.get("operation"):
        return envelope.payload["operation"]
    suffix = envelope.capability_id.split(".atomic.", 1)[1]
    return next(
        (candidate for operations in SUPPORTED_OPERATIONS.values() for candidate in operations
         if candidate.replace(".", "_") == suffix),
        suffix,
    )


def test_legacy_web_adapter_builds_a_server_derived_gateway_envelope():
    principal = AuthenticatedPrincipal(
        user_id="user-1",
        authentication_method="jwt",
        authenticated_at=datetime(2026, 8, 12, tzinfo=UTC),
    )

    envelope = build_web_compatibility_envelope(
        GatewayRelease(),
        capability_id="project.list.read",
        payload={
            "operation": "item_entries.get",
            "arguments": {"item_type": "task", "item_gid": "task-1"},
        },
        current_user={
            "gid": "user-1",
            "team_id": "team-1",
            "org_role": "member",
        },
        principal=principal,
        request_id="request-1",
        trace_id="trace-1",
    )

    assert envelope.capability_id == "project.list.read.atomic.item_entries_get"
    assert envelope.catalog_release == "rel_project_test"
    assert envelope.identity.actor.user_id == "user-1"
    assert envelope.identity.tenant.tenant_id == "team-1"
    assert envelope.identity.tenant.active_roles == ("member",)
    assert envelope.identity.consumer.consumer_id == "ai00.web.compatibility"
    assert envelope.payload == {"item_type": "task", "item_gid": "task-1"}
    context = CapabilityGatewayService._legacy_context(envelope)
    assert context.active_roles == ("member",)


def test_legacy_item_entry_read_uses_gateway_and_preserves_response_shape():
    application = FastAPI()
    application.include_router(item_entries_router)
    gateway = RecordingGateway()
    principal = AuthenticatedPrincipal(
        user_id="user-1",
        authentication_method="jwt",
        authenticated_at=datetime(2026, 8, 12, tzinfo=UTC),
    )
    application.dependency_overrides[get_current_user] = lambda: {
        "gid": "user-1",
        "team_id": "team-1",
        "org_role": "member",
    }
    application.dependency_overrides[get_authenticated_principal] = lambda: principal
    application.dependency_overrides[get_default_gateway] = lambda: gateway

    with TestClient(application) as client:
        response = client.get(
            "/api/item-entries/task/task-1",
            headers={"X-Request-ID": "request-1", "X-Trace-ID": "trace-1"},
        )

    assert response.status_code == 200
    assert response.json() == {"entries": []}
    assert len(gateway.envelopes) == 1
    assert gateway.envelopes[0].capability_id == "project.list.read.atomic.item_entries_get"
    assert gateway.envelopes[0].payload == {"item_type": "task", "item_gid": "task-1"}


def test_legacy_item_entry_writes_use_gateway_governance_headers():
    application = FastAPI()
    application.include_router(item_entries_router)
    gateway = RecordingGateway()
    principal = AuthenticatedPrincipal(
        user_id="user-1",
        authentication_method="jwt",
        authenticated_at=datetime(2026, 8, 12, tzinfo=UTC),
    )
    application.dependency_overrides[get_current_user] = lambda: {
        "gid": "user-1",
        "team_id": "team-1",
        "org_role": "member",
    }
    application.dependency_overrides[get_authenticated_principal] = lambda: principal
    application.dependency_overrides[get_default_gateway] = lambda: gateway
    headers = {
        "X-Request-ID": "request-write-1",
        "X-Trace-ID": "trace-write-1",
        "X-Idempotency-Key": "idem-write-1",
        "X-Capability-Approval": "approval-write-1",
    }

    with TestClient(application) as client:
        replaced = client.put(
            "/api/item-entries/task/task-1",
            headers=headers,
            json={"entries": [{"id": "entry-2", "content": "Updated"}]},
        )
        deleted = client.delete(
            "/api/item-entries/task/task-1",
            headers={**headers, "X-Request-ID": "request-write-2"},
        )

    assert replaced.status_code == 200
    assert replaced.json()["count"] == 1
    assert deleted.status_code == 200
    assert deleted.json() == {"success": True}
    assert [_envelope_operation(item) for item in gateway.envelopes] == [
        "item_entries.replace",
        "item_entries.delete",
    ]
    assert all(item.idempotency_key == "idem-write-1" for item in gateway.envelopes)
    assert all(item.approval_reference == "approval-write-1" for item in gateway.envelopes)


def test_legacy_change_log_read_uses_gateway_and_preserves_response_shape():
    application = FastAPI()
    application.include_router(change_logs_router)
    gateway = RecordingGateway()
    principal = AuthenticatedPrincipal(
        user_id="user-1",
        authentication_method="jwt",
        authenticated_at=datetime(2026, 8, 12, tzinfo=UTC),
    )
    application.dependency_overrides[get_current_user] = lambda: {
        "gid": "user-1",
        "team_id": "team-1",
        "org_role": "member",
    }
    application.dependency_overrides[get_authenticated_principal] = lambda: principal
    application.dependency_overrides[get_default_gateway] = lambda: gateway

    with TestClient(application) as client:
        response = client.get(
            "/api/change-logs",
            params={"item_type": "task", "item_gid": "task-1", "limit": 25},
            headers={"X-Request-ID": "request-change-1", "X-Trace-ID": "trace-change-1"},
        )

    assert response.status_code == 200
    assert response.json() == [
        {
            "gid": "change-1",
            "item_type": "task",
            "item_gid": "task-1",
            "list_gid": "list-1",
            "changed_by": "user-1",
        }
    ]
    assert gateway.envelopes[0].capability_id == "project.change_log.read.atomic.change_logs_search"
    assert gateway.envelopes[0].payload == {
        "item_type": "task",
        "item_gid": "task-1",
        "list_gid": None,
        "limit": 25,
        "offset": 0,
    }


def test_legacy_collaboration_routes_use_read_and_governed_write_capabilities():
    application = FastAPI()
    application.include_router(collab_router_module.router)
    gateway = RecordingGateway()
    principal = AuthenticatedPrincipal(
        user_id="user-1", authentication_method="jwt",
        authenticated_at=datetime(2026, 8, 12, tzinfo=UTC),
    )
    user = {"gid": "user-1", "team_id": "team-1", "org_role": "member"}
    application.dependency_overrides[collab_router_module._MEMBER] = lambda: user
    application.dependency_overrides[get_authenticated_principal] = lambda: principal
    application.dependency_overrides[get_default_gateway] = lambda: gateway
    headers = {
        "X-Request-ID": "request-collab-1", "X-Trace-ID": "trace-collab-1",
        "X-Idempotency-Key": "idem-collab-1", "X-Capability-Approval": "approval-collab-1",
    }

    with TestClient(application) as client:
        listed = client.get("/api/collab/sessions", headers=headers)
        created = client.post(
            "/api/collab/sessions", json={"section_gid": "section-2"}, headers=headers
        )
        joined = client.post("/api/collab/sessions/session-2/join", headers=headers)
        ended = client.post("/api/collab/sessions/session-2/end", headers=headers)

    assert listed.json() == {"success": True, "data": []}
    assert created.status_code == 201
    assert created.json() == {"success": True, "data": {"gid": "session-2"}}
    assert joined.json() == ended.json() == {"success": True}
    assert [envelope.capability_id for envelope in gateway.envelopes] == [
        "project.collaboration.read.atomic.collaboration_sessions_list",
        "project.collaboration.change.apply.atomic.collaboration_sessions_create",
        "project.collaboration.change.apply.atomic.collaboration_sessions_join",
        "project.collaboration.change.apply.atomic.collaboration_sessions_end",
    ]
    assert gateway.envelopes[0].idempotency_key is None
    assert all(envelope.idempotency_key == "idem-collab-1" for envelope in gateway.envelopes[1:])
    assert all(envelope.approval_reference == "approval-collab-1" for envelope in gateway.envelopes[1:])


def test_legacy_share_link_resolve_uses_project_sharing_capability():
    application = FastAPI()
    application.include_router(share_links_router_module.router)
    gateway = RecordingGateway()
    principal = AuthenticatedPrincipal(user_id="user-1", authentication_method="jwt", authenticated_at=datetime(2026, 8, 12, tzinfo=UTC))
    application.dependency_overrides[get_current_user] = lambda: {"gid": "user-1", "team_id": "team-1", "org_role": "member"}
    application.dependency_overrides[get_authenticated_principal] = lambda: principal
    application.dependency_overrides[get_default_gateway] = lambda: gateway
    with TestClient(application) as client:
        response = client.get("/api/share-links/token-1", headers={"X-Request-ID": "request-share-1"})
    assert response.status_code == 200
    assert response.json()["current_permission"] == "read"
    assert gateway.envelopes[0].capability_id == "project.sharing.read.atomic.share_links_resolve"
    assert gateway.envelopes[0].payload == {"token": "token-1"}
