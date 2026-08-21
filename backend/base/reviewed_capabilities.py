"""Reviewed Base outcomes exposed through a replaceable application port."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from backend.capability_v2.provider_contracts import (
    CapabilityBusinessError,
    CapabilityRisk,
    CapabilitySpec,
)

from .provider import register_capability


READ_CAPABILITIES = {
    "base.annotation.read",
    "base.authorization.grant.read",
    "base.identity.session.get",
    "base.plugin.marketplace.search",
    "base.saved_view.read",
    "base.team.read",
}
WRITE_CAPABILITIES = {
    "base.annotation.change.apply",
    "base.authorization.grant.change.apply",
    "base.identity.directory.sync",
    "base.identity.role.assign",
    "base.plugin.marketplace.publisher.register",
    "base.plugin.marketplace.release.change.apply",
    "base.saved_view.change.apply",
    "base.team.change.apply",
    "base.team.membership.change.apply",
}
REVIEWED_BASE_CAPABILITIES = READ_CAPABILITIES | WRITE_CAPABILITIES


class BaseOutcomeProvider(Protocol):
    def invoke(
        self,
        capability_id: str,
        payload: dict[str, Any],
        context: object,
    ) -> dict[str, Any]: ...


@dataclass
class BaseOutcomePort:
    provider: BaseOutcomeProvider | None = None

    def bind(self, provider: BaseOutcomeProvider) -> None:
        self.provider = provider

    def clear(self) -> None:
        self.provider = None

    def invoke(
        self,
        capability_id: str,
        payload: dict[str, Any],
        context: object,
    ) -> dict[str, Any]:
        if self.provider is None:
            raise CapabilityBusinessError(
                "provider_unavailable",
                "The Base application provider is unavailable.",
                retryable=True,
            )
        return self.provider.invoke(capability_id, payload, context)


base_outcome_port = BaseOutcomePort()


def _handler(capability_id: str):
    def invoke(payload: dict[str, Any], context: object) -> dict[str, Any]:
        return base_outcome_port.invoke(capability_id, payload, context)

    return invoke


def register_reviewed_base_capabilities(registry: Any) -> None:
    for capability_id in sorted(REVIEWED_BASE_CAPABILITIES):
        is_write = capability_id in WRITE_CAPABILITIES
        register_capability(
            registry,
            CapabilitySpec(
                owner="base",
                id=capability_id,
                version=1,
                description=f"Execute the reviewed {capability_id} Base outcome.",
                risk=CapabilityRisk.WRITE if is_write else CapabilityRisk.READ,
                confirmation="user" if is_write else "none",
                idempotent=True,
                permissions=("base.read",) if not is_write else ("base.write",),
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                tags=("base", "reviewed", "write" if is_write else "read"),
            ),
            _handler(capability_id),
        )


__all__ = [
    "BaseOutcomePort",
    "BaseOutcomeProvider",
    "REVIEWED_BASE_CAPABILITIES",
    "base_outcome_port",
    "register_reviewed_base_capabilities",
]
