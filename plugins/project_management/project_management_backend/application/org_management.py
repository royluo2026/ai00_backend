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


def _project_tenant(repository: OrgManagementRepository, project_gid: str, context: object) -> str:
    row = repository.project(project_gid)
    if not row or bool(row.get("is_deleted")):
        raise CapabilityBusinessError("resource_not_found", "项目不存在")
    owner_tenant = str(row.get("team_id") or _tenant(context))
    if owner_tenant != _tenant(context) and "super_admin" not in set(
        getattr(context, "active_roles", ()) or ()
    ):
        raise CapabilityBusinessError("permission_denied", "项目不属于当前租户")
    return owner_tenant


def validate_project(payload: dict[str, Any], context: object) -> dict[str, Any]:
    row = OrgManagementRepository().project(payload["project_gid"])
    if not row or bool(row.get("is_deleted")):
        raise CapabilityBusinessError("resource_not_found", "项目不存在")
    tenant = _tenant(context)
    identity = getattr(context, "effective_identity", None)
    service_id = getattr(getattr(identity, "actor", None), "service_id", None)
    if str(row.get("team_id") or "") != tenant and service_id != "base-project-validator":
        raise CapabilityBusinessError("permission_denied", "项目不属于当前租户")
    return {"data": {"gid": str(row["gid"]), "team_id": str(row.get("team_id") or tenant),
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
        owner_tenant = _project_tenant(repo, project_gid, context)
        row = repo.project(project_gid)
        if not row:
            raise CapabilityBusinessError("resource_not_found", "项目不存在")
        state = decode_org_management(row.get("meta"))
        return {"data": {"items": [{"gid": str(row["gid"]), "name": str(row.get("name") or ""), **state}],
                         "next_cursor": None}}
    size = int(arguments.get("page_size") or 100)
    search_tenant = None if "super_admin" in set(getattr(context, "active_roles", ()) or ()) else tenant
    items, next_cursor = repo.search(search_tenant, arguments.get("cursor"), size)
    return {"data": {"items": items, "next_cursor": next_cursor}}


async def change(payload: dict[str, Any], context: object) -> dict[str, Any]:
    if "super_admin" not in set(getattr(context, "active_roles", ()) or ()):
        raise CapabilityBusinessError("permission_denied", "仅超管可维护项目责任")
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    repository = OrgManagementRepository()
    tenant_gid = _project_tenant(repository, str(payload["arguments"].get("project_gid") or ""), context)
    from backend.capability_v2.contracts import CorrelationRef
    from backend.capability_v2.domain_client import DomainInvocation
    correlation = CorrelationRef(
        request_id=str(getattr(context, "request_id", "org-management-change")),
        trace_id=str(getattr(context, "request_id", "org-management-change")),
    )
    identity = context.effective_identity
    for user_gid in sorted(set(payload["arguments"].get("leader_user_gids", []))):
        checked = await context.domain_client.invoke(
            DomainInvocation(capability_id="base.identity.active_principal.get", major_version=1,
                             payload={"user_gid": user_gid}), identity, correlation,
        )
        if not checked.ok:
            raise CapabilityBusinessError("resource_not_found", "线体负责人不存在或已停用")
    if payload["arguments"].get("bop_line_gid"):
        checked = await context.domain_client.invoke(
            DomainInvocation(capability_id="craft.bop.active_line.validate", major_version=1,
                             payload={"project_gid": str(payload["arguments"]["project_gid"]),
                                      "bop_line_gid": str(payload["arguments"]["bop_line_gid"])}),
            identity, correlation,
        )
        if not checked.ok:
            raise CapabilityBusinessError("resource_not_found", "BOP 线体不存在、已失效或属于其他项目")
    result = repository.apply(
        tenant_gid=tenant_gid, actor_gid=str(getattr(context, "user_gid", "")),
        project_gid=str(payload["arguments"].get("project_gid") or ""),
        operation=payload["operation"], arguments=payload["arguments"],
        expected_revision=payload["expected_revision"], idempotency_key=payload["idempotency_key"],
        command_digest=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    )
    pending = repository.pending_projection(result["operation_gid"], tenant_gid)
    if pending is None:
        return {"data": result}
    from backend.capability_v2.delegation import InMemoryDelegationStore
    from backend.capability_v2.domain_client import DomainInvocation
    from backend.capability_v2.identity import AuthenticatedPrincipal, IdentityBroker, InMemoryMountStore
    from backend.capability_v2.official_service_grants import official_service_identities
    service_id = "project-org-projection"
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
