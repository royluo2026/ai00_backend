"""Machine-readable domain and database ownership governance."""

from .ownership import DomainRegistry, OwnershipError, load_registry

__all__ = ["DomainRegistry", "OwnershipError", "load_registry"]
