"""Neutral ownership extension point used by the Gateway composition root."""
from __future__ import annotations

from threading import RLock
from typing import Callable
from pathlib import Path

from backend.capability_v2.contracts import ConsumerIdentity


ResourceAuthorizer = Callable[[str, ConsumerIdentity], bool]


class ResourceAuthorizerRegistry:
    def __init__(self) -> None:
        self._authorizers: dict[str, ResourceAuthorizer] = {}
        self._identities: dict[str, tuple[str, str]] = {}
        self._lock = RLock()

    @staticmethod
    def _identity(authorizer: ResourceAuthorizer) -> tuple[str, str]:
        code = getattr(authorizer, "__code__", None)
        source = Path(code.co_filename).resolve().as_posix() if code is not None else type(authorizer).__module__
        name = getattr(authorizer, "__qualname__", type(authorizer).__qualname__)
        return source.casefold(), name

    def register(self, resource_type: str, authorizer: ResourceAuthorizer) -> None:
        if not resource_type or ":" in resource_type:
            raise ValueError("invalid resource type")
        with self._lock:
            identity = self._identity(authorizer)
            existing_identity = self._identities.get(resource_type)
            if existing_identity is not None and existing_identity != identity:
                raise ValueError(f"resource authorizer already registered: {resource_type}")
            self._authorizers[resource_type] = authorizer
            self._identities[resource_type] = identity

    def authorize(self, resource_ref: str, identity: ConsumerIdentity) -> bool:
        resource_type, separator, resource_id = resource_ref.partition(":")
        if not separator or not resource_id:
            return False
        with self._lock:
            authorizer = self._authorizers.get(resource_type)
        return bool(authorizer and authorizer(resource_id, identity))


resource_authorizers = ResourceAuthorizerRegistry()

__all__ = ["ResourceAuthorizerRegistry", "resource_authorizers"]
