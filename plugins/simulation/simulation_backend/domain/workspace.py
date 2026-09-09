"""Pure aggregate for private Simulation workspace edits."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Callable, Literal

from backend.platform_sdk.ids import next_gid


class WorkspaceError(ValueError):
    pass


class WorkspaceConflict(WorkspaceError):
    pass


class WorkspaceRuleError(WorkspaceError):
    pass


@dataclass(frozen=True)
class WorkspaceNode:
    gid: str
    parent_gid: str | None
    node_type: str
    name: str
    position: int
    removed: bool = False


@dataclass(frozen=True)
class WorkspaceBinding:
    gid: str
    node_gid: str
    occurrence_gid: str
    role: Literal["load", "operate"]
    removed: bool = False


@dataclass(frozen=True)
class WorkspaceChange:
    entity_gid: str
    row_version: int
    patch: dict[str, object]


def _fingerprint(value: dict[str, object]) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


class SimulationWorkspace:
    def __init__(
        self,
        *,
        gid: str,
        tenant_gid: str,
        owner_gid: str,
        name: str,
        gid_factory: Callable[[], str | int],
    ) -> None:
        self.gid = gid
        self.tenant_gid = tenant_gid
        self.owner_gid = owner_gid
        self.name = name
        self.row_version = 1
        self.nodes: dict[str, WorkspaceNode] = {}
        self.bindings: dict[str, WorkspaceBinding] = {}
        self._gid_factory = gid_factory
        self._idempotency: dict[str, tuple[str, WorkspaceChange]] = {}

    @classmethod
    def create(
        cls,
        *,
        gid: str,
        tenant_gid: str,
        owner_gid: str,
        name: str,
        gid_factory: Callable[[], str | int] = next_gid,
    ) -> "SimulationWorkspace":
        if not name.strip():
            raise WorkspaceRuleError("workspace_name_required")
        return cls(
            gid=str(gid), tenant_gid=str(tenant_gid), owner_gid=str(owner_gid),
            name=name.strip(), gid_factory=gid_factory,
        )

    def _begin(
        self, *, key: str, payload: dict[str, object], expected: int
    ) -> WorkspaceChange | None:
        digest = _fingerprint(payload)
        replay = self._idempotency.get(key)
        if replay:
            if replay[0] != digest:
                raise WorkspaceConflict("idempotency_conflict")
            return replay[1]
        if expected != self.row_version:
            raise WorkspaceConflict("version_conflict")
        return None

    def _finish(self, *, key: str, payload: dict[str, object], result: WorkspaceChange) -> WorkspaceChange:
        self._idempotency[key] = (_fingerprint(payload), result)
        return result

    def _next_gid(self) -> str:
        value = str(self._gid_factory())
        if not value.isdecimal() or int(value) <= 0:
            raise WorkspaceRuleError("invalid_gid")
        return value

    def create_node(
        self,
        *,
        parent_gid: str | None,
        node_type: str,
        name: str,
        expected_row_version: int,
        idempotency_key: str,
    ) -> WorkspaceChange:
        payload = {"op": "create", "parent_gid": parent_gid, "node_type": node_type, "name": name.strip()}
        replay = self._begin(key=idempotency_key, payload=payload, expected=expected_row_version)
        if replay:
            return replay
        if parent_gid is not None and (parent_gid not in self.nodes or self.nodes[parent_gid].removed):
            raise WorkspaceRuleError("parent_not_found")
        if not name.strip() or node_type not in {"line", "station", "process", "operation"}:
            raise WorkspaceRuleError("invalid_structure_node")
        siblings = [item for item in self.nodes.values() if item.parent_gid == parent_gid and not item.removed]
        node_gid = self._next_gid()
        node = WorkspaceNode(node_gid, parent_gid, node_type, name.strip(), len(siblings))
        self.nodes[node_gid] = node
        self.row_version += 1
        result = WorkspaceChange(
            node_gid, self.row_version,
            {"op": "create", "node_gid": node_gid, "parent_gid": parent_gid, "position": node.position},
        )
        return self._finish(key=idempotency_key, payload=payload, result=result)

    def move_node(
        self,
        *,
        node_gid: str,
        new_parent_gid: str | None,
        expected_row_version: int,
        idempotency_key: str,
    ) -> WorkspaceChange:
        payload = {"op": "move", "node_gid": node_gid, "parent_gid": new_parent_gid}
        replay = self._begin(key=idempotency_key, payload=payload, expected=expected_row_version)
        if replay:
            return replay
        node = self.nodes.get(node_gid)
        if node is None or node.removed:
            raise WorkspaceRuleError("structure_node_not_found")
        if new_parent_gid is not None and (
            new_parent_gid not in self.nodes or self.nodes[new_parent_gid].removed
        ):
            raise WorkspaceRuleError("parent_not_found")
        current = new_parent_gid
        while current is not None:
            if current == node_gid:
                raise WorkspaceRuleError("structure_cycle")
            current = self.nodes[current].parent_gid
        self.nodes[node_gid] = WorkspaceNode(
            node.gid, new_parent_gid, node.node_type, node.name,
            len([item for item in self.nodes.values() if item.parent_gid == new_parent_gid and not item.removed]),
        )
        self.row_version += 1
        result = WorkspaceChange(
            node_gid, self.row_version,
            {"op": "move", "node_gid": node_gid, "parent_gid": new_parent_gid},
        )
        return self._finish(key=idempotency_key, payload=payload, result=result)

    def remove_node(
        self,
        *,
        node_gid: str,
        expected_row_version: int,
        idempotency_key: str,
    ) -> WorkspaceChange:
        payload = {"op": "remove", "node_gid": node_gid}
        replay = self._begin(key=idempotency_key, payload=payload, expected=expected_row_version)
        if replay:
            return replay
        if node_gid not in self.nodes or self.nodes[node_gid].removed:
            raise WorkspaceRuleError("structure_node_not_found")
        removed = {node_gid}
        changed = True
        while changed:
            before = len(removed)
            removed.update(
                item.gid for item in self.nodes.values()
                if not item.removed and item.parent_gid in removed
            )
            changed = len(removed) != before
        for gid in removed:
            node = self.nodes[gid]
            self.nodes[gid] = WorkspaceNode(
                node.gid, node.parent_gid, node.node_type, node.name, node.position, True
            )
        for gid, binding in tuple(self.bindings.items()):
            if binding.node_gid in removed and not binding.removed:
                self.bindings[gid] = WorkspaceBinding(
                    binding.gid, binding.node_gid, binding.occurrence_gid, binding.role, True
                )
        self.row_version += 1
        result = WorkspaceChange(
            node_gid, self.row_version,
            {"op": "remove", "removed_node_gids": tuple(sorted(removed, key=int))},
        )
        return self._finish(key=idempotency_key, payload=payload, result=result)

    def create_binding(
        self,
        *,
        node_gid: str,
        occurrence_gid: str,
        role: Literal["load", "operate"],
        expected_row_version: int,
        idempotency_key: str,
    ) -> WorkspaceChange:
        payload = {"op": "bind", "node_gid": node_gid, "occurrence_gid": occurrence_gid, "role": role}
        replay = self._begin(key=idempotency_key, payload=payload, expected=expected_row_version)
        if replay:
            return replay
        if node_gid not in self.nodes or self.nodes[node_gid].removed:
            raise WorkspaceRuleError("structure_node_not_found")
        if role not in {"load", "operate"}:
            raise WorkspaceRuleError("invalid_binding_role")
        if role == "load" and any(
            item.occurrence_gid == occurrence_gid and item.role == "load" and not item.removed
            for item in self.bindings.values()
        ):
            raise WorkspaceRuleError("load_binding_exists")
        binding_gid = self._next_gid()
        self.bindings[binding_gid] = WorkspaceBinding(binding_gid, node_gid, occurrence_gid, role)
        self.row_version += 1
        result = WorkspaceChange(
            binding_gid, self.row_version,
            {"op": "bind", "binding_gid": binding_gid, "node_gid": node_gid, "occurrence_gid": occurrence_gid, "role": role},
        )
        return self._finish(key=idempotency_key, payload=payload, result=result)


__all__ = [
    "SimulationWorkspace", "WorkspaceBinding", "WorkspaceChange", "WorkspaceConflict",
    "WorkspaceError", "WorkspaceNode", "WorkspaceRuleError",
]
