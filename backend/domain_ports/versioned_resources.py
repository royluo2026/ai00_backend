"""Shared composition port for resolving immutable cross-domain resources."""
from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Any, Callable, Mapping


Resolver = Callable[[Mapping[str, Any], Any], Mapping[str, Any]]


def _provider_identity(resolver: Resolver) -> tuple[str, str]:
    code = getattr(resolver, "__code__", None)
    source = Path(code.co_filename).resolve() if code is not None else None
    return (str(source or getattr(resolver, "__module__", "")), getattr(resolver, "__qualname__", ""))


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
            # The plugin loader can import one source package through both its
            # distribution name and repository package path.  Source identity
            # remains stable across that aliasing and Python module reloads.
            same_provider = current is not None and _provider_identity(current) == _provider_identity(resolver)
            if current is not None and current is not resolver and not same_provider:
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
