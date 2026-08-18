"""Port for candidate-only capability-governance advice from the Agent domain."""
from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from backend.capability_governance_test.ai_advisory import AdvisoryResult
    from backend.capability_v2.contracts import ConsumerIdentity


class GovernanceAdvisorPort(Protocol):
    """The advisory boundary deliberately has no confirmation or mutation methods."""

    async def review(
        self,
        package: Mapping[str, Any],
        *,
        identity: "ConsumerIdentity",
        request_id: str,
    ) -> "AdvisoryResult": ...


__all__ = ["GovernanceAdvisorPort"]
