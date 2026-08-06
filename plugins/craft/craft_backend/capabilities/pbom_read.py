"""Snapshot-scoped PBOM read Capabilities."""
from __future__ import annotations

from typing import Any, Mapping

from backend.capabilities.models_next import CapabilityBusinessError, CapabilityContext, CapabilityOutput, CapabilitySpec, EvidenceRef

from ..data.connection import get_craft_conn


def _text(payload: Mapping[str, Any], name: str, *, required: bool = False) -> str | None:
    value = payload.get(name)
    if value is None or value == "":
        if required:
            raise ValueError(f"{name} is required")
        return None
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    value = value.strip()
    if required and not value:
        raise ValueError(f"{name} is required")
    return value or None


def _limit(payload: Mapping[str, Any]) -> int:
    value = payload.get("limit", 50)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 100:
        raise ValueError("limit must be between 1 and 100")
    return value


class PbomRepository:
    def get_snapshot(self, snapshot_gid: str) -> dict[str, Any] | None:
        with get_craft_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT gid, project_gid, version_tag, name, source_type, status, meta, created_at "
                    "FROM workmanship_bop_pbom_versions WHERE gid = %s",
                    (snapshot_gid,),
                )
                row = cursor.fetchone()
        return dict(row) if row else None

    def list_parts(self, snapshot_gid: str, query: str | None, limit: int = 10000) -> list[dict[str, Any]]:
        where = ["snapshot_gid = %s", "is_deleted = 0"]
        params: list[Any] = [snapshot_gid]
        if query:
            where.append("(part_no LIKE %s OR title LIKE %s OR vpps LIKE %s)")
            pattern = f"%{query}%"
            params.extend([pattern, pattern, pattern])
        params.append(limit)
        with get_craft_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT gid, snapshot_gid, part_no, title, quantity, unit, material, "
                    "parent_gid, component_id, vpps, vpps_desc, catia_occurrence_name, meta "
                    "FROM workmanship_bop_pbom WHERE " + " AND ".join(where) +
                    " ORDER BY part_no ASC, gid ASC LIMIT %s",
                    tuple(params),
                )
                return [dict(row) for row in cursor.fetchall()]


repository = PbomRepository()


def _snapshot(snapshot_gid: str) -> dict[str, Any]:
    row = repository.get_snapshot(snapshot_gid)
    if row is None:
        raise CapabilityBusinessError("pbom_snapshot_not_found", "PBOM snapshot not found", details={"snapshot_gid": snapshot_gid})
    return row


def _part(row: Mapping[str, Any]) -> dict[str, Any]:
    return {name: row.get(name) for name in (
        "gid", "snapshot_gid", "part_no", "title", "quantity", "unit", "material",
        "parent_gid", "component_id", "vpps", "vpps_desc", "catia_occurrence_name",
    )}


def get_pbom_snapshot(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    snapshot_gid = _text(payload, "snapshot_gid", required=True)
    row = _snapshot(snapshot_gid)
    parts = repository.list_parts(snapshot_gid, None)
    data = {**{name: row.get(name) for name in ("gid", "project_gid", "version_tag", "name", "source_type", "status", "created_at")}, "part_count": len(parts)}
    return CapabilityOutput(data=data, evidence=(EvidenceRef(kind="craft.pbom.snapshot", reference=f"craft://pbom/snapshot/{snapshot_gid}", summary=f"PBOM snapshot {snapshot_gid}"),))


def search_pbom_parts(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    snapshot_gid = _text(payload, "snapshot_gid", required=True)
    _snapshot(snapshot_gid)
    rows = repository.list_parts(snapshot_gid, _text(payload, "query"), _limit(payload))
    return CapabilityOutput(data={"snapshot_gid": snapshot_gid, "items": [_part(row) for row in rows]})


def compare_pbom_snapshots(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    from_gid = _text(payload, "from_snapshot_gid", required=True)
    to_gid = _text(payload, "to_snapshot_gid", required=True)
    before = _snapshot(from_gid)
    after = _snapshot(to_gid)
    before_rows = repository.list_parts(from_gid, None)
    after_rows = repository.list_parts(to_gid, None)
    identity = lambda row: str(row.get("component_id") or row.get("part_no") or row.get("gid"))
    left = {identity(row): _part(row) for row in before_rows}
    right = {identity(row): _part(row) for row in after_rows}
    common = sorted(set(left) & set(right))
    changed = [{"identity": key, "before": left[key], "after": right[key]} for key in common if left[key] != right[key]]
    data = {
        "comparability": "same_project" if before.get("project_gid") == after.get("project_gid") else "different_project",
        "from_snapshot_gid": from_gid,
        "to_snapshot_gid": to_gid,
        "added": [right[key] for key in sorted(set(right) - set(left))],
        "removed": [left[key] for key in sorted(set(left) - set(right))],
        "changed": changed,
    }
    return CapabilityOutput(data=data)


def register_pbom_read_capabilities(registry: Any) -> None:
    common = {"owner": "craft", "plugin_callable": False, "permissions": (), "subject_concepts": ("craft.pbom.snapshot",), "effects": ("read:craft.pbom",)}
    specs = (
        ("craft.pbom.snapshot.get", get_pbom_snapshot, ["snapshot_gid"], ["gid", "part_count"]),
        ("craft.pbom.snapshot.compare", compare_pbom_snapshots, ["from_snapshot_gid", "to_snapshot_gid"], ["comparability", "added", "removed", "changed"]),
        ("craft.pbom.part.search", search_pbom_parts, ["snapshot_gid"], ["snapshot_gid", "items"]),
    )
    for capability_id, handler, required_input, required_output in specs:
        registry.register(CapabilitySpec(
            id=capability_id, description=capability_id, use_when="A PBOM snapshot is explicitly selected.",
            do_not_use_when="No exact PBOM snapshot is known.",
            input_schema={"type": "object", "required": required_input},
            output_schema={"type": "object", "required": required_output},
            tags=("craft", "pbom", "read"), **common,
        ), handler)
