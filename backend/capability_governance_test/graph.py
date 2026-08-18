"""Deterministic, in-memory view of a scanned implementation graph."""
from __future__ import annotations

from collections import defaultdict, deque
from pathlib import PurePosixPath
from typing import Iterable

from .models import CapabilityBinding, ImplementationNode, ImplementationRelation


def node_key(node_type: str, owner: str, path: str, symbol: str = "") -> str:
    """Return the portable immutable identity for an implementation node."""
    return f"{node_type}:{owner}:{PurePosixPath(path)}:{symbol}"


class ImplementationGraph:
    """Read-only traversal helper; the persisted records remain the authority."""

    def __init__(
        self,
        nodes: Iterable[ImplementationNode],
        relations: Iterable[ImplementationRelation],
        bindings: Iterable[CapabilityBinding],
    ) -> None:
        self.nodes = {node.canonical_key: node for node in nodes}
        self.relations = tuple(relations)
        self.bindings = tuple(bindings)
        adjacent: dict[str, set[str]] = defaultdict(set)
        for relation in self.relations:
            if relation.from_canonical_key in self.nodes and relation.to_canonical_key in self.nodes:
                adjacent[relation.from_canonical_key].add(relation.to_canonical_key)
        self._adjacent = {key: tuple(sorted(value)) for key, value in adjacent.items()}

    def has_path(self, capability: str, node_types: list[str]) -> bool:
        """Return whether the capability has an exact typed implementation path."""
        if not node_types or "@" not in capability:
            return False
        capability_id, raw_major = capability.rsplit("@", 1)
        try:
            major = int(raw_major)
        except ValueError:
            return False
        starts = sorted(
            binding.node_canonical_key
            for binding in self.bindings
            if binding.capability_id == capability_id
            and binding.major_version == major
            and binding.node_canonical_key in self.nodes
            and self.nodes[binding.node_canonical_key].node_type == node_types[0]
        )
        wanted = tuple(node_types)
        for start in starts:
            queue: deque[tuple[str, int]] = deque(((start, 1),))
            visited = {(start, 1)}
            while queue:
                current, position = queue.popleft()
                if position == len(wanted):
                    return True
                for target in self._adjacent.get(current, ()):
                    state = (target, position + 1)
                    if state in visited or self.nodes[target].node_type != wanted[position]:
                        continue
                    visited.add(state)
                    queue.append(state)
        return False


__all__ = ["ImplementationGraph", "node_key"]
