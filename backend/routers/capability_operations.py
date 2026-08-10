"""Read-only HTTP transport for tenant-scoped Capability V2 operations."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.capability_v2.contracts import (
    ActorIdentity, ConsumerDescriptor, ConsumerIdentity, ConsumerType, TenantIdentity,
)
from backend.capability_v2.operations import (
    OperationAuthorizationError, OperationError, OperationService, SqlOperationStore,
)
from backend.db.connection import get_conn
from backend.routers.deps import (
    build_capability_authorization_grants, get_authenticated_principal, get_current_user,
)


router = APIRouter(prefix="/api/v2/capability-operations", tags=["capability-operations"])


def _identity(user: dict, principal) -> ConsumerIdentity:
    return ConsumerIdentity(
        actor=ActorIdentity(**principal.model_dump()),
        tenant=TenantIdentity(
            tenant_id=str(user.get("team_id") or "default"), membership="member",
            active_roles=tuple(filter(None, (user.get("org_role"), user.get("system_role")))),
        ),
        consumer=ConsumerDescriptor(type=ConsumerType.WEB, consumer_id="ai00.web"),
    )


@router.get("/{operation_id}")
def get_operation(
    operation_id: str,
    user: dict = Depends(get_current_user),
    principal=Depends(get_authenticated_principal),
):
    identity = _identity(user, principal)
    grants = build_capability_authorization_grants(user, identity.tenant.tenant_id, "web")
    try:
        record = OperationService(SqlOperationStore(get_conn)).get_authorized(
            operation_id, identity, granted_resources=grants.resource_scopes,
        )
    except OperationAuthorizationError as exc:
        raise HTTPException(status_code=403, detail={"code": "operation_access_denied"}) from exc
    except OperationError as exc:
        status = 404 if "not_found" in str(exc) else 503
        raise HTTPException(status_code=status, detail={"code": str(exc)}) from exc
    return {
        "operation_ref": record.ref.model_dump(mode="json"),
        "kind": record.kind,
        "resource_refs": record.resource_refs,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "error_code": record.error_code,
    }

