from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ImmutableVersionError(ValueError):
    pass


class InvalidLifecycleTransition(ValueError):
    pass


class PbomVersionStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    PUBLISHED = "published"
    ARCHIVED = "archived"


@dataclass(frozen=True)
class PbomVersion:
    gid: str
    project_ref: str
    version_tag: str
    status: PbomVersionStatus = PbomVersionStatus.DRAFT
    knowledge_revision_ref: str | None = None
    ontology_release_ref: str | None = None
    revision_commit_ref: str | None = None
    revision: int = 1

    def require_mutable(self) -> None:
        if self.status is not PbomVersionStatus.DRAFT:
            raise ImmutableVersionError(f"PBOM version {self.gid} is {self.status}")

    def transition(self, target: PbomVersionStatus) -> "PbomVersion":
        allowed = {
            PbomVersionStatus.DRAFT: {PbomVersionStatus.SUBMITTED, PbomVersionStatus.ARCHIVED},
            PbomVersionStatus.SUBMITTED: {PbomVersionStatus.PUBLISHED, PbomVersionStatus.DRAFT},
            PbomVersionStatus.PUBLISHED: {PbomVersionStatus.ARCHIVED},
            PbomVersionStatus.ARCHIVED: set(),
        }
        if target not in allowed[self.status]:
            raise InvalidLifecycleTransition(f"{self.status}->{target}")
        return PbomVersion(**{**self.__dict__, "status": target, "revision": self.revision + 1})


__all__ = ["ImmutableVersionError", "InvalidLifecycleTransition", "PbomVersion", "PbomVersionStatus"]
