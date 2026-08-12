"""Replaceable application boundary for reviewed device lifecycle outcomes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from backend.capability_v2.provider_contracts import CapabilityBusinessError


class DeviceOutcomeProvider(Protocol):
    def invoke(
        self, capability_id: str, payload: dict[str, Any], context: object
    ) -> dict[str, Any]: ...


@dataclass
class DeviceOutcomePort:
    provider: DeviceOutcomeProvider | None = None

    def bind(self, provider: DeviceOutcomeProvider) -> None:
        self.provider = provider

    def clear(self) -> None:
        self.provider = None

    def invoke(
        self, capability_id: str, payload: dict[str, Any], context: object
    ) -> dict[str, Any]:
        if self.provider is None:
            raise CapabilityBusinessError(
                "provider_unavailable",
                "The Local Runtime device provider is unavailable.",
                retryable=True,
            )
        return self.provider.invoke(capability_id, payload, context)


device_outcome_port = DeviceOutcomePort()

__all__ = ["DeviceOutcomePort", "DeviceOutcomeProvider", "device_outcome_port"]
