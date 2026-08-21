"""Deterministic BOP execution-structure projection owned by Craft."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable, Mapping

from backend.capability_v2.provider_contracts import CapabilityBusinessError
from backend.contracts import CraftExecutionStructureV1

from ..data.connection import get_craft_conn


@dataclass(frozen=True)
class BopAggregate:
    version: Mapping[str, Any]
    entries: tuple[Mapping[str, Any], ...]
    links: tuple[Mapping[str, Any], ...]


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return dict(decoded) if isinstance(decoded, Mapping) else {}
    return {}


def _json_array(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str) and value.strip():
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return []
        return list(decoded) if isinstance(decoded, list) else []
    return []


def _transport(value: Any) -> Any:
    return value.isoformat() if isinstance(value, (datetime, date)) else value


def _revision(version: Mapping[str, Any]) -> int:
    value = version.get("revision")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise CapabilityBusinessError(
            "bop_revision_unavailable",
            "BOP version has no authoritative revision",
            details={"version_gid": version.get("gid")},
        )
    return value


class ExecutionStructureRepository:
    def load_bop_aggregate(
        self,
        version_gid: str,
        *,
        expected_revision: int | None = None,
    ) -> BopAggregate:
        with get_craft_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT gid, project_gid, revision, status, lifecycle_phase, "
                    "published_at, updated_at, version_tag, bop_name "
                    "FROM workmanship_bop_bop_versions "
                    "WHERE gid = %s AND is_deleted = 0",
                    (version_gid,),
                )
                version_row = cursor.fetchone()
                if not version_row:
                    raise CapabilityBusinessError(
                        "bop_version_not_found",
                        "BOP version not found",
                        details={"version_gid": version_gid},
                    )
                version = dict(version_row)
                current_revision = _revision(version)
                if expected_revision is not None and expected_revision != current_revision:
                    raise CapabilityBusinessError(
                        "revision_conflict",
                        "BOP revision does not match expected_revision",
                        details={
                            "version_gid": version_gid,
                            "expected_revision": expected_revision,
                            "current_revision": current_revision,
                        },
                    )

                cursor.execute(
                    "SELECT gid, parent_gid, node_type, sort_order, title, vpps, "
                    "vpps_desc, owner_gid, meta, created_at, updated_at "
                    "FROM workmanship_bop_bop_entries "
                    "WHERE version_gid = %s AND is_deleted = 0",
                    (version_gid,),
                )
                entries = tuple(dict(row) for row in cursor.fetchall())

                cursor.execute(
                    "SELECT l.gid AS link_gid, l.entry_gid, l.link_type, l.entity_gid, l.is_primary, "
                    "l.snapshot_data, p.part_no, p.title AS part_name, p.parent_gid, "
                    "p.quantity, p.unit, p.snapshot_gid, p.material, p.meta, p.created_at, p.updated_at, "
                    "p.vpps, p.parent_part_gid, p.node_type, p.bom_row_id, p.seq_no, p.part_number "
                    "FROM workmanship_bop_bop_entry_links l "
                    "LEFT JOIN workmanship_bop_pbom p "
                    "ON l.link_type = 'pbom_part' AND p.gid = l.entity_gid "
                    "WHERE l.version_gid = %s AND l.is_deleted = 0",
                    (version_gid,),
                )
                links: list[dict[str, Any]] = []
                for raw in cursor.fetchall():
                    link = dict(raw)
                    entity_data = _json_object(link.pop("snapshot_data", None))
                    if link.get("link_type") == "pbom_part":
                        entity_data.update(
                            {
                                key: link.pop(key)
                                for key in (
                                    "part_no", "part_name", "parent_gid", "quantity", "unit",
                                    "snapshot_gid", "material", "meta", "created_at", "updated_at",
                                    "vpps", "parent_part_gid", "node_type", "bom_row_id", "seq_no", "part_number",
                                )
                                if link.get(key) is not None
                            }
                        )
                        if "part_name" in entity_data:
                            entity_data["name"] = entity_data.pop("part_name")
                        if "meta" in entity_data:
                            entity_data["meta"] = _json_object(entity_data["meta"])
                        if "created_at" in entity_data:
                            entity_data["created_at"] = _transport(entity_data["created_at"])
                    link["entity_data"] = entity_data
                    links.append(link)

        return BopAggregate(version=version, entries=entries, links=tuple(links))


repository = ExecutionStructureRepository()


def _sort_value(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _ordered_entries(entries: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    materialized = [dict(item) for item in entries]
    ids = {str(item.get("gid")) for item in materialized}
    children: dict[str | None, list[Mapping[str, Any]]] = {}
    for item in materialized:
        parent = item.get("parent_gid")
        parent_key = str(parent) if parent is not None and str(parent) in ids else None
        children.setdefault(parent_key, []).append(item)
    for group in children.values():
        group.sort(key=lambda item: (_sort_value(item.get("sort_order")), str(item.get("gid"))))

    ordered: list[Mapping[str, Any]] = []
    visited: set[str] = set()

    def visit(parent_gid: str | None) -> None:
        for item in children.get(parent_gid, []):
            gid = str(item["gid"])
            if gid in visited:
                continue
            visited.add(gid)
            ordered.append(item)
            visit(gid)

    visit(None)
    for item in sorted(
        materialized,
        key=lambda value: (_sort_value(value.get("sort_order")), str(value.get("gid"))),
    ):
        if str(item["gid"]) not in visited:
            ordered.append(item)
    return ordered


def _operation_kind(node_type: Any) -> str | None:
    value = str(node_type or "").lower()
    if value in {"operation", "bop_operation", "bop_steps", "step"}:
        return "step" if "step" in value else "operation"
    if value in {"process", "bop_process"}:
        return "process"
    return None


def _ref(prefix: str, value: Any) -> str:
    return f"{prefix}:{value}"


def _normalize(aggregate: BopAggregate) -> dict[str, Any]:
    ordered = _ordered_entries(aggregate.entries)
    entry_by_gid = {str(item["gid"]): item for item in ordered}
    links_by_entry: dict[str, list[Mapping[str, Any]]] = {}
    for link in sorted(
        aggregate.links,
        key=lambda item: (
            str(item.get("entry_gid")),
            str(item.get("link_type")),
            str(item.get("entity_gid")),
        ),
    ):
        links_by_entry.setdefault(str(link.get("entry_gid")), []).append(link)

    nodes: list[dict[str, Any]] = []
    operations: list[dict[str, Any]] = []
    previous_by_parent: dict[str | None, str] = {}
    conditions: list[dict[str, Any]] = []

    for index, entry in enumerate(ordered, start=1):
        gid = str(entry["gid"])
        parent_gid = str(entry["parent_gid"]) if entry.get("parent_gid") else None
        node_links = links_by_entry.get(gid, [])
        refs: dict[str, list[str]] = {
            "part_refs": [],
            "tool_refs": [],
            "fixture_refs": [],
            "equipment_refs": [],
            "knowledge_refs": [],
            "rule_refs": [],
        }
        for link in node_links:
            link_type = str(link.get("link_type") or "")
            entity_gid = link.get("entity_gid")
            if not entity_gid:
                continue
            if link_type == "pbom_part":
                refs["part_refs"].append(_ref("part", entity_gid))
            elif link_type in {"project_tools", "physical_tool", "tool"}:
                refs["tool_refs"].append(_ref("tool", entity_gid))
            elif link_type in {"project_tooling", "physical_fixture", "fixture"}:
                refs["fixture_refs"].append(_ref("fixture", entity_gid))
            elif link_type in {"project_equipment", "physical_equipment", "equipment"}:
                refs["equipment_refs"].append(_ref("equipment", entity_gid))
            elif link_type in {"knowledge", "knowledge_revision", "knowledge_document"}:
                refs["knowledge_refs"].append(_ref("knowledge", entity_gid))
            elif link_type in {"rule", "policy", "rule_ref"}:
                refs["rule_refs"].append(_ref("rule", entity_gid))
        refs = {name: sorted(set(values)) for name, values in refs.items()}
        meta = _json_object(entry.get("meta"))
        nodes.append(
            {
                "node_id": gid,
                "parent_id": parent_gid,
                "kind": str(entry.get("node_type") or "unknown"),
                "sequence": index * 10,
                "name": str(entry.get("title") or gid),
                "vpps": entry.get("vpps"),
                **refs,
            }
        )
        for raw_condition in _json_array(meta.get("conditions")):
            conditions.append({"node_id": gid, "condition": raw_condition})

        operation_kind = _operation_kind(entry.get("node_type"))
        if operation_kind is None:
            continue
        explicit = [
            str(item)
            for item in _json_array(meta.get("predecessor_ids"))
            if isinstance(item, str) and item
        ]
        predecessor_ids = explicit
        if not predecessor_ids and parent_gid in previous_by_parent:
            predecessor_ids = [previous_by_parent[parent_gid]]
        previous_by_parent[parent_gid] = gid
        resource_refs = sorted(
            refs["tool_refs"] + refs["fixture_refs"] + refs["equipment_refs"]
        )
        operations.append(
            {
                "operation_id": gid,
                "sequence": len(operations) * 10 + 10,
                "kind": operation_kind,
                "name": str(entry.get("title") or gid),
                "predecessor_ids": sorted(set(predecessor_ids)),
                "resource_refs": resource_refs,
                "model_refs": [],
                "part_refs": refs["part_refs"],
                "knowledge_refs": refs["knowledge_refs"],
                "rule_refs": refs["rule_refs"],
                "parameters": {"parent_node_id": parent_gid, "vpps": entry.get("vpps")},
            }
        )

    operation_ids = {item["operation_id"] for item in operations}
    for operation in operations:
        operation["predecessor_ids"] = [
            value for value in operation["predecessor_ids"] if value in operation_ids
        ]
    dependencies = [
        {"from": predecessor, "to": operation["operation_id"], "kind": "finish_to_start"}
        for operation in operations
        for predecessor in operation["predecessor_ids"]
    ]
    version = aggregate.version
    project_gid = version.get("project_gid")
    if not isinstance(project_gid, str) or not project_gid:
        raise CapabilityBusinessError(
            "bop_project_unassigned",
            "BOP version is not assigned to a project",
            details={"version_gid": version.get("gid")},
        )
    return {
        "source": {
            "bop_version_gid": str(version["gid"]),
            "project_gid": project_gid,
            "revision": _revision(version),
        },
        "published_at": str(
            _transport(version.get("published_at") or version.get("updated_at") or "unknown")
        ),
        "nodes": nodes,
        "operations": operations,
        "dependencies": dependencies,
        "conditions": sorted(
            conditions,
            key=lambda item: (item["node_id"], json.dumps(item["condition"], sort_keys=True)),
        ),
    }


def build_execution_structure(
    version_gid: str,
    *,
    expected_revision: int | None,
    preview: bool,
) -> dict[str, Any]:
    aggregate = repository.load_bop_aggregate(
        version_gid,
        expected_revision=expected_revision,
    )
    current_revision = _revision(aggregate.version)
    if expected_revision is not None and current_revision != expected_revision:
        raise CapabilityBusinessError(
            "revision_conflict",
            "BOP revision does not match expected_revision",
            details={
                "version_gid": version_gid,
                "expected_revision": expected_revision,
                "current_revision": current_revision,
            },
        )
    if not preview and not aggregate.version.get("published_at"):
        raise CapabilityBusinessError(
            "version_not_published",
            "BOP version is not published",
            details={"version_gid": version_gid},
        )
    return CraftExecutionStructureV1.from_normalized(
        _normalize(aggregate),
        official=not preview,
    )


def linked_parts(aggregate: BopAggregate) -> list[dict[str, Any]]:
    entries = {str(item["gid"]): item for item in aggregate.entries}
    grouped: dict[str, dict[str, Any]] = {}
    for link in aggregate.links:
        if link.get("link_type") != "pbom_part" or not link.get("entity_gid"):
            continue
        part_gid = str(link["entity_gid"])
        data = _json_object(link.get("entity_data"))
        item = grouped.setdefault(
            part_gid,
            {
                "part_gid": part_gid,
                "part_no": data.get("part_no"),
                "name": data.get("name") or data.get("title"),
                "usage": [],
            },
        )
        entry_gid = str(link.get("entry_gid"))
        entry = entries.get(entry_gid, {})
        item["usage"].append(
            {"entry_gid": entry_gid, "entry_title": entry.get("title")}
        )
    for item in grouped.values():
        item["usage"].sort(key=lambda value: (value["entry_gid"], value.get("entry_title") or ""))
    return [grouped[key] for key in sorted(grouped)]


def legacy_linked_parts(aggregate: BopAggregate) -> list[dict[str, Any]]:
    """Project the historical one-row-per-primary-link response shape."""
    rows: list[dict[str, Any]] = []
    for link in aggregate.links:
        if link.get("link_type") != "pbom_part" or not link.get("entity_gid"):
            continue
        if link.get("is_primary") in {False, 0}:
            continue
        data = _json_object(link.get("entity_data"))
        rows.append(
            {
                "gid": str(link["entity_gid"]),
                "name": data.get("name") or data.get("title") or "",
                "parent_gid": data.get("parent_gid"),
                "part_no": data.get("part_no"),
                "quantity": data.get("quantity"),
                "unit": data.get("unit"),
                "snapshot_gid": data.get("snapshot_gid"),
                "material": data.get("material"),
                "meta": _json_object(data.get("meta")),
                "entry_gid": link.get("entry_gid"),
                "link_gid": link.get("link_gid"),
                "created_at": _transport(data.get("created_at")),
            }
        )
    return sorted(
        rows,
        key=lambda item: (
            str(item.get("part_no") or ""),
            str(item.get("gid") or ""),
            str(item.get("entry_gid") or ""),
        ),
    )


def legacy_pbom_items(aggregate: BopAggregate) -> list[dict[str, Any]]:
    """Project the historical version PBOM rows from the same aggregate."""
    rows: list[dict[str, Any]] = []
    for link in aggregate.links:
        if link.get("link_type") != "pbom_part" or not link.get("entity_gid"):
            continue
        data = _json_object(link.get("entity_data"))
        rows.append(
            {
                "gid": str(link["entity_gid"]),
                "title": data.get("name") or data.get("title"),
                "vpps": data.get("vpps"),
                "parent_part_gid": data.get("parent_part_gid"),
                "node_type": data.get("node_type"),
                "bom_row_id": data.get("bom_row_id"),
                "seq_no": data.get("seq_no"),
                "quantity": data.get("quantity"),
                "unit": data.get("unit"),
                "part_number": data.get("part_number"),
                "created_at": _transport(data.get("created_at")),
                "updated_at": _transport(data.get("updated_at")),
            }
        )
    return sorted(rows, key=lambda item: (item.get("seq_no") is None, item.get("seq_no") or 0, item["gid"]))


def project_work_package(
    aggregate: BopAggregate,
    *,
    scope_kind: str,
    scope_gid: str,
) -> dict[str, Any]:
    normalized = _normalize(aggregate)
    nodes = normalized["nodes"]
    by_parent: dict[str | None, list[str]] = {}
    for node in nodes:
        by_parent.setdefault(node.get("parent_id"), []).append(node["node_id"])

    selected: set[str] = set()
    if scope_kind in {"line", "station"}:
        pending = [scope_gid]
        while pending:
            node_gid = pending.pop()
            if node_gid in selected:
                continue
            selected.add(node_gid)
            pending.extend(by_parent.get(node_gid, []))
    else:
        selected = {
            str(link["entry_gid"])
            for link in aggregate.links
            if link.get("link_type") in {"project_role", "role"}
            and str(link.get("entity_gid")) == scope_gid
        }

    selected_nodes = [node for node in nodes if node["node_id"] in selected]
    operations = [
        operation
        for operation in normalized["operations"]
        if operation["operation_id"] in selected
    ]
    return {
        "version_gid": str(aggregate.version["gid"]),
        "revision": _revision(aggregate.version),
        "scope": {"kind": scope_kind, "gid": scope_gid},
        "work_items": operations,
        "parts": sorted({ref for node in selected_nodes for ref in node["part_refs"]}),
        "tools": sorted({ref for node in selected_nodes for ref in node["tool_refs"]}),
        "fixtures": sorted({ref for node in selected_nodes for ref in node["fixture_refs"]}),
        "equipment_requirements": sorted(
            {ref for node in selected_nodes for ref in node["equipment_refs"]}
        ),
        "knowledge_refs": sorted(
            {ref for node in selected_nodes for ref in node["knowledge_refs"]}
        ),
        "rule_refs": sorted({ref for node in selected_nodes for ref in node["rule_refs"]}),
    }
