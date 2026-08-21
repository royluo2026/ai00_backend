"""Read-only Capabilities for the single active GBOP release."""
from __future__ import annotations

import json
from typing import Any, Mapping

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext, CapabilityOutput, CapabilitySpec, EvidenceRef

from ..data.connection import get_craft_conn

_STATUSES = frozenset({"exact", "modified", "outdated", "inherited", "broken"})
_VERSION_COLUMNS = (
    "gid,name,version_family_gid,status,frozen_at,archived_at,"
    "vehicle_model,team_id,created_by,created_at,updated_at"
)


def _json(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping): return dict(value)
    if isinstance(value, str) and value.strip():
        try: decoded = json.loads(value)
        except ValueError: return {}
        return dict(decoded) if isinstance(decoded, Mapping) else {}
    return {}


def _required(payload: Mapping[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip(): raise ValueError(f"{name} is required")
    return value.strip()


class GbopRepository:
    def list_versions(self, include_archived: bool = False) -> list[dict[str, Any]]:
        where = "" if include_archived else " WHERE archived_at IS NULL"
        with get_craft_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT {_VERSION_COLUMNS} FROM workmanship_tpl_gbop_versions"
                    f"{where} ORDER BY version_family_gid, created_at, gid"
                )
                return [dict(row) for row in cursor.fetchall()]

    def resolve_active_release(self) -> dict[str, Any]:
        with get_craft_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT gid, name, version_family_gid, status, frozen_at, updated_at "
                    "FROM workmanship_tpl_gbop_versions "
                    "WHERE status = 'active' AND archived_at IS NULL ORDER BY updated_at DESC, gid ASC LIMIT 2"
                )
                rows = [dict(row) for row in cursor.fetchall()]
        if not rows: raise CapabilityBusinessError("active_gbop_not_found", "No active GBOP release exists")
        if len(rows) > 1: raise CapabilityBusinessError("multiple_active_gbop_releases", "More than one active GBOP release exists")
        return rows[0]

    def search_items(self, release_gid: str, query: str | None, limit: int) -> list[dict[str, Any]]:
        params: list[Any] = [release_gid]
        where = ["version_gid = %s", "status = 'active'"]
        if query:
            where.append("(vpps LIKE %s OR vpps_desc LIKE %s OR vpps_part LIKE %s)")
            pattern = f"%{query}%"; params.extend([pattern, pattern, pattern])
        params.append(limit)
        with get_craft_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT gid, version_gid, parent_gid, level, node_type, seq_no, vpps, vpps_desc, "
                    "vpps_part, part_feed, importance, torque_importance, sort_order, meta "
                    "FROM workmanship_tpl_gbop_entries WHERE " + " AND ".join(where) +
                    " ORDER BY sort_order ASC, gid ASC LIMIT %s", tuple(params))
                return [dict(row) for row in cursor.fetchall()]

    def get_item(self, item_gid: str) -> dict[str, Any] | None:
        with get_craft_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT gid, version_gid, parent_gid, node_type, vpps, vpps_desc, vpps_part, meta "
                    "FROM workmanship_tpl_gbop_entries WHERE gid = %s", (item_gid,))
                row = cursor.fetchone()
        return dict(row) if row else None

    def list_usage(self, item_gid: str) -> list[dict[str, Any]]:
        with get_craft_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT l.version_gid AS bop_version_gid, l.entry_gid, l.is_inherited, l.snapshot_data, "
                    "e.is_deleted, e.meta FROM workmanship_bop_bop_entry_links l "
                    "LEFT JOIN workmanship_bop_bop_entries e ON e.gid = l.entry_gid "
                    "WHERE l.gbop_source_gid = %s AND l.is_deleted = 0", (item_gid,))
                return [dict(row) for row in cursor.fetchall()]


repository = GbopRepository()


def _active_item(payload: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    release = repository.resolve_active_release()
    item_gid = _required(payload, "item_gid")
    item = repository.get_item(item_gid)
    if item is None or str(item.get("version_gid")) != str(release["gid"]):
        raise CapabilityBusinessError("active_gbop_item_not_found", "GBOP item is not in the active release", details={"item_gid": item_gid})
    return release, item


def search_gbop_items(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    release = repository.resolve_active_release()
    query = payload.get("query")
    if query is not None and not isinstance(query, str): raise ValueError("query must be a string")
    limit = payload.get("limit", 50)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100: raise ValueError("limit must be between 1 and 100")
    rows = repository.search_items(str(release["gid"]), query.strip() if query else None, limit)
    items = [{name: row.get(name) for name in ("gid", "parent_gid", "node_type", "vpps", "vpps_desc", "vpps_part", "part_feed", "importance", "torque_importance")} for row in rows]
    return CapabilityOutput(data={"active_release_gid": str(release["gid"]), "items": items})


def _version_row(row: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(row)
    for name in ("frozen_at", "archived_at", "created_at", "updated_at"):
        if result.get(name) is not None:
            result[name] = str(result[name])
    return result


def search_gbop_releases(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    include_archived = payload.get("include_archived", False)
    if not isinstance(include_archived, bool):
        raise ValueError("include_archived must be a boolean")
    rows = repository.list_versions(include_archived=include_archived)
    if len(rows) > 500:
        raise ValueError("GBOP version inventory exceeds the bounded limit of 500")
    return CapabilityOutput(data={"items": [_version_row(row) for row in rows]})


def _provenance(row: Mapping[str, Any]) -> str:
    meta = _json(row.get("meta")); explicit = row.get("provenance_status") or meta.get("provenance_status")
    if explicit in _STATUSES: return str(explicit)
    if row.get("is_deleted"): return "broken"
    if row.get("is_inherited"): return "inherited"
    snapshot = _json(row.get("snapshot_data"))
    if snapshot.get("modified") is True: return "modified"
    if snapshot.get("outdated") is True: return "outdated"
    return "exact"


def get_gbop_item_usage(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    release, item = _active_item(payload)
    rows = repository.list_usage(str(item["gid"]))
    items = [{"bop_version_gid": row.get("bop_version_gid"), "entry_gid": row.get("entry_gid"), "provenance_status": _provenance(row)} for row in rows]
    return CapabilityOutput(data={"active_release_gid": str(release["gid"]), "item_gid": str(item["gid"]), "items": items})


def list_gbop_item_knowledge(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    release, item = _active_item(payload)
    refs = _json(item.get("meta")).get("knowledge_refs", [])
    pinned = []
    if isinstance(refs, list):
        for ref in refs:
            if isinstance(ref, Mapping) and ref.get("document_gid") and ref.get("revision_gid"):
                pinned.append({"document_gid": str(ref["document_gid"]), "revision_gid": str(ref["revision_gid"]), "title": ref.get("title")})
    return CapabilityOutput(data={"active_release_gid": str(release["gid"]), "item_gid": str(item["gid"]), "items": pinned})


def register_gbop_read_capabilities(registry: Any) -> None:
    common = {"owner": "craft", "plugin_callable": False, "permissions": (), "subject_concepts": ("craft.gbop.item",), "effects": ("read:craft.gbop",), "tags": ("craft", "gbop", "active", "read")}
    for capability_id, handler, required in (
        ("craft.gbop.item.search", search_gbop_items, []),
        ("craft.gbop.item.usage.get", get_gbop_item_usage, ["item_gid"]),
        ("craft.gbop.item.knowledge.list", list_gbop_item_knowledge, ["item_gid"]),
    ):
        registry.register(CapabilitySpec(id=capability_id, description=capability_id,
            use_when="The current active GBOP release is the required source.",
            do_not_use_when="A historical or draft GBOP release is required.",
            input_schema={"type": "object", "required": required},
            output_schema={"type": "object", "required": ["active_release_gid", "items"]}, **common), handler)
