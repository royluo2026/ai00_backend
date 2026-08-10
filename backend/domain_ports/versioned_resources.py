"""Shared composition port for resolving immutable cross-domain resources."""
from __future__ import annotations

from threading import RLock
from typing import Any, Callable, Mapping


Resolver = Callable[[Mapping[str, Any], Any], Mapping[str, Any]]


class VersionedResourceResolvers:
    """Fail-closed resolver registry populated by resource-owning providers."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._resolvers: dict[str, Resolver] = {}

    def register(self, resource_type: str, resolver: Resolver) -> None:
        if not resource_type or not callable(resolver):
            raise ValueError("resource_type and resolver are required")
        with self._lock:
            current = self._resolvers.get(resource_type)
            if current is not None and current is not resolver:
                raise RuntimeError(f"versioned resource resolver already registered: {resource_type}")
            self._resolvers[resource_type] = resolver

    def resolve(self, resource_type: str, reference: Mapping[str, Any], context: Any) -> dict[str, Any]:
        with self._lock:
            resolver = self._resolvers.get(resource_type)
        if resolver is None:
            raise LookupError(f"versioned resource resolver unavailable: {resource_type}")
        return dict(resolver(reference, context))


versioned_resource_resolvers = VersionedResourceResolvers()

__all__ = ["VersionedResourceResolvers", "versioned_resource_resolvers"]
