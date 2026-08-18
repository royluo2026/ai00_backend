"""Bounded BOP navigation projections implemented with Craft-owned scoped SQL."""
from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Callable, Mapping
from datetime import date, datetime
from typing import Any

from backend.capability_v2.provider_contracts import CapabilityBusinessError

from ..data.connection import get_craft_conn


_MIN_SORT = -1.7976931348623157e308
_REF_FIELDS = {
    "pbom_part": ("part_refs", "part"),
    "project_tools": ("tool_refs", "tool"),
    "physical_tool": ("tool_refs", "tool"),
    "tool": ("tool_refs", "tool"),
    "project_tooling": ("fixture_refs", "fixture"),
    "physical_fixture": ("fixture_refs", "fixture"),
    "fixture": ("fixture_refs", "fixture"),
    "project_equipment": ("equipment_refs", "equipment"),
    "physical_equipment": ("equipment_refs", "equipment"),
    "equipment": ("equipment_refs", "equipment"),
    "knowledge": ("knowledge_refs", "knowledge"),
    "knowledge_revision": ("knowledge_refs", "knowledge"),
    "knowledge_document": ("knowledge_refs", "knowledge"),
    "rule": ("rule_refs", "rule"),
    "rule_std": ("rule_refs", "rule"),
    "rule_custom": ("rule_refs", "rule"),
}
_REF_NAMES = tuple(sorted({value[0] for value in _REF_FIELDS.values()}))
_COUNT_NAMES = ("stations", "roles", "processes", "operations", "parts", "resources")
_COUNT_GROUP = {
    "station_process": "stations",
    "operator_process": "roles",
    "process": "processes",
    "bop_process": "processes",
    "operation": "operations",
    "bop_steps": "operations",
    "part": "parts",
    "non_standard_part": "parts",
    "standard_part": "parts",
    "support_material": "parts",
    "equipment_factory": "resources",
    "tool_factory": "resources",
    "fixture_factory": "resources",
    "equipment_need": "resources",
    "tool_need": "resources",
    "fixture_need": "resources",
}


def _error(code: str, message: str, **details: Any) -> CapabilityBusinessError:
    return CapabilityBusinessError(code, message, details=details)


def encode_cursor(sort_order: float | int, gid: str) -> str:
    document = {"gid": str(gid), "sort_order": float(sort_order), "v": 1}
    raw = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(value: str | None) -> tuple[float, str]:
    if not isinstance(value, str) or not value:
        raise _error("invalid_cursor", "Cursor is invalid")
    try:
        padded = value + "=" * (-len(value) % 4)
        raw = base64.b64decode(padded, altchars=b"-_", validate=True)
        document = json.loads(raw.decode("utf-8"))
        if base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=") != value:
            raise ValueError("non-canonical cursor")
        if not isinstance(document, dict) or set(document) != {"gid", "sort_order", "v"}:
            raise ValueError("invalid cursor fields")
        if document["v"] != 1 or not isinstance(document["gid"], str) or not document["gid"]:
            raise ValueError("invalid cursor values")
        if isinstance(document["sort_order"], bool):
            raise ValueError("invalid cursor order")
        return float(document["sort_order"]), document["gid"]
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise _error("invalid_cursor", "Cursor is invalid") from exc


def _json_value(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str) and value:
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return fallback
    return fallback


def _transport(value: Any) -> Any:
    return value.isoformat() if isinstance(value, (datetime, date)) else value


class BopNavigationRepository:
    def __init__(self, connection_factory: Callable[[], Any] = get_craft_conn) -> None:
        self._connection_factory = connection_factory

    @staticmethod
    def _page_size(value: int, maximum: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
            raise _error("invalid_page_size", f"page_size must be between 1 and {maximum}")
        return value

    @staticmethod
    def _assert_revision(cursor: Any, version_gid: str, expected_revision: int) -> None:
        cursor.execute(
            "SELECT revision FROM workmanship_bop_bop_versions "
            "WHERE gid=%s AND is_deleted=0",
            (version_gid,),
        )
        row = cursor.fetchone()
        if not row:
            raise _error("bop_version_not_found", "BOP version not found", version_gid=version_gid)
        current = row.get("revision") if isinstance(row, Mapping) else None
        if current != expected_revision:
            raise _error(
                "revision_conflict", "BOP revision changed during navigation read",
                version_gid=version_gid, expected_revision=expected_revision,
                current_revision=current,
            )

    def get_outline_page(
        self, version_gid: str, revision: int, *, cursor: str | None, page_size: int,
    ) -> dict[str, Any]:
        size = self._page_size(page_size, 100)
        cursor_sort, cursor_gid = decode_cursor(cursor) if cursor else (_MIN_SORT, "")
        with self._connection_factory() as connection:
            with connection.cursor() as db:
                self._assert_revision(db, version_gid, revision)
                db.execute(
                    "SELECT gid,parent_gid,node_type,sort_order,title "
                    "FROM workmanship_bop_bop_entries WHERE version_gid=%s "
                    "AND is_deleted=0 AND parent_gid IS NULL ORDER BY sort_order,gid LIMIT 1",
                    (version_gid,),
                )
                root = db.fetchone()
                db.execute(
                    "SELECT gid,parent_gid,node_type,sort_order,title "
                    "FROM workmanship_bop_bop_entries e WHERE version_gid=%s AND is_deleted=0 "
                    "AND node_type='line_process' "
                    "AND (e.sort_order > %s OR (e.sort_order = %s AND e.gid > %s)) "
                    "ORDER BY e.sort_order,e.gid LIMIT %s",
                    (version_gid, cursor_sort, cursor_sort, cursor_gid, size + 1),
                )
                raw_lines = [dict(row) for row in db.fetchall()]
                db.execute(
                    "SELECT COUNT(*) AS total_count FROM workmanship_bop_bop_entries "
                    "WHERE version_gid=%s AND is_deleted=0 AND node_type='line_process'",
                    (version_gid,),
                )
                total_row = db.fetchone() or {}
                page = raw_lines[:size]
                counts: dict[str, dict[str, int]] = {
                    str(row["gid"]): {name: 0 for name in _COUNT_NAMES} for row in page
                }
                if page:
                    placeholders = ",".join("%s" for _ in page)
                    db.execute(
                        "WITH RECURSIVE scoped(root_gid,gid,node_type) AS ("
                        " SELECT e.gid,e.gid,e.node_type FROM workmanship_bop_bop_entries e"
                        f" WHERE e.version_gid=%s AND e.is_deleted=0 AND e.gid IN ({placeholders})"
                        " UNION ALL SELECT s.root_gid,c.gid,c.node_type"
                        " FROM workmanship_bop_bop_entries c JOIN scoped s ON c.parent_gid=s.gid"
                        " WHERE c.version_gid=%s AND c.is_deleted=0)"
                        " SELECT root_gid,node_type,COUNT(*) AS node_count FROM scoped"
                        " WHERE gid<>root_gid GROUP BY root_gid,node_type",
                        (version_gid, *(row["gid"] for row in page), version_gid),
                    )
                    for row in db.fetchall():
                        group = _COUNT_GROUP.get(str(row["node_type"]))
                        if group:
                            counts[str(row["root_gid"])][group] += int(row["node_count"])
                self._assert_revision(db, version_gid, revision)
        lines = [{**row, "counts": counts[str(row["gid"])]} for row in page]
        next_cursor = (
            encode_cursor(page[-1]["sort_order"], page[-1]["gid"])
            if len(raw_lines) > size and page else None
        )
        return {
            "version_gid": version_gid, "revision": revision,
            "root": dict(root) if root else None, "lines": lines,
            "total_lines": int(total_row.get("total_count") or 0),
            "next_cursor": next_cursor,
        }

    def get_work_package_page(
        self, version_gid: str, revision: int, scope_kind: str, scope_gid: str,
        *, cursor: str | None, page_size: int,
    ) -> dict[str, Any]:
        if scope_kind not in {"line", "station"}:
            raise _error("invalid_scope_kind", "scope_kind must be line or station")
        size = self._page_size(page_size, 200)
        cursor_sort, cursor_gid = decode_cursor(cursor) if cursor else (_MIN_SORT, "")
        with self._connection_factory() as connection:
            with connection.cursor() as db:
                self._assert_revision(db, version_gid, revision)
                db.execute(
                    "SELECT gid,node_type FROM workmanship_bop_bop_entries "
                    "WHERE version_gid=%s AND gid=%s AND is_deleted=0",
                    (version_gid, scope_gid),
                )
                scope = db.fetchone()
                expected_type = "line_process" if scope_kind == "line" else "station_process"
                if not scope or scope.get("node_type") != expected_type:
                    raise _error("scope_not_found", "BOP scope was not found", scope_gid=scope_gid)
                cte = (
                    "WITH RECURSIVE scoped(gid) AS ("
                    " SELECT gid FROM workmanship_bop_bop_entries"
                    " WHERE version_gid=%s AND gid=%s AND is_deleted=0"
                    " UNION ALL SELECT e.gid FROM workmanship_bop_bop_entries e"
                    " JOIN scoped s ON e.parent_gid=s.gid"
                    " WHERE e.version_gid=%s AND e.is_deleted=0) "
                )
                db.execute(
                    cte +
                    "SELECT e.gid,e.parent_gid,e.node_type,e.sort_order,e.title,e.vpps "
                    "FROM workmanship_bop_bop_entries e JOIN scoped s ON s.gid=e.gid "
                    "WHERE e.version_gid=%s "
                    "AND (e.sort_order > %s OR (e.sort_order = %s AND e.gid > %s)) "
                    "ORDER BY e.sort_order,e.gid LIMIT %s",
                    (version_gid, scope_gid, version_gid, version_gid,
                     cursor_sort, cursor_sort, cursor_gid, size + 1),
                )
                raw_nodes = [dict(row) for row in db.fetchall()]
                db.execute(
                    cte + "SELECT COUNT(*) AS total_count FROM scoped",
                    (version_gid, scope_gid, version_gid),
                )
                total_row = db.fetchone() or {}
                page = raw_nodes[:size]
                links: list[dict[str, Any]] = []
                if page:
                    placeholders = ",".join("%s" for _ in page)
                    db.execute(
                        "SELECT entry_gid,link_type,entity_gid,is_primary "
                        "FROM workmanship_bop_bop_entry_links WHERE version_gid=%s "
                        f"AND is_deleted=0 AND entry_gid IN ({placeholders}) "
                        "ORDER BY entry_gid,link_type,entity_gid",
                        (version_gid, *(row["gid"] for row in page)),
                    )
                    links = [dict(row) for row in db.fetchall()]
                self._assert_revision(db, version_gid, revision)
        refs = {str(row["gid"]): {name: [] for name in _REF_NAMES} for row in page}
        for link in links:
            mapping = _REF_FIELDS.get(str(link.get("link_type") or ""))
            entity_gid = link.get("entity_gid")
            entry_gid = str(link.get("entry_gid"))
            if mapping and entity_gid and entry_gid in refs:
                field, prefix = mapping
                refs[entry_gid][field].append(f"{prefix}:{entity_gid}")
        nodes = []
        for row in page:
            node_refs = {key: sorted(set(values)) for key, values in refs[str(row["gid"])].items()}
            nodes.append({**row, **node_refs})
        next_cursor = (
            encode_cursor(page[-1]["sort_order"], page[-1]["gid"])
            if len(raw_nodes) > size and page else None
        )
        return {
            "version_gid": version_gid, "revision": revision,
            "scope": {"kind": scope_kind, "gid": scope_gid},
            "nodes": nodes, "links": links,
            "total_count": int(total_row.get("total_count") or 0),
            "next_cursor": next_cursor,
        }

    def get_entry_detail(
        self, version_gid: str, revision: int, entry_gid: str,
    ) -> dict[str, Any]:
        with self._connection_factory() as connection:
            with connection.cursor() as db:
                self._assert_revision(db, version_gid, revision)
                db.execute(
                    "SELECT gid,version_gid,parent_gid,node_type,sort_order,level,ai00_level,"
                    "title,vpps,vpps_desc,owner_gid,meta,process_flow_pic,process_chart_pic,"
                    "created_at,updated_at FROM workmanship_bop_bop_entries "
                    "WHERE version_gid=%s AND gid=%s AND is_deleted=0",
                    (version_gid, entry_gid),
                )
                row = db.fetchone()
                if not row:
                    raise _error("entry_not_found", "BOP entry was not found", entry_gid=entry_gid)
                db.execute(
                    "SELECT entry_gid,link_type,entity_gid,is_primary,snapshot_data "
                    "FROM workmanship_bop_bop_entry_links WHERE version_gid=%s "
                    "AND entry_gid=%s AND is_deleted=0 ORDER BY link_type,entity_gid LIMIT %s",
                    (version_gid, entry_gid, 501),
                )
                links = [dict(item) for item in db.fetchall()]
                if len(links) > 500:
                    raise _error(
                        "entry_detail_too_large",
                        "BOP entry has more than 500 links; use a bounded relation capability",
                        entry_gid=entry_gid,
                    )
                self._assert_revision(db, version_gid, revision)
        detail = dict(row)
        detail = {key: _transport(value) for key, value in detail.items()}
        detail["meta"] = _json_value(detail.get("meta"), {})
        detail["process_flow_pic"] = _json_value(detail.get("process_flow_pic"), [])
        detail["process_chart_pic"] = _json_value(detail.get("process_chart_pic"), [])
        for link in links:
            link["snapshot_data"] = _json_value(link.get("snapshot_data"), {})
        return {
            "version_gid": version_gid, "revision": revision,
            "entry": detail, "links": links,
        }


repository = BopNavigationRepository()


__all__ = ["BopNavigationRepository", "decode_cursor", "encode_cursor", "repository"]
