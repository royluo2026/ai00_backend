"""Shared registry for bounded operational health providers."""
from __future__ import annotations

from typing import Protocol


class OperationsProvider(Protocol):
    owner: str

    def health(self, context: object) -> dict[str, object]: ...


class OperationsPortRegistry:
    def __init__(self) -> None:
        self.providers: dict[str, OperationsProvider] = {}

    def register(self, provider: OperationsProvider) -> None:
        self.providers[str(provider.owner)] = provider

    def get(self, owner: str) -> OperationsProvider | None:
        return self.providers.get(owner)

    def clear(self) -> None:
        self.providers.clear()


operations_registry = OperationsPortRegistry()

__all__ = ["OperationsPortRegistry", "OperationsProvider", "operations_registry"]
