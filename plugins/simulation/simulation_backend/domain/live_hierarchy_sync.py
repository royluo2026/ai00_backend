"""Pure, conservative three-way reconciliation for one bound AH observation.

No persistence, authorization, native calls or CPS mutation occurs here. Providers
must supply scoped, complete observations after their own version/permission checks.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass


class SyncValidationError(ValueError):
    pass


@dataclass(frozen=True)
class HierarchyNode:
    node_id: str
    parent_id: str | None
    name: str
    source_identity: str | None = None
    position: int = 0
    insertion_instance_id: str | None = None
    occurrence_id: str | None = None


@dataclass(frozen=True)
class HierarchySnapshot:
    environment_id: str
    document_session: str
    complete: bool
    nodes: tuple[HierarchyNode, ...]


@dataclass(frozen=True)
class SyncConflict:
    node_id: str
    reason: str
    base: HierarchyNode | None
    desired: HierarchyNode | None
    observed: HierarchyNode | None


@dataclass(frozen=True)
class Reconciliation:
    nodes: tuple[HierarchyNode, ...] | None
    conflicts: tuple[SyncConflict, ...]


def _graph_errors(nodes: dict[str, HierarchyNode]) -> dict[str, str]:
    errors = {key: "parent_deleted" for key, node in nodes.items()
              if node.parent_id is not None and node.parent_id not in nodes}
    if errors:
        return errors
    children: dict[str, list[str]] = {}
    roots = deque()
    for key, node in nodes.items():
        if node.parent_id is None:
            roots.append(key)
        else:
            children.setdefault(node.parent_id, []).append(key)
    visited: set[str] = set()
    while roots:
        key = roots.popleft()
        visited.add(key)
        roots.extend(children.get(key, ()))
    return {key: "merged_cycle" for key in nodes if key not in visited}


def _index(snapshot: HierarchySnapshot) -> dict[str, HierarchyNode]:
    if snapshot.complete is not True:
        raise SyncValidationError("hierarchy_observation_incomplete")
    return validate_hierarchy_nodes(snapshot.nodes)


def validate_hierarchy_nodes(nodes: tuple[HierarchyNode, ...]) -> dict[str, HierarchyNode]:
    """Validate structure without asserting that a native observation is complete."""
    if not isinstance(nodes, tuple) or len(nodes) > 1_000_000:
        raise SyncValidationError("hierarchy_nodes_invalid")
    result: dict[str, HierarchyNode] = {}
    for node in nodes:
        if not isinstance(node, HierarchyNode):
            raise SyncValidationError("hierarchy_node_invalid")
        if not isinstance(node.node_id, str) or not node.node_id or len(node.node_id) > 1024:
            raise SyncValidationError("hierarchy_identity_invalid")
        if node.parent_id is not None and (not isinstance(node.parent_id, str) or not node.parent_id):
            raise SyncValidationError("hierarchy_parent_invalid")
        if not isinstance(node.name, str) or len(node.name) > 16384:
            raise SyncValidationError("hierarchy_name_invalid")
        # A shared artifact/source is not an inserted instance. All three parts
        # are required; a source-only legacy link needs explicit reconciliation.
        reference = (node.source_identity, node.insertion_instance_id, node.occurrence_id)
        if any(value is not None for value in reference):
            if any(value is None for value in reference):
                raise SyncValidationError("hierarchy_reference_incomplete")
            if any(not isinstance(value, str) or not value.strip() or len(value) > 4096
                   for value in reference):
                raise SyncValidationError("hierarchy_reference_invalid")
        if type(node.position) is not int or node.position < 0:
            raise SyncValidationError("hierarchy_position_invalid")
        if node.node_id in result:
            raise SyncValidationError("hierarchy_identity_duplicate")
        result[node.node_id] = node
    if _graph_errors(result):
        raise SyncValidationError("hierarchy_graph_invalid")
    return result


def reconcile(base: HierarchySnapshot, desired: HierarchySnapshot,
              observed: HierarchySnapshot) -> Reconciliation:
    """Merge whole-node changes. Conflicts never yield a partially usable tree.

    Runtime observations are session-bound. Restoring a prior session must first
    resolve stable identities into a fresh, verified baseline outside this function.
    """
    scope = (base.environment_id, base.document_session)
    if any(not isinstance(value, str) or not value for value in scope):
        raise SyncValidationError("hierarchy_scope_invalid")
    if any((s.environment_id, s.document_session) != scope for s in (desired, observed)):
        raise SyncValidationError("hierarchy_scope_changed")
    b, a, v = (_index(s) for s in (base, desired, observed))
    merged: dict[str, HierarchyNode] = {}
    conflicts: list[SyncConflict] = []
    for key in sorted(b.keys() | a.keys() | v.keys()):
        before, local, remote = b.get(key), a.get(key), v.get(key)
        if local == remote:
            chosen = local
        elif local == before:
            chosen = remote
        elif remote == before:
            chosen = local
        else:
            conflicts.append(SyncConflict(key, "concurrent_change", before, local, remote))
            continue
        if chosen is not None:
            merged[key] = chosen
    if conflicts:
        return Reconciliation(None, tuple(conflicts))
    for key, reason in sorted(_graph_errors(merged).items()):
        conflicts.append(SyncConflict(key, reason, b.get(key), a.get(key), v.get(key)))
    return Reconciliation(None if conflicts else tuple(merged.values()), tuple(conflicts))
