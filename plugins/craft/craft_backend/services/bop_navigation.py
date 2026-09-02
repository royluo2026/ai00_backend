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
_PUBLIC_LINK_FIELDS = (
    "link_gid", "entry_gid", "version_gid", "link_type", "entity_gid", "is_primary",
)
_ENTITY_CARD_FIELDS = frozenset({
    "gid", "project_gid", "bop_version_gid", "snapshot_gid", "name", "title",
    "part_no", "code", "resource_type", "status", "vpps", "vpps_desc", "version_no",
    "process_code", "operation_code", "operator_code", "unit", "material", "parent_gid",
    "owner_gid", "modified_type", "sequence_color", "position", "bom_row_id", "vpps_part",
    "standard_time", "station_height", "height_mm", "height", "headcount", "quantity",
    "critical_process", "part_feed", "ext", "meta", "params", "attributes",
    "process_flow_pic", "process_chart_pic",
})
_ENTITY_CARD_EXPRESSION = """
CASE
        WHEN v.frozen_at IS NOT NULL AND l.snapshot_data IS NOT NULL THEN l.snapshot_data
        WHEN l.link_type='bop_line' AND ln.gid IS NOT NULL THEN JSON_OBJECT(
            'gid',ln.gid,'project_gid',ln.project_gid,'name',ln.title,
            'vpps',ln.vpps,'version_no',ln.version_no,'owner_gid',ln.owner_gid,
            'ext',ln.ext)
        WHEN l.link_type='bop_station' AND st.gid IS NOT NULL THEN JSON_OBJECT(
            'gid',st.gid,'project_gid',st.project_gid,'name',st.title,
            'vpps',st.vpps,'version_no',st.version_no,'owner_gid',st.owner_gid,
            'height_mm',JSON_EXTRACT(st.ext,'$.height_mm'),
            'height',JSON_EXTRACT(st.ext,'$.height'),'ext',st.ext)
        WHEN l.link_type='bop_process' AND pr.gid IS NOT NULL THEN JSON_OBJECT(
            'gid',pr.gid,'project_gid',pr.project_gid,'bop_version_gid',pr.bop_version_gid,
            'name',pr.name,'process_code',pr.process_code,'standard_time',pr.standard_time,
            'vpps',pr.vpps,'vpps_desc',pr.vpps_desc,'params',pr.params,
            'modified_type',JSON_UNQUOTE(JSON_EXTRACT(pr.ext,'$.modified_type')),
            'critical_process',JSON_EXTRACT(pr.ext,'$.critical_process'),
            'sequence_color',JSON_UNQUOTE(JSON_EXTRACT(pr.ext,'$.sequence_color')),
            'ext',pr.ext)
        WHEN l.link_type='bop_steps' AND op.gid IS NOT NULL THEN JSON_OBJECT(
            'gid',op.gid,'project_gid',op.project_gid,'name',op.title,
            'operation_code',op.operation_code,'station_height',op.station_height,
            'vpps',op.vpps,'vpps_desc',op.vpps_desc,'params',op.params,
            'process_flow_pic',op.process_flow_pic,'process_chart_pic',op.process_chart_pic,
            'vpps_part',op.vpps_part,'part_feed',op.part_feed,'ext',op.ext)
        WHEN l.link_type='bop_operator' AND opr.gid IS NOT NULL THEN JSON_OBJECT(
            'gid',opr.gid,'project_gid',opr.project_gid,'name',opr.title,
            'operator_code',opr.operator_code,'headcount',opr.headcount,
            'vpps',opr.vpps,'version_no',opr.version_no,'owner_gid',opr.owner_gid,
            'position',JSON_UNQUOTE(JSON_EXTRACT(opr.ext,'$.position')),'ext',opr.ext)
        WHEN l.link_type='pbom_part' AND pb.gid IS NOT NULL THEN JSON_OBJECT(
            'gid',pb.gid,'snapshot_gid',pb.snapshot_gid,'part_no',pb.part_no,
            'name',pb.title,'quantity',pb.quantity,'unit',pb.unit,'material',pb.material,
            'parent_gid',pb.parent_gid,'vpps',pb.vpps,'vpps_desc',pb.vpps_desc,
            'bom_row_id',pb.bom_row,'meta',pb.meta)
        WHEN l.link_type IN ('resource_socket','resource_tool','resource_fixture','resource_equipment')
             AND rr.gid IS NOT NULL THEN JSON_OBJECT(
            'gid',rr.gid,'resource_type',rr.resource_type,'code',rr.code,'name',rr.name,
            'status',rr.status,'attributes',rr.attributes)
END
"""
_PRIMARY_CARD_EXPRESSION = f"CASE WHEN l.is_primary=1 THEN {_ENTITY_CARD_EXPRESSION} END"
_LINK_CARD_SELECT = f"""
SELECT l.gid AS link_gid,l.entry_gid,l.version_gid,l.link_type,l.entity_gid,l.is_primary,
       l.snapshot_data,{_PRIMARY_CARD_EXPRESSION} AS entity_data
FROM workmanship_bop_bop_entry_links l
JOIN workmanship_bop_bop_versions v ON v.gid=l.version_gid
LEFT JOIN workmanship_bop_bop_line ln ON ln.gid=l.entity_gid AND l.link_type='bop_line'
LEFT JOIN workmanship_bop_bop_station st ON st.gid=l.entity_gid AND l.link_type='bop_station'
LEFT JOIN workmanship_bop_bop_process pr ON pr.gid=l.entity_gid AND l.link_type='bop_process'
LEFT JOIN workmanship_bop_bop_steps op ON op.gid=l.entity_gid AND l.link_type='bop_steps'
LEFT JOIN workmanship_bop_bop_operator opr ON opr.gid=l.entity_gid AND l.link_type='bop_operator'
LEFT JOIN workmanship_bop_pbom pb ON pb.gid=l.entity_gid AND l.link_type='pbom_part'
LEFT JOIN workmanship_craft_resource_requirements rr ON rr.gid=l.entity_gid
    AND l.link_type IN ('resource_socket','resource_tool','resource_fixture','resource_equipment')
"""


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


def _entity_card(value: Any) -> dict[str, Any] | None:
    card = _json_value(value, None)
    if not isinstance(card, dict):
        return None
    card = {key: item for key, item in card.items() if key in _ENTITY_CARD_FIELDS}
    for field in ("ext", "meta", "params", "attributes"):
        if field in card:
            card[field] = _json_value(card.get(field), {})
    for field in ("process_flow_pic", "process_chart_pic"):
        if field in card:
            card[field] = _json_value(card.get(field), [])
    return {key: _transport(item) for key, item in card.items()}


def _public_link(link: Mapping[str, Any], *, include_snapshot: bool = False) -> dict[str, Any]:
    projected = {key: link.get(key) for key in _PUBLIC_LINK_FIELDS if key in link}
    if "is_primary" in projected:
        projected["is_primary"] = bool(projected["is_primary"])
    if include_snapshot:
        projected["snapshot_data"] = _json_value(link.get("snapshot_data"), {})
    return projected


def _add_primary_projection(row: dict[str, Any], links: list[dict[str, Any]]) -> dict[str, Any]:
    primary = [link for link in links if bool(link.get("is_primary"))]
    row["primary_link_count"] = len(primary)
    row["primary_link"] = _public_link(primary[0]) if primary else None
    row["entity_data"] = _entity_card(primary[0].get("entity_data")) if primary else None
    return row


def _normalize_entry_fields(row: dict[str, Any]) -> dict[str, Any]:
    row["meta"] = _json_value(row.get("meta"), {})
    row["process_flow_pic"] = _json_value(row.get("process_flow_pic"), [])
    row["process_chart_pic"] = _json_value(row.get("process_chart_pic"), [])
    return row


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
                    "SELECT e.gid,e.parent_gid,e.node_type,e.sort_order,e.title,e.vpps,"
                    "e.meta,e.process_flow_pic,e.process_chart_pic,"
                    "JSON_UNQUOTE(JSON_EXTRACT(e.meta,'$.tc_key')) AS bom_row_id "
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
                        _LINK_CARD_SELECT +
                        f" WHERE l.version_gid=%s AND l.is_deleted=0 AND l.deleted_at IS NULL"
                        f" AND l.entry_gid IN ({placeholders})"
                        " ORDER BY l.entry_gid,l.is_primary DESC,l.link_type,l.entity_gid",
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
        links_by_entry: dict[str, list[dict[str, Any]]] = {}
        for link in links:
            links_by_entry.setdefault(str(link.get("entry_gid")), []).append(link)
        nodes = []
        for row in page:
            node_refs = {key: sorted(set(values)) for key, values in refs[str(row["gid"])].items()}
            node = _normalize_entry_fields({**row, **node_refs})
            nodes.append(_add_primary_projection(node, links_by_entry.get(str(row["gid"]), [])))
        next_cursor = (
            encode_cursor(page[-1]["sort_order"], page[-1]["gid"])
            if len(raw_nodes) > size and page else None
        )
        return {
            "version_gid": version_gid, "revision": revision,
            "scope": {"kind": scope_kind, "gid": scope_gid},
            "nodes": nodes, "links": [_public_link(link) for link in links],
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
                    _LINK_CARD_SELECT +
                    " WHERE l.version_gid=%s AND l.entry_gid=%s AND l.is_deleted=0"
                    " AND l.deleted_at IS NULL ORDER BY l.is_primary DESC,l.link_type,l.entity_gid LIMIT %s",
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
        detail = _normalize_entry_fields(detail)
        detail = _add_primary_projection(detail, links)
        return {
            "version_gid": version_gid, "revision": revision,
            "entry": detail, "links": [_public_link(link, include_snapshot=True) for link in links],
        }

    def resolve_entry_reference(self, entry_gid: str) -> dict[str, Any]:
        """Resolve the current BOP version/revision needed by the legacy route."""
        with self._connection_factory() as connection:
            with connection.cursor() as db:
                db.execute(
                    "SELECT e.version_gid, v.revision "
                    "FROM workmanship_bop_bop_entries e "
                    "JOIN workmanship_bop_bop_versions v ON v.gid = e.version_gid "
                    "WHERE e.gid=%s AND e.is_deleted=0",
                    (entry_gid,),
                )
                row = db.fetchone()
        if not row:
            raise _error("entry_not_found", "BOP entry was not found", entry_gid=entry_gid)
        return {"version_gid": str(row["version_gid"]), "revision": int(row["revision"])}


repository = BopNavigationRepository()


__all__ = ["BopNavigationRepository", "decode_cursor", "encode_cursor", "repository"]
