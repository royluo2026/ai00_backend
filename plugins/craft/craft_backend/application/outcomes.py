"""Replaceable application boundary for the final reviewed Craft outcomes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from backend.capability_v2.provider_contracts import CapabilityBusinessError


class CraftOutcomeProvider(Protocol):
    def invoke(
        self, capability_id: str, payload: dict[str, Any], context: object
    ) -> dict[str, Any]: ...


@dataclass
class CraftOutcomePort:
    provider: CraftOutcomeProvider | None = None

    def bind(self, provider: CraftOutcomeProvider) -> None:
        self.provider = provider

    def clear(self) -> None:
        self.provider = None

    def invoke(
        self, capability_id: str, payload: dict[str, Any], context: object
    ) -> dict[str, Any]:
        if self.provider is None:
            raise CapabilityBusinessError(
                "provider_unavailable",
                "The Craft application provider is unavailable.",
                retryable=True,
            )
        return self.provider.invoke(capability_id, payload, context)


craft_outcome_port = CraftOutcomePort()

__all__ = ["CraftOutcomePort", "CraftOutcomeProvider", "craft_outcome_port"]
