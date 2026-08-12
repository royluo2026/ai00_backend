from __future__ import annotations

from dataclasses import asdict
from typing import Any, Protocol

from ..domain.pbom import PbomVersion, PbomVersionStatus


class PbomRepositoryPort(Protocol):
    def get_version(self, version_gid: str) -> PbomVersion | None: ...
    def replace_part(self, version_gid: str, part: dict[str, Any]) -> dict[str, Any]: ...
    def set_status(self, version_gid: str, status: PbomVersionStatus, expected_revision: int) -> PbomVersion: ...


class PbomNotFound(ValueError):
    pass


class PbomService:
    def __init__(self, repository: PbomRepositoryPort):
        self.repository = repository

    def get(self, version_gid: str) -> PbomVersion:
        version = self.repository.get_version(version_gid)
        if version is None:
            raise PbomNotFound(version_gid)
        return version

    def change_part(self, version_gid: str, part: dict[str, Any]) -> dict[str, Any]:
        version = self.get(version_gid)
        version.require_mutable()
        return self.repository.replace_part(version_gid, part)

    def transition(self, version_gid: str, target: PbomVersionStatus) -> dict[str, Any]:
        current = self.get(version_gid)
        changed = current.transition(target)
        stored = self.repository.set_status(version_gid, target, current.revision)
        return asdict(stored if stored else changed)


__all__ = ["PbomNotFound", "PbomRepositoryPort", "PbomService"]
