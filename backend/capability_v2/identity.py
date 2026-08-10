"""Server-only adapters that construct trusted Capability consumer identities."""
from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime
from typing import Callable, Protocol

from pydantic import Field, model_validator

from .contracts import (
    ActorIdentity,
    ConsumerDescriptor,
    ConsumerIdentity,
    ConsumerType,
    DelegationContext,
    FrozenModel,
    IDENTITY_PATTERN,
    TenantIdentity,
)
from .delegation import DelegationError, DelegationStore, hash_token


class IdentityError(PermissionError):
    pass


class AuthenticatedPrincipal(FrozenModel):
    user_id: str | None = Field(default=None, pattern=IDENTITY_PATTERN)
    service_id: str | None = Field(default=None, pattern=IDENTITY_PATTERN)
    authentication_method: str = Field(min_length=1, max_length=64)
    authenticated_at: datetime

    @model_validator(mode="after")
    def principal_contract(self) -> "AuthenticatedPrincipal":
        if (self.user_id is None) == (self.service_id is None):
            raise ValueError("principal requires exactly one actor")
        if self.authenticated_at.tzinfo is None or self.authenticated_at.utcoffset() is None:
            raise ValueError("authenticated_at must be timezone-aware")
        return self


class TenantMembership(FrozenModel):
    tenant_id: str = Field(pattern=IDENTITY_PATTERN)
    membership: str = Field(min_length=1, max_length=64)
    active_roles: tuple[str, ...] = ()
    active: bool


class MembershipResolver(Protocol):
    def resolve(self, *, user_id: str | None = None, service_id: str | None = None,
                tenant_id: str) -> TenantMembership: ...


class MountGrant(FrozenModel):
    mount_session_id: str = Field(pattern=IDENTITY_PATTERN)
    user_id: str = Field(pattern=IDENTITY_PATTERN)
    tenant_id: str = Field(pattern=IDENTITY_PATTERN)
    plugin_id: str = Field(pattern=IDENTITY_PATTERN)
    plugin_version: str = Field(min_length=1, max_length=128)
    installation_id: str = Field(pattern=IDENTITY_PATTERN)
    authentication_method: str = "jwt"
    authenticated_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None

    @model_validator(mode="after")
    def mount_contract(self) -> "MountGrant":
        if any(value.tzinfo is None or value.utcoffset() is None
               for value in (self.authenticated_at, self.expires_at)):
            raise ValueError("mount timestamps must be timezone-aware")
        if self.expires_at <= self.authenticated_at:
            raise ValueError("mount expiry must follow authentication")
        return self


class MountStore(Protocol):
    def consume_active(self, token: str) -> MountGrant: ...


class InMemoryMountStore:
    """Test-only mount-session store used until the Manifest V2 migration."""

    def __init__(self, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._clock = clock
        self._records: dict[str, MountGrant] = {}

    def issue(self, grant: MountGrant) -> str:
        token = secrets.token_urlsafe(32)
        self._records[hashlib.sha256(token.encode("utf-8")).hexdigest()] = grant
        return token

    def consume_active(self, token: str) -> MountGrant:
        grant = self._records.get(hashlib.sha256(token.encode("utf-8")).hexdigest())
        if grant is None:
            raise IdentityError("mount_session_invalid")
        if grant.revoked_at is not None:
            raise IdentityError("mount_session_revoked")
        if grant.expires_at <= self._clock():
            raise IdentityError("mount_session_expired")
        return grant


class IdentityBroker:
    def __init__(self, memberships: MembershipResolver, delegation_store: DelegationStore,
                 mount_store: MountStore, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._memberships = memberships
        self._delegations = delegation_store
        self._mounts = mount_store
        self._clock = clock

    def _identity(self, principal: AuthenticatedPrincipal, tenant_id: str,
                  consumer: ConsumerDescriptor, delegation: DelegationContext | None = None) -> ConsumerIdentity:
        membership = self._memberships.resolve(
            user_id=principal.user_id,
            service_id=principal.service_id,
            tenant_id=tenant_id,
        )
        if membership.tenant_id != tenant_id or not membership.active:
            raise IdentityError("tenant_membership_inactive")
        return ConsumerIdentity(
            actor=ActorIdentity(**principal.model_dump()),
            tenant=TenantIdentity(
                tenant_id=membership.tenant_id,
                membership=membership.membership,
                active_roles=membership.active_roles,
            ),
            consumer=consumer,
            delegation=delegation,
        )

    def for_web(self, principal: AuthenticatedPrincipal, *, tenant_id: str) -> ConsumerIdentity:
        return self._identity(principal, tenant_id, ConsumerDescriptor(type=ConsumerType.WEB, consumer_id="ai00.web"))

    def for_plugin_mount(self, token: str) -> ConsumerIdentity:
        grant = self._mounts.consume_active(token)
        principal = AuthenticatedPrincipal(
            user_id=grant.user_id,
            authentication_method=grant.authentication_method,
            authenticated_at=grant.authenticated_at,
        )
        return self._identity(principal, grant.tenant_id, ConsumerDescriptor(
            type=ConsumerType.PLUGIN,
            consumer_id=grant.plugin_id,
            consumer_version=grant.plugin_version,
            installation_id=grant.installation_id,
            mount_session_id=grant.mount_session_id,
        ))

    def for_agent_delegation(self, token: str) -> ConsumerIdentity:
        try:
            grant = self._delegations.consume_active(token)
        except DelegationError as exc:
            raise IdentityError(str(exc)) from exc
        if grant.consumer_type is not ConsumerType.AGENT:
            raise IdentityError("delegation_consumer_mismatch")
        principal = AuthenticatedPrincipal(
            user_id=grant.user_id,
            service_id=grant.service_id,
            authentication_method=grant.authentication_method,
            authenticated_at=grant.authenticated_at,
        )
        context = DelegationContext(
            delegation_id=grant.delegation_id,
            delegated_by=grant.delegated_by,
            capability_scopes=grant.capability_scopes,
            resource_scopes=grant.resource_scopes,
            data_scopes=grant.data_scopes,
            catalog_release=grant.catalog_release,
            maximum_automation_level=grant.maximum_automation_level,
            expires_at=grant.expires_at,
        )
        return self._identity(principal, grant.tenant_id, ConsumerDescriptor(
            type=ConsumerType.AGENT,
            consumer_id=grant.consumer_id,
            consumer_version=grant.consumer_version,
            agent_run_id=grant.agent_run_id,
        ), context)

    def for_mcp_client(self, principal: AuthenticatedPrincipal, *, tenant_id: str, client_id: str) -> ConsumerIdentity:
        return self._identity(principal, tenant_id, ConsumerDescriptor(type=ConsumerType.MCP, consumer_id=client_id))

    def for_worker(self, principal: AuthenticatedPrincipal, *, tenant_id: str, worker_id: str) -> ConsumerIdentity:
        self._require_service(principal)
        return self._identity(principal, tenant_id, ConsumerDescriptor(type=ConsumerType.WORKER, consumer_id=worker_id))

    def for_local_runtime(self, principal: AuthenticatedPrincipal, *, tenant_id: str, runtime_id: str) -> ConsumerIdentity:
        self._require_service(principal)
        return self._identity(principal, tenant_id, ConsumerDescriptor(type=ConsumerType.LOCAL_RUNTIME, consumer_id=runtime_id))

    @staticmethod
    def _require_service(principal: AuthenticatedPrincipal) -> None:
        if principal.service_id is None:
            raise IdentityError("service_principal_required")


__all__ = [
    "AuthenticatedPrincipal",
    "IdentityBroker",
    "IdentityError",
    "InMemoryMountStore",
    "MountGrant",
    "TenantMembership",
]
