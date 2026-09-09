"""Closed identities and grants for official org-management services."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator

from .authorization import AuthorizationGrants
from .contracts import ConsumerIdentity
from .identity import IdentityError, TenantMembership


@dataclass(frozen=True)
class _TenantAuthority:
    service_id: str
    tenant_id: str
    source_kind: str
    source_ref: str


_AUTHORITY: ContextVar[_TenantAuthority | None] = ContextVar(
    "ai00_official_service_tenant_authority", default=None
)


class OfficialServiceIdentityRegistry:
    """Composition-root allowlist; intentionally not user configurable."""

    _CAPABILITIES = {
        "base-project-validator": ("project.project.validation.get",),
        "project-org-projection": (
            "base.project_responsibility.projection.apply",
            "base.project_responsibility.projection.get",
        ),
    }

    @contextmanager
    def trusted_tenant(
        self, *, service_id: str, tenant_id: str, source_kind: str, source_ref: str
    ) -> Iterator[None]:
        if service_id not in self._CAPABILITIES:
            raise IdentityError("official_service_unknown")
        if source_kind not in {"authenticated_request", "project_outbox"} or not source_ref:
            raise IdentityError("official_service_tenant_source_invalid")
        token = _AUTHORITY.set(_TenantAuthority(service_id, tenant_id, source_kind, source_ref))
        try:
            yield
        finally:
            _AUTHORITY.reset(token)

    def resolve(self, *, user_id=None, service_id=None, tenant_id: str) -> TenantMembership:
        authority = _AUTHORITY.get()
        if user_id is not None or service_id not in self._CAPABILITIES:
            raise IdentityError("official_service_unknown")
        if authority is None or authority.service_id != service_id or authority.tenant_id != tenant_id:
            raise IdentityError("official_service_tenant_denied")
        return TenantMembership(
            tenant_id=tenant_id, membership="official_service",
            active_roles=("official_service",), active=True,
        )

    def grants(self, identity: ConsumerIdentity) -> AuthorizationGrants:
        service_id = identity.actor.service_id
        authority = _AUTHORITY.get()
        if service_id not in self._CAPABILITIES or authority is None:
            raise IdentityError("official_service_unknown")
        if authority.service_id != service_id or authority.tenant_id != identity.tenant.tenant_id:
            raise IdentityError("official_service_tenant_denied")
        if identity.consumer.consumer_id != service_id:
            raise IdentityError("official_service_consumer_denied")
        return AuthorizationGrants(
            permissions=("base.read", "project.view", "system.user.manage"),
            capability_scopes=self._CAPABILITIES[service_id],
            resource_scopes=("*",), data_scopes=("confidential",),
            policy_version="official-service-v1",
            tenant_id=identity.tenant.tenant_id,
        )


official_service_identities = OfficialServiceIdentityRegistry()


__all__ = ["OfficialServiceIdentityRegistry", "official_service_identities"]
