"""Resource- and data-scoped authorization for Capability V2."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Callable

from .contracts import (
    AutomationLevel,
    CapabilityDescriptorV2,
    ConsumerIdentity,
    ConsumerType,
    FrozenModel,
    InvocationEnvelope,
)


class AuthorizationGrants(FrozenModel):
    permissions: tuple[str, ...] = ()
    capability_scopes: tuple[str, ...] = ("*",)
    resource_scopes: tuple[str, ...] = ()
    data_scopes: tuple[str, ...] = ()
    policy_version: str
    tenant_id: str | None = None


class AuthorizationDecision(FrozenModel):
    allowed: bool
    code: str
    policy_version: str
    resource_refs: tuple[str, ...] = ()
    data_scopes: tuple[str, ...] = ()


GrantResolver = Callable[[ConsumerIdentity], AuthorizationGrants]


class CapabilityAuthorizer:
    def __init__(self, grants: GrantResolver) -> None:
        self._grants = grants

    def authorize(
        self,
        descriptor: CapabilityDescriptorV2,
        envelope: InvocationEnvelope,
        *,
        required_permissions: tuple[str, ...] = (),
    ) -> AuthorizationDecision:
        identity = envelope.identity
        try:
            grants = self._grants(identity)
        except Exception:
            return self._deny("authorization_backend_failed", "unavailable")
        policy_version = grants.policy_version

        if grants.tenant_id is not None and grants.tenant_id != identity.tenant.tenant_id:
            return self._deny("tenant_scope_denied", policy_version)
        missing = set(required_permissions) - set(grants.permissions)
        if missing:
            return self._deny("permission_denied", policy_version)
        if not _scope_allows(grants.capability_scopes, descriptor.id):
            return self._deny("consumer_capability_scope_denied", policy_version)

        resource_refs, selector_error = _resource_refs(descriptor, envelope.payload)
        if selector_error:
            return self._deny(selector_error, policy_version)
        if any(not _scope_allows(grants.resource_scopes, ref) for ref in resource_refs):
            return self._deny("resource_scope_denied", policy_version, resource_refs)

        classification = descriptor.data_classification
        if classification in {"confidential", "restricted"} and not _scope_allows(
            grants.data_scopes, classification
        ):
            return self._deny("data_scope_denied", policy_version, resource_refs)

        delegated_error = _delegation_error(descriptor, envelope, resource_refs)
        if delegated_error:
            return self._deny(delegated_error, policy_version, resource_refs)

        return AuthorizationDecision(
            allowed=True,
            code="allowed",
            policy_version=policy_version,
            resource_refs=resource_refs,
            data_scopes=_effective_data_scopes(identity, grants.data_scopes),
        )

    @staticmethod
    def _deny(code: str, policy_version: str,
              resource_refs: tuple[str, ...] = ()) -> AuthorizationDecision:
        return AuthorizationDecision(
            allowed=False, code=code, policy_version=policy_version, resource_refs=resource_refs
        )


def _resource_refs(descriptor, payload) -> tuple[tuple[str, ...], str | None]:
    refs: list[str] = []
    for selector in descriptor.resource_selectors:
        found, value = _select(payload, selector.payload_path)
        if not found or value is None or value == "":
            if selector.required:
                return (), "resource_selector_missing"
            continue
        if isinstance(value, (dict, list, tuple, set, bool)):
            return (), "resource_selector_invalid"
        refs.append(f"{selector.resource_type}:{value}")
    return tuple(refs), None


def _select(payload, path: str):
    parts = (
        [part.replace("~1", "/").replace("~0", "~") for part in path.lstrip("/").split("/")]
        if path.startswith("/")
        else path.split(".")
    )
    current = payload
    for part in parts:
        if not part or not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def _scope_allows(scopes: tuple[str, ...], requested: str) -> bool:
    resource_type = requested.split(":", 1)[0]
    return "*" in scopes or requested in scopes or f"{resource_type}:*" in scopes


def _delegation_error(descriptor, envelope, resource_refs) -> str | None:
    identity = envelope.identity
    if identity.consumer.type is ConsumerType.PLUGIN:
        if not identity.consumer.installation_id or not identity.consumer.mount_session_id:
            return "plugin_mount_required"
        if identity.delegation is None:
            return None
    if identity.consumer.type is not ConsumerType.AGENT and identity.delegation is None:
        return None
    delegation = identity.delegation
    if delegation is None:
        return "delegation_required"
    if delegation.expires_at <= datetime.now(UTC):
        return "delegation_expired"
    if delegation.catalog_release != envelope.catalog_release:
        return "delegation_catalog_mismatch"
    if not _scope_allows(delegation.capability_scopes, descriptor.id):
        return "capability_scope_denied"
    if _automation_rank(descriptor.automation_level) > _automation_rank(
        delegation.maximum_automation_level
    ):
        return "automation_scope_denied"
    if any(not _scope_allows(delegation.resource_scopes, ref) for ref in resource_refs):
        return "resource_scope_denied"
    if descriptor.data_classification in {"confidential", "restricted"} and not _scope_allows(
        delegation.data_scopes, descriptor.data_classification
    ):
        return "data_scope_denied"
    if identity.consumer.type is ConsumerType.AGENT and not identity.consumer.agent_run_id:
        return "agent_run_required"
    if identity.consumer.type is ConsumerType.PLUGIN and not identity.consumer.installation_id:
        return "plugin_installation_required"
    return None


def _automation_rank(level: AutomationLevel) -> int:
    return int(level.value[1:])


def _effective_data_scopes(identity: ConsumerIdentity, granted: tuple[str, ...]) -> tuple[str, ...]:
    delegation = identity.delegation
    if delegation is None:
        return granted
    delegated = delegation.data_scopes
    if "*" in granted:
        return delegated
    if "*" in delegated:
        return granted
    return tuple(sorted(set(granted) & set(delegated)))


__all__ = ["AuthorizationDecision", "AuthorizationGrants", "CapabilityAuthorizer"]
