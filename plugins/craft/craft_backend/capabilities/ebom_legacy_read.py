"""Bounded read projections for legacy eBOM/PBOM comparison routes."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.provider_contracts import (
    CapabilityBusinessError,
    CapabilityContext,
    CapabilityOutput,
    CapabilitySpec,
)

from ..data.connection import get_craft_conn


OPERATIONS = ("diff",)
_MAX_ITEMS = 500
_CMP_FIELDS = (
    "name", "quantity", "unit", "material", "component_type",
    "component_version_status", "purchase_status", "torque",
    "torque_importance", "variable_formula", "vpps_desc", "parent_vpps",
    "parent_vpps_name", "bom_row", "bom_row_label", "ownership_user",
    "configuration", "parent_bom_row",
)
_FIELD_LABELS = {
    "name": "名称", "quantity": "数量", "unit": "单位", "material": "材料",
    "component_type": "类型", "component_version_status": "版本状态",
    "purchase_status": "采购状态", "torque": "扭矩", "torque_importance": "扭矩重要度",
    "variable_formula": "变量公式", "vpps_desc": "VPPS描述",
    "parent_vpps": "父级VPPS", "parent_vpps_name": "父级名称",
    "bom_row": "BOM行", "bom_row_label": "BOM行标签",
    "ownership_user": "所有权用户", "configuration": "配置",
    "parent_bom_row": "父级BOM行",
}


def _required_text(payload: dict[str, Any], name: str) -> str:
    value = str(payload.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _match_key(part: dict[str, Any]) -> str:
    bom = str(part.get("bom_row") or "").strip()
    component_id = str(part.get("component_id") or "").strip()
    vpps = str(part.get("vpps") or "").strip()
    part_no = str(part.get("part_no") or "").strip()
    if bom and component_id:
        return f"{bom}|{component_id}"
    if bom:
        return bom
    if vpps:
        return vpps
    if component_id:
        return component_id
    return part_no


def _norm(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return str(round(value, 6))
    return str(value).strip()


def _load_parts(cur: Any, snapshot_gid: str) -> list[dict[str, Any]]:
    columns = (
        "gid, part_no, title AS name, quantity, unit, material, vpps, vpps_desc, "
        "parent_vpps, parent_vpps_name, bom_row, bom_row_label, component_id, "
        "component_type, component_version_status, purchase_status, torque, "
        "torque_importance, variable_formula, ownership_user, configuration, "
        "parent_bom_row"
    )
    cur.execute(
        f"SELECT {columns} FROM workmanship_bop_pbom "
        "WHERE snapshot_gid=%s ORDER BY level, bom_row, part_no",
        (snapshot_gid,),
    )
    return [dict(row) for row in cur.fetchall()]


def _bounded(items: list[dict[str, Any]], *, label: str) -> None:
    if len(items) > _MAX_ITEMS:
        raise CapabilityBusinessError(
            "invalid_input",
            f"{label} exceeds the bounded response limit",
            details={"limit": _MAX_ITEMS, "count": len(items)},
        )


def diff_snapshots(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    if str(payload.get("operation") or "diff") not in OPERATIONS:
        raise ValueError("unsupported eBOM legacy read operation")
    base_gid = _required_text(payload, "base_gid")
    target_gid = _required_text(payload, "target_gid")

    with get_craft_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid, version_tag, name FROM workmanship_bop_pbom_versions WHERE gid=%s",
                (base_gid,),
            )
            base_version = cur.fetchone()
            if not base_version:
                raise CapabilityBusinessError("resource_not_found", f"base snapshot {base_gid} does not exist")
            cur.execute(
                "SELECT gid, version_tag, name FROM workmanship_bop_pbom_versions WHERE gid=%s",
                (target_gid,),
            )
            target_version = cur.fetchone()
            if not target_version:
                raise CapabilityBusinessError("resource_not_found", f"target snapshot {target_gid} does not exist")
            base_parts = _load_parts(cur, base_gid)
            target_parts = _load_parts(cur, target_gid)

    _bounded(base_parts, label="base snapshot parts")
    _bounded(target_parts, label="target snapshot parts")

    def build_map(parts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        counts: dict[str, int] = {}
        result: dict[str, dict[str, Any]] = {}
        for part in parts:
            key = _match_key(part)
            if not key:
                continue
            ordinal = counts.get(key, 0)
            counts[key] = ordinal + 1
            match_key = f"{key}#{ordinal}" if ordinal else key
            item = dict(part)
            item["_mk"] = match_key
            result[match_key] = item
        return result

    base_map = build_map(base_parts)
    target_map = build_map(target_parts)
    added = [
        {"match_key": key, "part_no": item.get("part_no", ""), "name": item.get("name", "")}
        for key, item in target_map.items() if key not in base_map
    ]
    deleted = [
        {"match_key": key, "part_no": item.get("part_no", ""), "name": item.get("name", "")}
        for key, item in base_map.items() if key not in target_map
    ]
    modified: list[dict[str, Any]] = []
    same_count = 0
    for key, target in target_map.items():
        base = base_map.get(key)
        if base is None:
            continue
        changes = [
            {
                "field": field,
                "label": _FIELD_LABELS.get(field, field),
                "from": _norm(base.get(field)) or "-",
                "to": _norm(target.get(field)) or "-",
            }
            for field in _CMP_FIELDS
            if _norm(base.get(field)) != _norm(target.get(field))
        ]
        if changes:
            modified.append(
                {
                    "match_key": key,
                    "part_no": target.get("part_no", ""),
                    "name": target.get("name", ""),
                    "changed_fields": changes,
                }
            )
        else:
            same_count += 1

    _bounded(added, label="added changes")
    _bounded(deleted, label="deleted changes")
    _bounded(modified, label="modified changes")
    return CapabilityOutput(
        data={
            "base": {
                "gid": base_gid,
                "version_tag": base_version["version_tag"],
                "name": base_version["name"] or "",
            },
            "target": {
                "gid": target_gid,
                "version_tag": target_version["version_tag"],
                "name": target_version["name"] or "",
            },
            "summary": {
                "total_base": len(base_parts),
                "total_target": len(target_parts),
                "added": len(added),
                "deleted": len(deleted),
                "modified": len(modified),
                "same": same_count,
            },
            "added": added,
            "deleted": deleted,
            "modified": modified,
        }
    )


def register_ebom_legacy_read_capability(registry: Any) -> None:
    registry.register(
        CapabilitySpec(
            id="craft.ebom.legacy_read",
            owner="craft",
            description="Read bounded legacy PBOM snapshot comparison projections.",
            use_when="A governed Craft consumer needs the legacy eBOM/PBOM diff response shape.",
            do_not_use_when="The consumer needs mutation, VPPS validation, or the native PBOM compare contract.",
            risk="read",
            permissions=("craft.read",),
            input_schema={
                "type": "object",
                "required": ["operation", "base_gid", "target_gid"],
                "properties": {
                    "operation": {"type": "string", "enum": list(OPERATIONS)},
                    "base_gid": {"type": "string"},
                    "target_gid": {"type": "string"},
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["base", "target", "summary", "added", "deleted", "modified"],
                "properties": {
                    "base": {"type": "object", "additionalProperties": True},
                    "target": {"type": "object", "additionalProperties": True},
                    "summary": {"type": "object", "additionalProperties": True},
                    "added": {"type": "array", "maxItems": _MAX_ITEMS, "items": {"type": "object", "additionalProperties": True}},
                    "deleted": {"type": "array", "maxItems": _MAX_ITEMS, "items": {"type": "object", "additionalProperties": True}},
                    "modified": {"type": "array", "maxItems": _MAX_ITEMS, "items": {"type": "object", "additionalProperties": True}},
                },
                "additionalProperties": False,
            },
            tags=("craft", "ebom", "legacy", "read"),
        ),
        diff_snapshots,
    )


__all__ = ["OPERATIONS", "diff_snapshots", "register_ebom_legacy_read_capability"]
