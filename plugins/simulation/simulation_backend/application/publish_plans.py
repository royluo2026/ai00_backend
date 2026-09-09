"""Pure selective Simulation-to-Craft BOP publish planning."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Iterable, Mapping


@dataclass(frozen=True)
class BopPublishPlan:
    environment_version_gid: str
    environment_hash: str
    base_bop_version_gid: str
    base_bop_revision: int
    base_bop_hash: str
    selected_node_gids: tuple[str, ...]
    parent_closure_gids: tuple[str, ...]
    craft_preview_actions: tuple[dict[str, object], ...]
    binding_actions: tuple[dict[str, object], ...]
    plan_hash: str


def _hash(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def build_bop_publish_plan(
    *,
    environment_version_gid: str,
    environment_hash: str,
    base_bop_version_gid: str,
    base_bop_revision: int,
    base_bop_hash: str,
    nodes: Iterable[Mapping[str, object]],
    bindings: Iterable[Mapping[str, object]],
    selected_node_gids: Iterable[str],
) -> BopPublishPlan:
    by_gid = {str(item["node_gid"]): dict(item) for item in nodes}
    selected = tuple(dict.fromkeys(str(value) for value in selected_node_gids))
    if not selected:
        raise ValueError("publish_selection_required")
    if any(gid not in by_gid for gid in selected):
        raise ValueError("selected_node_not_found")

    closure: set[str] = set()
    for gid in selected:
        parent = by_gid[gid].get("parent_gid")
        seen = {gid}
        while parent is not None:
            parent_gid = str(parent)
            if parent_gid in seen:
                raise ValueError("structure_cycle")
            if parent_gid not in by_gid:
                raise ValueError("parent_node_not_found")
            seen.add(parent_gid)
            closure.add(parent_gid)
            parent = by_gid[parent_gid].get("parent_gid")

    included = set(selected) | closure

    def depth(gid: str) -> int:
        value = 0
        parent = by_gid[gid].get("parent_gid")
        while parent is not None:
            value += 1
            parent = by_gid[str(parent)].get("parent_gid")
        return value

    ordered = sorted(
        included,
        key=lambda gid: (depth(gid), int(by_gid[gid].get("position") or 0), gid),
    )
    actions: list[dict[str, object]] = []
    for gid in ordered:
        node = by_gid[gid]
        if node.get("source_bop_node_gid"):
            continue
        parent_gid = str(node["parent_gid"]) if node.get("parent_gid") is not None else None
        parent = by_gid.get(parent_gid) if parent_gid else None
        action: dict[str, object] = {
            "operation": "node.create",
            "client_ref": f"sim:{environment_version_gid}:{gid}",
            "source_node_gid": gid,
            "node_type": str(node.get("node_type") or ""),
            "name": str(node.get("name") or ""),
            "sort_order": int(node.get("position") or 0),
        }
        if parent is not None:
            if parent.get("source_bop_node_gid"):
                action["parent_bop_node_gid"] = str(parent["source_bop_node_gid"])
            else:
                action["parent_client_ref"] = f"sim:{environment_version_gid}:{parent_gid}"
        actions.append(action)

    binding_actions = tuple(
        {
            "client_ref": f"sim-binding:{environment_version_gid}:{binding['binding_gid']}",
            "node_client_ref": f"sim:{environment_version_gid}:{binding['node_gid']}",
            "occurrence_gid": str(binding["occurrence_gid"]),
            "role": str(binding["role"]),
        }
        for binding in sorted(bindings, key=lambda item: str(item["binding_gid"]))
        if str(binding["node_gid"]) in set(selected)
    )
    canonical = {
        "environment_version_gid": str(environment_version_gid),
        "environment_hash": str(environment_hash),
        "base_bop_version_gid": str(base_bop_version_gid),
        "base_bop_revision": int(base_bop_revision),
        "base_bop_hash": str(base_bop_hash),
        "selected_node_gids": selected,
        "parent_closure_gids": tuple(gid for gid in ordered if gid in closure),
        "craft_preview_actions": tuple(actions),
        "binding_actions": binding_actions,
    }
    return BopPublishPlan(**canonical, plan_hash=_hash(canonical))


__all__ = ["BopPublishPlan", "build_bop_publish_plan"]
