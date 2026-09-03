from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from backend.capability_v2.contracts import (
    ActorIdentity,
    ConsumerDescriptor,
    ConsumerIdentity,
    ConsumerType,
    InvocationEnvelope,
    TenantIdentity,
)
from backend.capability_v2.identity import AuthenticatedPrincipal
from plugins.craft.craft_backend.routers import ontology
from plugins.factory.factory_backend.api.compatibility import (
    build_web_compatibility_envelope,
    invoke_compatibility as invoke_factory_compatibility,
)
from plugins.project_management.project_management_backend.api.compatibility import (
    invoke_compatibility as invoke_project_compatibility,
)
from plugins.simulation.simulation_backend.routers import environments


class Error:
    code = "confirmation_required"
    message = "Confirmation is required."

    def model_dump(self, **_kwargs):
        return {"code": self.code, "message": self.message}


class Result:
    def __init__(self, ok: bool):
        self.ok = ok
        self.error = None if ok else Error()
        self.data = {"data": {"gid": "created-1"}} if ok else None

    def model_dump(self, **_kwargs):
        return {
            "ok": self.ok,
            "data": self.data,
            "error": self.error.model_dump() if self.error else None,
        }


class ConfirmingGateway:
    catalog_release = "rel_adapter_test"

    def __init__(self):
        self.invocations = []
        self.approvals = []

    async def invoke(self, envelope):
        self.invocations.append(envelope)
        return Result(ok=len(self.invocations) > 1)

    async def request_approval(self, envelope):
        self.approvals.append(envelope)
        return type("Issued", (), {"token": "approval-1"})()


def _envelope(consumer_id: str) -> InvocationEnvelope:
    return InvocationEnvelope(
        capability_id="project.list.change.apply",
        major_version=1,
        catalog_release="rel_adapter_test",
        payload={"operation": "lists.create", "arguments": {"name": "任务清单"}},
        identity=ConsumerIdentity(
            actor=ActorIdentity(
                user_id="user-1",
                authentication_method="jwt",
                authenticated_at=datetime(2026, 8, 14, tzinfo=UTC),
            ),
            tenant=TenantIdentity(tenant_id="team-1", membership="member"),
            consumer=ConsumerDescriptor(type=ConsumerType.WEB, consumer_id=consumer_id),
        ),
        request_id="request-1",
        trace_id="trace-1",
    )


def _principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user_id="user-1",
        authentication_method="jwt",
        authenticated_at=datetime(2026, 8, 14, tzinfo=UTC),
    )


def test_factory_web_envelope_defaults_to_v1_and_accepts_explicit_major():
    gateway = SimpleNamespace(catalog_release="rel_adapter_test")
    common = dict(
        gateway=gateway,
        capability_id="agent.interaction.chat.change.apply",
        payload={"operation": "chat_sync", "body": {"message": "hi"}},
        current_user={"gid": "user-1", "team_id": "team-1", "org_role": "member"},
        principal=_principal(),
        request_id="request-1",
        trace_id="trace-1",
    )

    assert build_web_compatibility_envelope(**common).major_version == 1
    assert build_web_compatibility_envelope(**common, major_version=2).major_version == 2


def test_project_legacy_adapter_completes_unapproved_governed_write():
    gateway = ConfirmingGateway()

    result = asyncio.run(
        invoke_project_compatibility(gateway, _envelope("ai00.web.compatibility"))
    )

    assert result.ok is True
    assert len(gateway.invocations) == 2
    assert len(gateway.approvals) == 1


def test_factory_legacy_adapter_completes_unapproved_governed_write():
    gateway = ConfirmingGateway()

    result = asyncio.run(
        invoke_factory_compatibility(
            gateway, _envelope("ai00.web.factory.compatibility")
        )
    )

    assert result.ok is True
    assert len(gateway.invocations) == 2
    assert len(gateway.approvals) == 1


def test_ontology_legacy_adapter_completes_unapproved_governed_write(monkeypatch):
    gateway = ConfirmingGateway()
    monkeypatch.setattr(ontology, "get_default_gateway", lambda: gateway)

    result = asyncio.run(
        ontology._invoke(
            "ontology.schema.change.apply",
            {"base_release_gid": "release-1", "changes": []},
            {"gid": "user-1", "team_id": "team-1", "org_role": "member"},
            _principal(),
            write=True,
        )
    )

    assert result == {"data": {"gid": "created-1"}}
    assert len(gateway.invocations) == 2
    assert len(gateway.approvals) == 1


def test_simulation_legacy_adapter_completes_unapproved_governed_write(monkeypatch):
    gateway = ConfirmingGateway()
    monkeypatch.setattr(environments, "get_default_gateway", lambda: gateway)
    request = type("Request", (), {"headers": {}})()

    response = asyncio.run(
        environments._invoke(
            "simulation.environment.create",
            {"name": "Simulation"},
            request,
            {"gid": "user-1", "team_id": "team-1", "org_role": "member"},
            _principal(),
        )
    )

    assert response["success"] is True
    assert len(gateway.invocations) == 2
    assert len(gateway.approvals) == 1
