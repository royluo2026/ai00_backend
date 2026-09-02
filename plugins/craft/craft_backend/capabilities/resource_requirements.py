"""Atomic governed outcomes for Craft process resource standards."""
from __future__ import annotations

import json
from typing import Any, Callable

from pymysql.err import IntegrityError

from backend.capability_v2.provider_contracts import (
    CapabilityBusinessError,
    CapabilityCollectionPolicy,
    CapabilityContext,
    CapabilityExecutionBudget,
    CapabilityOutput,
    CapabilitySpec,
)
from backend.platform_sdk.ids import next_gid

from ..data.connection import get_conn

RESOURCE_TYPES = ("socket", "tool", "fixture", "equipment")
RESOURCE_LINK_TYPES = {
    "socket": "resource_socket",
    "tool": "resource_tool",
    "fixture": "resource_fixture",
    "equipment": "resource_equipment",
}
PENDING_STATES = ("pending", "unmatched", "ambiguous")
RESOURCE_TYPES_BY_LINK = {link_type: resource_type for resource_type, link_type in RESOURCE_LINK_TYPES.items()}
TC_RESOURCE_NODES = {
    "socket_need": ("socket", "resource_socket"),
    "equipment_need": ("equipment", "resource_equipment"),
    "fixture_need": ("fixture", "resource_fixture"),
    "tool_need": ("tool", "resource_tool"),
}


def normalize_resource_type(value: Any) -> str:
    resource_type = str(value or "").strip().lower()
    if resource_type not in RESOURCE_TYPES:
        raise ValueError("resource_type must be socket, tool, fixture, or equipment")
    return resource_type


def normalize_nonblank(value: Any, field: str, max_length: int) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > max_length:
        raise ValueError(f"{field} must be nonblank and at most {max_length} characters")
    return normalized


def normalize_resource_match_value(value: Any) -> str:
    return str(value or "").strip().casefold()


def validate_resource_link(link_type: str, resource_gid: str, cur: Any) -> None:
    """Require an active standard resource whose semantic type matches the BOP link."""
    expected_type = RESOURCE_TYPES_BY_LINK.get(str(link_type or "").strip())
    if not expected_type:
        raise CapabilityBusinessError("resource_link_type_invalid", "The BOP resource link type is not supported.")
    cur.execute(
        "SELECT resource_type,status FROM workmanship_craft_resource_requirements WHERE gid=%s FOR UPDATE",
        (normalize_nonblank(resource_gid, "resource_gid", 128),),
    )
    row = cur.fetchone()
    if not row or row["status"] != "active":
        raise CapabilityBusinessError("resource_not_found", "The active resource does not exist.")
    if row["resource_type"] != expected_type:
        raise CapabilityBusinessError("resource_type_mismatch", "The resource type does not match the BOP link type.")


def ensure_resource_not_referenced(cur: Any, resource_gid: str) -> None:
    cur.execute(
        "SELECT 1 AS used FROM workmanship_bop_bop_entry_links "
        "WHERE entity_gid=%s AND deleted_at IS NULL LIMIT 1",
        (resource_gid,),
    )
    if cur.fetchone():
        raise CapabilityBusinessError("resource_in_use", "The resource is still linked to an active BOP entry.")
    cur.execute(
        "SELECT 1 AS used FROM workmanship_craft_tc_resource_staging "
        "WHERE matched_resource_gid=%s AND match_status='resolved' LIMIT 1",
        (resource_gid,),
    )
    if cur.fetchone():
        raise CapabilityBusinessError("resource_in_use", "The resource is still referenced by a resolved TC staging row.")


def resolve_tc_resource_for_import(
    cur: Any,
    version_gid: str,
    entry_gid: str,
    node_type: str,
    raw: dict[str, Any],
) -> tuple[str | None, str | None]:
    """Resolve a TC resource node to one active standard or persist it for review."""
    if node_type not in TC_RESOURCE_NODES:
        raise ValueError("node_type is not a TC resource node")
    resource_type, _link_type = TC_RESOURCE_NODES[node_type]
    raw_code = str(raw.get("resource_code") or raw.get("code") or raw.get("vpps") or "").strip()
    raw_name = str(raw.get("resource_name") or raw.get("name") or raw.get("title") or "").strip()
    raw_model = str(raw.get("model") or raw.get("preferred_model") or raw.get("vpps_desc") or "").strip()

    if raw_code:
        cur.execute(
            "SELECT gid FROM workmanship_craft_resource_requirements "
            "WHERE resource_type=%s AND status='active' AND BINARY code=%s LIMIT 1",
            (resource_type, raw_code),
        )
        exact = cur.fetchone()
        if exact:
            return exact["gid"], None

    normalized = list(dict.fromkeys(filter(None, (
        normalize_resource_match_value(raw_code),
        normalize_resource_match_value(raw_name),
        normalize_resource_match_value(raw_model),
    ))))
    candidates: list[str] = []
    if normalized:
        placeholders = ",".join(["%s"] * len(normalized))
        cur.execute(
            "SELECT r.gid FROM workmanship_craft_resource_aliases a "
            "JOIN workmanship_craft_resource_requirements r ON r.gid=a.resource_gid "
            f"WHERE r.resource_type=%s AND r.status='active' AND a.normalized_value IN ({placeholders}) "
            "ORDER BY r.gid",
            (resource_type, *normalized),
        )
        candidates = sorted({row["gid"] for row in cur.fetchall()})
        if len(candidates) == 1:
            return candidates[0], None

    staging_gid = str(next_gid())
    cur.execute(
        "INSERT INTO workmanship_craft_tc_resource_staging "
        "(gid,version_gid,entry_gid,resource_type,raw_name,raw_payload,match_status,candidate_resource_gids) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            staging_gid, version_gid, entry_gid, resource_type,
            (raw_name or raw_code or raw_model or node_type)[:255],
            json.dumps(raw, ensure_ascii=False, default=str),
            "ambiguous" if candidates else "unmatched",
            json.dumps(candidates),
        ),
    )
    return None, staging_gid


def _json(value: Any, default: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return default if value is None else value


def _transport(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    for key in ("attributes", "raw_payload", "candidate_resource_gids"):
        if key in result:
            result[key] = _json(result[key], {} if key != "candidate_resource_gids" else [])
    for key, value in tuple(result.items()):
        if hasattr(value, "isoformat"):
            result[key] = value.isoformat()
    attributes = result.get("attributes")
    if isinstance(attributes, dict) and isinstance(attributes.get("legacy_spec"), (dict, list)):
        attributes["legacy_spec"] = json.dumps(attributes["legacy_spec"], ensure_ascii=False, sort_keys=True)
    return result


def _page_size(payload: dict[str, Any]) -> int:
    value = int(payload.get("page_size") or 100)
    if not 1 <= value <= 200:
        raise CapabilityBusinessError("invalid_page_size", "page_size must be between 1 and 200")
    return value


def search_resource_requirements(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    page_size = _page_size(payload)
    clauses = []
    params: list[Any] = []
    if payload.get("resource_type"):
        clauses.append("resource_type=%s")
        params.append(normalize_resource_type(payload["resource_type"]))
    status = str(payload.get("status") or "active").strip()
    if status not in {"active", "retired", "all"}:
        raise ValueError("status must be active, retired, or all")
    if status != "all":
        clauses.append("status=%s")
        params.append(status)
    query = str(payload.get("q") or "").strip()
    if query:
        clauses.append("(code LIKE %s OR name LIKE %s)")
        params.extend((f"%{query}%", f"%{query}%"))
    cursor = str(payload.get("cursor") or "").strip()
    if cursor:
        clauses.append("gid>%s")
        params.append(cursor)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid,resource_type,code,name,attributes,source,status,resource_version,"
                "created_by,updated_by,created_at,updated_at FROM workmanship_craft_resource_requirements"
                f"{where} ORDER BY gid LIMIT %s",
                tuple((*params, page_size + 1)),
            )
            rows = [_transport(dict(row)) for row in cur.fetchall()]
            page = rows[:page_size]
            aliases = {row["gid"]: [] for row in page}
            if aliases:
                gids = list(aliases)
                cur.execute(
                    "SELECT gid,resource_gid,alias_value,normalized_value,created_at,updated_at "
                    f"FROM workmanship_craft_resource_aliases WHERE resource_gid IN ({','.join(['%s'] * len(gids))}) "
                    "ORDER BY resource_gid,normalized_value",
                    tuple(gids),
                )
                for alias in cur.fetchall():
                    item = _transport(dict(alias))
                    aliases[item["resource_gid"]].append(item)
            for row in page:
                row["aliases"] = aliases[row["gid"]]
    return CapabilityOutput(data={"items": page, "next_cursor": page[-1]["gid"] if len(rows) > page_size else None})


def create_resource_requirement(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    resource_type = normalize_resource_type(payload.get("resource_type"))
    code = normalize_nonblank(payload.get("code"), "code", 128)
    name = normalize_nonblank(payload.get("name"), "name", 255)
    attributes = payload.get("attributes", {})
    if not isinstance(attributes, dict):
        raise ValueError("attributes must be an object")
    source = normalize_nonblank(payload.get("source") or "manual", "source", 255)
    gid = str(next_gid())
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO workmanship_craft_resource_requirements "
                    "(gid,resource_type,code,name,attributes,source,created_by,updated_by) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (gid, resource_type, code, name, json.dumps(attributes, ensure_ascii=False), source, context.user_gid, context.user_gid),
                )
            conn.commit()
    except IntegrityError as error:
        raise CapabilityBusinessError("resource_code_conflict", "A resource with this type and code already exists.") from error
    return CapabilityOutput(data={"gid": gid, "resource_version": 1, "status": "active"})


def update_resource_requirement(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    gid = normalize_nonblank(payload.get("gid"), "gid", 128)
    expected = payload.get("expected_resource_version")
    if not isinstance(expected, int) or expected < 1:
        raise ValueError("expected_resource_version is required")
    changes: dict[str, Any] = {}
    if "code" in payload:
        changes["code"] = normalize_nonblank(payload["code"], "code", 128)
    if "name" in payload:
        changes["name"] = normalize_nonblank(payload["name"], "name", 255)
    if "attributes" in payload:
        if not isinstance(payload["attributes"], dict):
            raise ValueError("attributes must be an object")
        changes["attributes"] = json.dumps(payload["attributes"], ensure_ascii=False)
    if not changes:
        raise ValueError("at least one update field is required")
    assignments = [f"{key}=%s" for key in changes]
    params = [*changes.values(), context.user_gid, gid, expected]
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE workmanship_craft_resource_requirements SET {','.join(assignments)},"
                    "updated_by=%s,resource_version=resource_version+1 WHERE gid=%s AND status='active' AND resource_version=%s",
                    tuple(params),
                )
                if cur.rowcount != 1:
                    raise CapabilityBusinessError("resource_version_conflict", "The resource changed or is not active.")
            conn.commit()
    except IntegrityError as error:
        raise CapabilityBusinessError("resource_code_conflict", "A resource with this type and code already exists.") from error
    return CapabilityOutput(data={"gid": gid, "resource_version": expected + 1})


def retire_resource_requirement(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    gid = normalize_nonblank(payload.get("gid"), "gid", 128)
    expected = payload.get("expected_resource_version")
    if not isinstance(expected, int) or expected < 1:
        raise ValueError("expected_resource_version is required")
    with get_conn() as conn:
        with conn.cursor() as cur:
            ensure_resource_not_referenced(cur, gid)
            cur.execute(
                "UPDATE workmanship_craft_resource_requirements SET status='retired',updated_by=%s,"
                "resource_version=resource_version+1 WHERE gid=%s AND status='active' AND resource_version=%s",
                (context.user_gid, gid, expected),
            )
            if cur.rowcount != 1:
                raise CapabilityBusinessError("resource_version_conflict", "The resource changed or is not active.")
        conn.commit()
    return CapabilityOutput(data={"gid": gid, "status": "retired", "resource_version": expected + 1})


def create_resource_alias(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    resource_gid = normalize_nonblank(payload.get("resource_gid"), "resource_gid", 128)
    alias_value = normalize_nonblank(payload.get("alias_value"), "alias_value", 255)
    normalized = alias_value.casefold()
    gid = str(next_gid())
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT gid FROM workmanship_craft_resource_requirements WHERE gid=%s AND status='active' FOR UPDATE", (resource_gid,))
                if not cur.fetchone():
                    raise CapabilityBusinessError("resource_not_found", "The active resource does not exist.")
                cur.execute(
                    "INSERT INTO workmanship_craft_resource_aliases (gid,resource_gid,alias_value,normalized_value,created_by) VALUES (%s,%s,%s,%s,%s)",
                    (gid, resource_gid, alias_value, normalized, context.user_gid),
                )
            conn.commit()
    except IntegrityError as error:
        raise CapabilityBusinessError("resource_alias_conflict", "This alias already exists for the resource.") from error
    return CapabilityOutput(data={"gid": gid, "resource_gid": resource_gid})


def delete_resource_alias(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    resource_gid = normalize_nonblank(payload.get("resource_gid"), "resource_gid", 128)
    alias_gid = normalize_nonblank(payload.get("alias_gid"), "alias_gid", 128)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM workmanship_craft_resource_aliases WHERE gid=%s AND resource_gid=%s", (alias_gid, resource_gid))
            if cur.rowcount != 1:
                raise CapabilityBusinessError("resource_alias_not_found", "The resource alias does not exist.")
        conn.commit()
    return CapabilityOutput(data={"gid": alias_gid, "resource_gid": resource_gid, "deleted": True})


def search_resource_staging(payload: dict[str, Any], _context: CapabilityContext) -> CapabilityOutput:
    page_size = _page_size(payload)
    clauses, params = [], []
    if payload.get("version_gid"):
        clauses.append("version_gid=%s")
        params.append(normalize_nonblank(payload["version_gid"], "version_gid", 128))
    if payload.get("match_status"):
        clauses.append("match_status=%s")
        params.append(normalize_nonblank(payload["match_status"], "match_status", 16))
    if payload.get("cursor"):
        clauses.append("gid>%s")
        params.append(str(payload["cursor"]))
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM workmanship_craft_tc_resource_staging{where} ORDER BY gid LIMIT %s", tuple((*params, page_size + 1)))
            rows = [_transport(dict(row)) for row in cur.fetchall()]
    page = rows[:page_size]
    return CapabilityOutput(data={"items": page, "next_cursor": page[-1]["gid"] if len(rows) > page_size else None})


def _decide_staging(payload: dict[str, Any], context: CapabilityContext, *, ignored: bool) -> CapabilityOutput:
    staging_gid = normalize_nonblank(payload.get("staging_gid"), "staging_gid", 128)
    expected = payload.get("expected_staging_version")
    if not isinstance(expected, int) or expected < 1:
        raise ValueError("expected_staging_version is required")
    review_note = str(payload.get("review_note") or "").strip() or None
    resource_gid = None if ignored else normalize_nonblank(payload.get("resource_gid"), "resource_gid", 128)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid,version_gid,entry_gid,resource_type,match_status,resource_version "
                "FROM workmanship_craft_tc_resource_staging WHERE gid=%s FOR UPDATE",
                (staging_gid,),
            )
            staging = cur.fetchone()
            if not staging:
                raise CapabilityBusinessError("resource_staging_not_found", "The staging row does not exist.")
            if staging["match_status"] not in PENDING_STATES or int(staging["resource_version"]) != expected:
                raise CapabilityBusinessError("resource_staging_conflict", "The staging row was already decided or changed.")
            link_type = RESOURCE_LINK_TYPES[normalize_resource_type(staging["resource_type"])]
            if resource_gid:
                cur.execute(
                    "SELECT gid,resource_type,status FROM workmanship_craft_resource_requirements WHERE gid=%s FOR UPDATE",
                    (resource_gid,),
                )
                resource = cur.fetchone()
                if not resource or resource["status"] != "active":
                    raise CapabilityBusinessError("resource_not_found", "The active resource does not exist.")
                if resource["resource_type"] != staging["resource_type"]:
                    raise CapabilityBusinessError("resource_type_mismatch", "The resource type does not match the staging row.")
            cur.execute(
                "UPDATE workmanship_bop_bop_entry_links SET deleted_at=NOW(),is_deleted=TRUE "
                "WHERE entry_gid=%s AND link_type=%s AND deleted_at IS NULL",
                (staging["entry_gid"], link_type),
            )
            if resource_gid:
                cur.execute(
                    "INSERT INTO workmanship_bop_bop_entry_links "
                    "(gid,version_gid,entry_gid,entity_gid,link_type,is_primary,is_inherited,is_deleted,is_archived) "
                    "VALUES (%s,%s,%s,%s,%s,TRUE,FALSE,FALSE,FALSE) "
                    "ON DUPLICATE KEY UPDATE version_gid=VALUES(version_gid),is_primary=TRUE,is_inherited=FALSE,is_deleted=FALSE,is_archived=FALSE,deleted_at=NULL",
                    (str(next_gid()), staging["version_gid"], staging["entry_gid"], resource_gid, link_type),
                )
            status = "ignored" if ignored else "resolved"
            cur.execute(
                "UPDATE workmanship_craft_tc_resource_staging SET match_status=%s,matched_resource_gid=%s,review_note=%s,"
                "decided_by=%s,decided_at=NOW(),resource_version=resource_version+1 WHERE gid=%s AND resource_version=%s",
                (status, resource_gid, review_note, context.user_gid, staging_gid, expected),
            )
            if cur.rowcount != 1:
                raise CapabilityBusinessError("resource_staging_conflict", "The staging row changed during review.")
        conn.commit()
    return CapabilityOutput(data={"gid": staging_gid, "status": status, "resource_gid": resource_gid, "resource_version": expected + 1})


def resolve_resource_staging(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    return _decide_staging(payload, context, ignored=False)


def ignore_resource_staging(payload: dict[str, Any], context: CapabilityContext) -> CapabilityOutput:
    return _decide_staging(payload, context, ignored=True)


def _object(properties: dict[str, Any], *required: str) -> dict[str, Any]:
    result = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        result["required"] = list(required)
    return result


STRING = {"type": "string", "minLength": 1}
RESOURCE_TYPE = {"type": "string", "enum": list(RESOURCE_TYPES)}
NULLABLE_STRING = {"type": ["string", "null"]}
ATTRIBUTE_VALUE = {"type": ["string", "number", "boolean", "null"]}
ATTRIBUTES = _object({
    key: ({"type": ["string", "null"]} if key == "legacy_spec" else ATTRIBUTE_VALUE)
    for key in (
        "gun_model", "matou_part_no", "importance", "gun_type", "wireless",
        "output_square", "torque_min", "torque_recommended", "cad_model_no",
        "socket_model", "fastener_type", "fastener_params", "extension_model",
        "socket_cad_no", "extension_cad_no", "category", "legacy_spec",
    )
})
CURSOR = {"anyOf": [{"type": "string"}, {"type": "null"}]}
ALIAS_ROW = _object({
    "gid": STRING, "resource_gid": STRING, "alias_value": STRING,
    "normalized_value": {"type": "string"}, "created_at": {"type": "string"},
    "updated_at": {"type": "string"},
}, "gid", "resource_gid", "alias_value")
RESOURCE_ROW = {
    "type": "object",
    "properties": {
        "gid": STRING, "resource_type": RESOURCE_TYPE, "code": STRING, "name": STRING,
        "attributes": ATTRIBUTES, "source": STRING, "status": {"type": "string", "enum": ["active", "retired"]},
        "resource_version": {"type": "integer", "minimum": 1}, "created_by": {"type": "string"},
        "updated_by": {"type": "string"}, "created_at": {"type": "string"}, "updated_at": {"type": "string"},
        "aliases": {"type": "array", "maxItems": 500, "items": ALIAS_ROW},
    },
    "required": ["gid", "resource_type", "code", "name", "attributes", "source", "status", "resource_version"],
    "additionalProperties": False,
}

TC_RAW_PAYLOAD = _object({
    "_level": {"type": "integer", "minimum": 0}, "ai00_level": {"type": ["integer", "null"]},
    "node_type": {"type": "string"},
    **{key: NULLABLE_STRING for key in (
        "title", "bom_row_label", "bom_row_id", "bom_row_owner", "bop_name",
        "parent_bop_label", "parent_label", "vpps", "vpps_part", "vpps_desc",
        "parent_vpps", "parent_vpps_name", "catia_occurrence_name", "quantity",
        "torque", "torque_importance", "label", "operation_code", "role_type",
        "factory_role_ref_gid", "pbom_version_gid", "resource_code", "code",
        "resource_name", "name", "model", "preferred_model",
    )},
    "headcount": {"type": ["number", "string", "null"]},
    "part_feed": {"type": ["boolean", "string", "null"]},
    "seq_no": {"type": ["number", "string", "null"]},
    "sort_order": {"type": ["number", "string", "null"]},
})
STAGING_ROW = _object({
    "gid": STRING, "version_gid": STRING, "entry_gid": STRING, "resource_type": RESOURCE_TYPE,
    "raw_name": {"type": "string"}, "raw_payload": TC_RAW_PAYLOAD,
    "match_status": {"type": "string", "enum": ["pending", "unmatched", "ambiguous", "resolved", "ignored"]},
    "candidate_resource_gids": {"type": "array", "maxItems": 500, "items": STRING},
    "resolved_resource_gid": CURSOR, "review_note": NULLABLE_STRING,
    "resource_version": {"type": "integer", "minimum": 1}, "created_by": {"type": "string"},
    "decided_by": NULLABLE_STRING, "decided_at": NULLABLE_STRING,
    "created_at": {"type": "string"}, "updated_at": {"type": "string"},
}, "gid", "version_gid", "entry_gid", "resource_type", "raw_name", "raw_payload", "match_status", "candidate_resource_gids", "resource_version")


SCHEMAS: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {
    "craft.resource_requirement.search": (
        _object({"resource_type": RESOURCE_TYPE, "status": {"type": "string", "enum": ["active", "retired", "all"]}, "q": {"type": "string", "maxLength": 200}, "cursor": {"type": "string"}, "page_size": {"type": "integer", "minimum": 1, "maximum": 200}}),
        _object({"items": {"type": "array", "maxItems": 200, "items": RESOURCE_ROW}, "next_cursor": CURSOR}, "items", "next_cursor"),
    ),
    "craft.resource_requirement.create": (
        _object({"resource_type": RESOURCE_TYPE, "code": {"type": "string", "minLength": 1, "maxLength": 128}, "name": {"type": "string", "minLength": 1, "maxLength": 255}, "attributes": ATTRIBUTES, "source": {"type": "string", "minLength": 1, "maxLength": 255}}, "resource_type", "code", "name"),
        _object({"gid": STRING, "resource_version": {"type": "integer"}, "status": {"type": "string"}}, "gid", "resource_version", "status"),
    ),
    "craft.resource_requirement.update": (
        _object({"gid": STRING, "expected_resource_version": {"type": "integer", "minimum": 1}, "code": {"type": "string", "minLength": 1, "maxLength": 128}, "name": {"type": "string", "minLength": 1, "maxLength": 255}, "attributes": ATTRIBUTES}, "gid", "expected_resource_version"),
        _object({"gid": STRING, "resource_version": {"type": "integer"}}, "gid", "resource_version"),
    ),
    "craft.resource_requirement.retire": (
        _object({"gid": STRING, "expected_resource_version": {"type": "integer", "minimum": 1}}, "gid", "expected_resource_version"),
        _object({"gid": STRING, "status": {"type": "string"}, "resource_version": {"type": "integer"}}, "gid", "status", "resource_version"),
    ),
    "craft.resource_requirement.alias.create": (
        _object({"resource_gid": STRING, "alias_value": {"type": "string", "minLength": 1, "maxLength": 255}}, "resource_gid", "alias_value"),
        _object({"gid": STRING, "resource_gid": STRING}, "gid", "resource_gid"),
    ),
    "craft.resource_requirement.alias.delete": (
        _object({"resource_gid": STRING, "alias_gid": STRING}, "resource_gid", "alias_gid"),
        _object({"gid": STRING, "resource_gid": STRING, "deleted": {"type": "boolean"}}, "gid", "resource_gid", "deleted"),
    ),
    "craft.resource_requirement.staging.search": (
        _object({"version_gid": STRING, "match_status": {"type": "string", "maxLength": 16}, "cursor": {"type": "string"}, "page_size": {"type": "integer", "minimum": 1, "maximum": 200}}, "version_gid"),
        _object({"items": {"type": "array", "maxItems": 200, "items": STAGING_ROW}, "next_cursor": CURSOR}, "items", "next_cursor"),
    ),
    "craft.resource_requirement.staging.resolve": (
        _object({"staging_gid": STRING, "resource_gid": STRING, "expected_staging_version": {"type": "integer", "minimum": 1}, "review_note": {"type": "string", "maxLength": 1000}}, "staging_gid", "resource_gid", "expected_staging_version"),
        _object({"gid": STRING, "status": {"type": "string"}, "resource_gid": STRING, "resource_version": {"type": "integer"}}, "gid", "status", "resource_gid", "resource_version"),
    ),
    "craft.resource_requirement.staging.ignore": (
        _object({"staging_gid": STRING, "expected_staging_version": {"type": "integer", "minimum": 1}, "review_note": {"type": "string", "maxLength": 1000}}, "staging_gid", "expected_staging_version"),
        _object({"gid": STRING, "status": {"type": "string"}, "resource_gid": CURSOR, "resource_version": {"type": "integer"}}, "gid", "status", "resource_gid", "resource_version"),
    ),
}


def _spec(capability_id: str, handler: Callable[..., CapabilityOutput]) -> tuple[CapabilitySpec, Callable[..., CapabilityOutput]]:
    is_read = capability_id.endswith(".search")
    noun = capability_id.removeprefix("craft.resource_requirement.")
    input_schema, output_schema = SCHEMAS[capability_id]
    budget = CapabilityExecutionBudget(collection_policy=CapabilityCollectionPolicy.PAGED, max_page_size=200) if is_read else None
    spec = CapabilitySpec(
        id=capability_id,
        owner="craft",
        description=f"Governed Craft resource requirement {noun} outcome.",
        use_when="A governed consumer manages or resolves a Craft process resource requirement standard.",
        do_not_use_when="The object is a physical Factory asset or a legacy VPPS template row.",
        subject_concepts=("craft.resource_requirement",),
        effects=(("read:" if is_read else "write:") + "craft.resource_requirement",),
        risk="read" if is_read else "write",
        confirmation="none" if is_read else "user",
        permissions=("craft.read",) if is_read else ("craft.write",),
        input_schema=input_schema,
        output_schema=output_schema,
        execution_budget=budget,
        tags=("craft", "resource_requirement", noun),
    )
    return spec, handler


def register_resource_requirement_capabilities(registry: Any) -> None:
    handlers = {
        "craft.resource_requirement.search": search_resource_requirements,
        "craft.resource_requirement.create": create_resource_requirement,
        "craft.resource_requirement.update": update_resource_requirement,
        "craft.resource_requirement.retire": retire_resource_requirement,
        "craft.resource_requirement.alias.create": create_resource_alias,
        "craft.resource_requirement.alias.delete": delete_resource_alias,
        "craft.resource_requirement.staging.search": search_resource_staging,
        "craft.resource_requirement.staging.resolve": resolve_resource_staging,
        "craft.resource_requirement.staging.ignore": ignore_resource_staging,
    }
    for capability_id, handler in handlers.items():
        registry.register(*_spec(capability_id, handler))


__all__ = [
    "RESOURCE_LINK_TYPES", "RESOURCE_TYPES_BY_LINK", "TC_RESOURCE_NODES", "SCHEMAS",
    "normalize_nonblank", "normalize_resource_type", "normalize_resource_match_value",
    "validate_resource_link", "ensure_resource_not_referenced", "resolve_tc_resource_for_import",
    "register_resource_requirement_capabilities", "search_resource_requirements",
    "create_resource_requirement", "update_resource_requirement", "retire_resource_requirement",
    "create_resource_alias", "delete_resource_alias", "search_resource_staging",
    "resolve_resource_staging", "ignore_resource_staging",
]
