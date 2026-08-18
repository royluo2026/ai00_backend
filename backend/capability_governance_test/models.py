"""Immutable records used by the test-only Capability Governance Center."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from backend.utils.gid import gid_to_json


class ImmutableRecordError(RuntimeError):
    """Raised when an immutable governance record would be changed."""


def _frozen_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(value))


@dataclass(frozen=True)
class ScannedCapability:
    capability_id: str
    major_version: int
    owner_domain: str
    semantic_class: str
    business_effect: str
    lifecycle_status: str
    descriptor_hash: str
    input_schema_hash: str
    output_schema_hash: str
    error_schema_hash: str
    policy_hash: str
    provider_hash: str
    descriptor: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "descriptor", _frozen_mapping(self.descriptor))

    def to_json(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "major_version": self.major_version,
            "owner_domain": self.owner_domain,
            "semantic_class": self.semantic_class,
            "business_effect": self.business_effect,
            "lifecycle_status": self.lifecycle_status,
            "descriptor_hash": self.descriptor_hash,
            "input_schema_hash": self.input_schema_hash,
            "output_schema_hash": self.output_schema_hash,
            "error_schema_hash": self.error_schema_hash,
            "policy_hash": self.policy_hash,
            "provider_hash": self.provider_hash,
            "descriptor": dict(self.descriptor),
        }


@dataclass(frozen=True)
class ImplementationNode:
    canonical_key: str
    owner_domain: str
    node_type: str
    source_path: str
    artifact_hash: str
    source_symbol: str | None = None
    http_method: str | None = None
    route_path: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _frozen_mapping(self.metadata))

    def to_json(self) -> dict[str, Any]:
        return {
            "canonical_key": self.canonical_key, "owner_domain": self.owner_domain,
            "node_type": self.node_type, "source_path": self.source_path,
            "artifact_hash": self.artifact_hash, "source_symbol": self.source_symbol,
            "http_method": self.http_method, "route_path": self.route_path,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class CapabilityBinding:
    capability_id: str
    major_version: int
    node_canonical_key: str
    binding_type: str
    binding_hash: str


@dataclass(frozen=True)
class ImplementationRelation:
    from_canonical_key: str
    to_canonical_key: str
    relation_type: str
    relation_hash: str


@dataclass(frozen=True)
class CapabilityProjection:
    capability_gid: int
    capability_version_gid: int
    capability_id: str
    major_version: int
    owner_domain: str
    semantic_class: str
    business_effect: str
    lifecycle_status: str
    descriptor_hash: str

    def to_json(self) -> dict[str, Any]:
        return {
            "capability_gid": gid_to_json(self.capability_gid),
            "capability_version_gid": gid_to_json(self.capability_version_gid),
            "capability_id": self.capability_id,
            "major_version": self.major_version,
            "owner_domain": self.owner_domain,
            "semantic_class": self.semantic_class,
            "business_effect": self.business_effect,
            "lifecycle_status": self.lifecycle_status,
            "descriptor_hash": self.descriptor_hash,
        }


@dataclass(frozen=True)
class SnapshotDocument:
    product_release_id: str
    extension_release_id: str | None
    code_revision: str
    snapshot_hash: str
    capabilities: tuple[ScannedCapability, ...]
    nodes: tuple[ImplementationNode, ...]
    bindings: tuple[CapabilityBinding, ...]
    relations: tuple[ImplementationRelation, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "product_release_id": self.product_release_id,
            "extension_release_id": self.extension_release_id,
            "code_revision": self.code_revision,
            "snapshot_hash": self.snapshot_hash,
            "capabilities": [item.to_json() for item in self.capabilities],
            "nodes": [item.to_json() for item in self.nodes],
            "bindings": [item.__dict__.copy() for item in self.bindings],
            "relations": [item.__dict__.copy() for item in self.relations],
        }


@dataclass(frozen=True)
class SnapshotEntry(CapabilityProjection):
    snapshot_entry_gid: int

    def to_json(self) -> dict[str, Any]:
        return {**super().to_json(), "snapshot_entry_gid": gid_to_json(self.snapshot_entry_gid)}


@dataclass(frozen=True)
class SnapshotRecord:
    snapshot_gid: int
    scan_run_gid: int
    document: SnapshotDocument
    entries: tuple[SnapshotEntry, ...]
    node_gids: Mapping[str, int] = field(default_factory=dict)
    binding_gids: tuple[int, ...] = ()
    relation_gids: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_gids", _frozen_mapping(self.node_gids))

    def to_json(self) -> dict[str, Any]:
        return {
            "snapshot_gid": gid_to_json(self.snapshot_gid),
            "scan_run_gid": gid_to_json(self.scan_run_gid),
            "document": self.document.to_json(),
            "entries": [entry.to_json() for entry in self.entries],
            "node_gids": {key: gid_to_json(value) for key, value in self.node_gids.items()},
            "binding_gids": [gid_to_json(value) for value in self.binding_gids],
            "relation_gids": [gid_to_json(value) for value in self.relation_gids],
        }


__all__ = [
    "CapabilityBinding", "CapabilityProjection", "ImplementationNode", "ImplementationRelation",
    "ImmutableRecordError", "ScannedCapability", "SnapshotDocument", "SnapshotEntry", "SnapshotRecord",
]
