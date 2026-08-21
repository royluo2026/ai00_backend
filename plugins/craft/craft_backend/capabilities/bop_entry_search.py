"""Bounded search over non-deleted BOP entries."""
from __future__ import annotations

from typing import Any

from backend.capability_v2.provider_contracts import CapabilityContext, CapabilityOutput, CapabilitySpec

from ..data.connection import get_craft_conn


def search_bop_entries(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    query = payload.get("q")
    query = str(query) if query is not None else ""
    raw_types = payload.get("node_types")
    node_types = [str(item).strip() for item in (raw_types or []) if str(item).strip()]
    limit = payload.get("limit", 200)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500")
    clauses = ["e.is_deleted=FALSE"]
    params: list[Any] = []
    if node_types:
        clauses.append("e.node_type IN (" + ",".join(["%s"] * len(node_types)) + ")")
        params.extend(node_types)
    if query:
        clauses.append("COALESCE(e.title,'') LIKE %s")
        params.append(f"%{query}%")
    params.append(limit)
    with get_craft_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT e.gid, COALESCE(e.title,'') AS title, e.node_type, "
                "v.gid AS version_gid, v.version_tag "
                "FROM workmanship_bop_bop_entries e "
                "JOIN workmanship_bop_bop_versions v ON v.gid=e.version_gid "
                "WHERE " + " AND ".join(clauses) + " ORDER BY v.version_tag, e.sort_order LIMIT %s",
                params,
            )
            rows = [dict(row) for row in cur.fetchall()]
    return CapabilityOutput(data={"data": rows})


def register_bop_entry_search_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.bop.entry.search", owner="craft",
        description="Search bounded non-deleted BOP entries by title and node type.",
        use_when="A governed consumer needs to find BOP entries before selecting a detail or structure capability.",
        do_not_use_when="The consumer needs a revision-pinned detail, mutation, or complete execution structure.",
        risk="read", permissions=("craft.read",),
        input_schema={"type": "object", "properties": {"q": {"type": "string"}, "node_types": {"type": "array", "items": {"type": "string"}, "maxItems": 20}, "limit": {"type": "integer", "minimum": 1, "maximum": 500}}, "additionalProperties": False},
        output_schema={"type": "object", "required": ["data"], "properties": {"data": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}}}, "additionalProperties": False},
        tags=("craft", "bop", "entry", "search"),
    ), search_bop_entries)
