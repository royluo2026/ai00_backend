"""Public references and application port owned by Project Management."""
from __future__ import annotations

from typing import Protocol, Sequence

from pydantic import Field

from backend.capability_v2.contracts import FrozenModel, IDENTITY_PATTERN


class ProjectRef(FrozenModel):
    project_id: str = Field(pattern=IDENTITY_PATTERN)
    object_ref: str = Field(pattern=r"^project:[A-Za-z0-9_.:-]+$")
    title: str = Field(min_length=1, max_length=255)


class ProjectManagementDomainPort(Protocol):
    def search_projects(self, query: str, *, limit: int) -> Sequence[ProjectRef]: ...


__all__ = ["ProjectManagementDomainPort", "ProjectRef"]
