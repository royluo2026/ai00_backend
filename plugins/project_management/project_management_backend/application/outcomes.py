"""Replaceable application boundary for reviewed Project Management outcomes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from backend.capability_v2.provider_contracts import CapabilityBusinessError


class ProjectOutcomeProvider(Protocol):
    def invoke(
        self, capability_id: str, payload: dict[str, Any], context: object
    ) -> dict[str, Any]: ...


@dataclass
class ProjectOutcomePort:
    provider: ProjectOutcomeProvider | None = None

    def bind(self, provider: ProjectOutcomeProvider) -> None:
        self.provider = provider

    def clear(self) -> None:
        self.provider = None

    def invoke(
        self, capability_id: str, payload: dict[str, Any], context: object
    ) -> dict[str, Any]:
        if self.provider is None:
            raise CapabilityBusinessError(
                "provider_unavailable",
                "The Project Management application provider is unavailable.",
                retryable=True,
            )
        return self.provider.invoke(capability_id, payload, context)


project_outcome_port = ProjectOutcomePort()

__all__ = ["ProjectOutcomePort", "ProjectOutcomeProvider", "project_outcome_port"]
