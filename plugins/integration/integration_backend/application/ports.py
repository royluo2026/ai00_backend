"""Narrow owner-domain ports used by the Integration application boundary."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Protocol


class ResourceNotFound(RuntimeError):
    pass


class RevisionConflict(RuntimeError):
    pass


class IncompleteOperation(RuntimeError):
    pass


class CredentialEnrollmentPort(Protocol):
    def consume(self, handle: str, actor_gid: str, team_gid: str | None) -> str: ...


class CatalogResolverPort(Protocol):
    def require_stable(
        self, capability_id: str, major_version: int, minimum_release: str
    ) -> None: ...


class ConnectorRuntimePort(Protocol):
    async def test(
        self, connector: Mapping[str, Any], *, timeout_seconds: int, result_limit: int
    ) -> Mapping[str, Any]: ...

    async def discover(
        self, connector: Mapping[str, Any], *, timeout_seconds: int, result_limit: int
    ) -> Mapping[str, Any]: ...

    async def source_columns(
        self, connector: Mapping[str, Any], mapping: Mapping[str, Any], *,
        timeout_seconds: int, result_limit: int,
    ) -> Mapping[str, Any]: ...

    async def preview(
        self, connector: Mapping[str, Any], mapping: Mapping[str, Any], *,
        timeout_seconds: int, result_limit: int,
    ) -> Mapping[str, Any]: ...


class OperationIdentityPort(Protocol):
    def new_id(self, kind: str) -> str: ...

    def now(self) -> datetime: ...


class OperationPersistencePort(Protocol):
    def find_operation(
        self, owner_gid: str, capability_id: str, idempotency_key: str
    ) -> Any | None: ...

    def find_import_operation(
        self, owner_gid: str, capability_id: str, idempotency_key: str
    ) -> Any | None: ...

    def claim_operation(self, record: Any) -> tuple[Any, bool]: ...

    def claim_import_operation(self, record: Any, run: Mapping[str, Any]) -> tuple[Any, bool]: ...

    def get_operation(
        self, operation_id: str, owner_gid: str, team_gid: str | None
    ) -> Any | None: ...

    def transition_operation(
        self, operation_id: str, expected_version: int, replacement: Any,
        owner_gid: str, team_gid: str | None,
    ) -> Any: ...


__all__ = [
    "CatalogResolverPort",
    "ConnectorRuntimePort",
    "CredentialEnrollmentPort",
    "IncompleteOperation",
    "OperationIdentityPort",
    "OperationPersistencePort",
    "ResourceNotFound",
    "RevisionConflict",
]
