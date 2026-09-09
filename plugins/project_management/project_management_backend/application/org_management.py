"""Application service for the management-center responsibility tree."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from backend.capability_v2.provider_contracts import CapabilityBusinessError

from ..domain.models import decode_org_management
from ..infrastructure.org_management_repository import OrgManagementRepository


def _tenant(context: object) -> str:
    return str(getattr(context, "team_gid", None) or f"user:{getattr(context, 'user_gid', '')}")


def validate_project(payload: dict[str, Any], context: object) -> dict[str, Any]:
    row = OrgManagementRepository().project(payload["project_gid"])
    if not row or bool(row.get("is_deleted")):
        raise CapabilityBusinessError("resource_not_found", "项目不存在")
    tenant = _tenant(context)
    if str(row.get("team_id") or "") != tenant:
        raise CapabilityBusinessError("permission_denied", "项目不属于当前租户")
    return {"data": {"gid": str(row["gid"]), "team_id": str(row["team_id"]),
                     "is_deleted": bool(row["is_deleted"])}}


def read(payload: dict[str, Any], context: object) -> dict[str, Any]:
    arguments = payload["arguments"]
    repo = OrgManagementRepository()
    tenant = _tenant(context)
    if payload["operation"] == "operation.get":
        row = repo.operation(str(arguments.get("operation_gid") or ""), tenant)
        if not row:
            raise CapabilityBusinessError("resource_not_found", "操作不存在")
        return {"data": {"items": [{"gid": str(row["operation_gid"]),
                                      "name": str(row["status"]),
                                      "revision": int(row["revision"]), "lines": []}],
                         "next_cursor": None}}
    if payload["operation"] == "responsibility_matrix.get":
        project_gid = str(arguments.get("project_gid") or "")
        row = repo.project(project_gid, tenant)
        if not row:
            raise CapabilityBusinessError("resource_not_found", "项目不存在")
        state = decode_org_management(row.get("meta"))
        return {"data": {"items": [{"gid": str(row["gid"]), "name": str(row.get("name") or ""), **state}],
                         "next_cursor": None}}
    size = int(arguments.get("page_size") or 100)
    items, next_cursor = repo.search(tenant, arguments.get("cursor"), size)
    return {"data": {"items": items, "next_cursor": next_cursor}}


async def change(payload: dict[str, Any], context: object) -> dict[str, Any]:
    if "super_admin" not in set(getattr(context, "active_roles", ()) or ()):
        raise CapabilityBusinessError("permission_denied", "仅超管可维护项目责任")
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    repository = OrgManagementRepository()
    result = repository.apply(
        tenant_gid=_tenant(context), actor_gid=str(getattr(context, "user_gid", "")),
        project_gid=str(payload["arguments"].get("project_gid") or ""),
        operation=payload["operation"], arguments=payload["arguments"],
        expected_revision=payload["expected_revision"], idempotency_key=payload["idempotency_key"],
        command_digest=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    )
    pending = repository.pending_projection(result["operation_gid"], _tenant(context))
    if pending is None:
        return {"data": result}
    from backend.capability_v2.delegation import InMemoryDelegationStore
    from backend.capability_v2.domain_client import DomainInvocation
    from backend.capability_v2.identity import AuthenticatedPrincipal, IdentityBroker, InMemoryMountStore
    from backend.capability_v2.official_service_grants import official_service_identities
    from backend.capability_v2.contracts import CorrelationRef
    service_id = "project-org-projection"
    tenant_gid = _tenant(context)
    try:
        with official_service_identities.trusted_tenant(
            service_id=service_id, tenant_id=tenant_gid, source_kind="project_outbox",
            source_ref=result["operation_gid"],
        ):
            broker = IdentityBroker(official_service_identities, InMemoryDelegationStore(), InMemoryMountStore())
            identity = broker.for_worker(
                AuthenticatedPrincipal(service_id=service_id, authentication_method="project_outbox",
                                       authenticated_at=datetime.now(UTC)),
                tenant_id=tenant_gid, worker_id=service_id,
            )
            line = pending["line"]
            outcome = await context.domain_client.invoke(
                DomainInvocation(
                    capability_id="base.project_responsibility.projection.apply", major_version=1,
                    payload={"operation_gid": result["operation_gid"], "source_gid": line["gid"],
                             "source_revision": pending["revision"], "project_gid": str(payload["arguments"]["project_gid"]),
                             "bop_line_gid": line.get("bop_line_gid"),
                             "user_gids": line.get("leader_user_gids", []),
                             "idempotency_key": result["operation_gid"]},
                    idempotency_key=result["operation_gid"],
                ), identity,
                CorrelationRef(request_id=str(getattr(context, "request_id", result["operation_gid"])),
                               trace_id=str(getattr(context, "request_id", result["operation_gid"]))),
            )
        if not outcome.ok:
            raise RuntimeError(outcome.error.message if outcome.error else "projection failed")
        repository.complete_projection(result["operation_gid"], tenant_gid)
        result["status"] = "completed"
    except Exception as exc:
        repository.fail_projection(result["operation_gid"], tenant_gid, str(exc))
        result["status"] = "failed_retryable"
    return {"data": result}


__all__ = ["change", "read", "validate_project"]
