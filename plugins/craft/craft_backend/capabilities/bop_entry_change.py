"""Governed update and soft-delete of BOP main-tree entries."""
from __future__ import annotations

import json
import re
from typing import Any

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext, CapabilitySpec
from plugins.ontology.public import active_projection

from ..data.connection import get_craft_conn
from ..rule_engine.checker import validate_with_proposed
from ..routers._bop._constants import _AI00_LEVEL, _ENTRY_BY_GID_SQL, _LINK_TARGET_TABLES
from ..routers._bop._helpers import _check_line_editable, _log_entry_op, _sync_child_vpps


OPERATIONS = ("update", "delete")
_UPDATE_FIELDS = frozenset({"parent_gid", "node_type", "sort_order", "title", "vpps", "vpps_desc", "parent_bop_title", "process_flow_pic", "process_chart_pic", "cad_sim_pics", "meta"})
_OWNED_ENTITY_TYPES = frozenset({"bop_line", "bop_station", "bop_process", "bop_steps", "bop_operator"})
_ENTITY_TITLE_SYNC = {
    "bop_line": ("workmanship_bop_bop_line", "title"),
    "bop_station": ("workmanship_bop_bop_station", "title"),
    "bop_process": ("workmanship_bop_bop_process", "name"),
    "bop_steps": ("workmanship_bop_bop_steps", "title"),
    "bop_operator": ("workmanship_bop_bop_operator", "title"),
}
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ENTITY_PROP_DENY = frozenset({
    "gid", "created_at", "updated_at", "deleted_at", "project_gid",
    "bop_version_gid", "version_gid", "vpps", "created_by", "title",
})


def _required(payload: dict[str, Any], name: str) -> str:
    value = str(payload.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _property_map(items: Any) -> dict[str, Any]:
    if items is None:
        return {}
    if not isinstance(items, list):
        raise ValueError("properties must be an array")
    result: dict[str, Any] = {}
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("each property update must be an object")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("property name is required")
        name = name.strip()
        if name in result:
            raise ValueError(f"duplicate property: {name}")
        if "value" not in item:
            raise ValueError(f"property value is required: {name}")
        result[name] = item["value"]
    return result


def _user(context: CapabilityContext) -> dict[str, Any]:
    roles = set(context.active_roles or ())
    org_role = next((role for role in ("super_admin", "team_admin", "project_admin", "member") if role in roles), None)
    return {"gid": context.user_gid, "name": context.user_gid, "org_role": org_role or "external"}


def _ensure_editable(cur: Any, version_gid: str, entry_gid: str, context: CapabilityContext) -> None:
    cur.execute("SELECT status FROM workmanship_bop_bop_versions WHERE gid=%s", (version_gid,))
    version = cur.fetchone()
    if not version:
        raise CapabilityBusinessError("resource_not_found", f"BOP version {version_gid} does not exist")
    status = version.get("status") if isinstance(version, dict) else dict(version)["status"]
    if status != "active":
        raise CapabilityBusinessError("invalid_state", f"version {version_gid} is not editable (current: {status})")
    try:
        _check_line_editable(cur, version_gid, entry_gid, _user(context))
    except HTTPException as exc:
        raise CapabilityBusinessError("permission_denied", str(exc.detail)) from exc


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, default=str)


def _json_object_base_expr(column: str) -> str:
    if not _IDENTIFIER_RE.fullmatch(column):
        raise ValueError("invalid JSON column identifier")
    return (
        f"CASE WHEN {column} IS NULL OR JSON_TYPE({column})='NULL' "
        f"THEN JSON_OBJECT() ELSE {column} END"
    )


def _property_contracts(node_type: str) -> dict[str, dict[str, Any]]:
    projection = active_projection()
    concepts = {
        str(item.get("stable_gid")): item
        for item in projection.get("concept", [])
        if item.get("stable_gid") and not item.get("deprecated")
    }
    concept = next(
        (item for item in concepts.values() if item.get("node_type_binding") == node_type),
        None,
    )
    if not concept:
        raise CapabilityBusinessError(
            "ontology_contract_missing",
            f"No active Ontology concept is bound to node_type {node_type!r}",
        )
    class_gids: set[str] = set()
    current = concept
    while current:
        stable_gid = str(current.get("stable_gid") or "")
        if not stable_gid or stable_gid in class_gids:
            break
        class_gids.add(stable_gid)
        parent_gid = str(current.get("parent_stable_gid") or current.get("parent_gid") or "")
        current = concepts.get(parent_gid)

    result: dict[str, dict[str, Any]] = {}
    for item in projection.get("property", []):
        class_gid = str(item.get("class_stable_gid") or item.get("class_gid") or "")
        if class_gid not in class_gids or item.get("deprecated"):
            continue
        name = str(item.get("name") or "").strip()
        db_key = str(item.get("mapped_column") or name).strip()
        if not _IDENTIFIER_RE.fullmatch(name) or not _IDENTIFIER_RE.fullmatch(db_key):
            raise CapabilityBusinessError(
                "invalid_ontology_contract",
                f"Ontology property {item.get('stable_gid') or name!r} has an unsafe storage identifier",
            )
        result[name] = {**dict(item), "name": name, "db_key": db_key, "storage_hint": item.get("storage_hint") or "auto"}
    return result


def _validate_property_value(name: str, value: Any, contract: dict[str, Any]) -> None:
    if value in (None, ""):
        if contract.get("required"):
            raise CapabilityBusinessError("property_validation_failed", f"{name}: required")
        return
    data_type = contract.get("data_type") or contract.get("value_type")
    if data_type in {"integer", "float", "number"}:
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise CapabilityBusinessError("property_validation_failed", f"{name}: must be numeric") from exc
        if contract.get("min_val") is not None and number < float(contract["min_val"]):
            raise CapabilityBusinessError("property_validation_failed", f"{name}: below minimum")
        if contract.get("max_val") is not None and number > float(contract["max_val"]):
            raise CapabilityBusinessError("property_validation_failed", f"{name}: above maximum")
    if data_type == "enum":
        allowed = contract.get("enum_values") or []
        if isinstance(allowed, str):
            try:
                allowed = json.loads(allowed)
            except (TypeError, ValueError):
                allowed = []
        if allowed and value not in allowed:
            raise CapabilityBusinessError("property_validation_failed", f"{name}: value is not in the allowed enum")


def _validate_property_updates(node_type: str, properties: dict[str, Any]) -> dict[str, dict[str, Any]]:
    contracts = _property_contracts(node_type)
    for name, value in properties.items():
        if name in _ENTITY_PROP_DENY or name.startswith("_") or name not in contracts:
            raise CapabilityBusinessError("undeclared_property", f"undeclared_property: {name!r} is not declared for {node_type!r}")
        contract = contracts[name]
        if contract.get("storage_hint") == "derived":
            raise CapabilityBusinessError("read_only_property", f"read_only_property: {name!r} is derived and cannot be written")
        _validate_property_value(name, value, contract)
    return contracts


def _validate_property_rules(
    *,
    node_type: str,
    entry_gid: str,
    properties: dict[str, Any],
    contracts: dict[str, dict[str, Any]],
    conn: Any,
) -> list[dict[str, Any]]:
    proposed: dict[str, Any] = {}
    for name, value in properties.items():
        proposed[name] = value
        proposed[str(contracts[name]["db_key"])] = value
    violations = validate_with_proposed(node_type, entry_gid, proposed, conn=conn)
    mandatory = [item for item in violations if item.get("enforcement_level") == "mandatory"]
    if mandatory:
        messages = "; ".join(str(item.get("message") or item.get("rule_name") or "rule failed") for item in mandatory)
        raise CapabilityBusinessError("rule_validation_failed", messages)
    return [item for item in violations if item.get("enforcement_level") != "mandatory"]


def _real_columns(cur: Any, table: str) -> set[str]:
    cur.execute(
        "SELECT COLUMN_NAME AS column_name FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s",
        (table,),
    )
    return {str(row["column_name"]) for row in cur.fetchall()}


def _update_json_property(cur: Any, *, table: str, column: str, key: str, value: Any, gid: str, has_updated_at: bool) -> None:
    timestamp = ", updated_at=NOW()" if has_updated_at else ""
    if value is None:
        cur.execute(
            f"UPDATE {table} SET {column}=JSON_REMOVE({_json_object_base_expr(column)}, CONCAT('$.', %s)){timestamp} WHERE gid=%s",
            (key, gid),
        )
    else:
        cur.execute(
            f"UPDATE {table} SET {column}=JSON_SET({_json_object_base_expr(column)}, CONCAT('$.', %s), CAST(%s AS JSON)){timestamp} WHERE gid=%s",
            (key, json.dumps(value, ensure_ascii=False, default=str), gid),
        )


def _persist_property_updates(
    cur: Any,
    *,
    entry_gid: str,
    entity_table: str | None,
    entity_gid: str | None,
    contracts: dict[str, dict[str, Any]],
    properties: dict[str, Any],
) -> None:
    if entity_table and entity_gid:
        cur.execute(f"SELECT gid FROM {entity_table} WHERE gid=%s LIMIT 1", (entity_gid,))
        if not cur.fetchone():
            raise CapabilityBusinessError(
                "resource_not_found",
                f"Primary linked entity {entity_gid} does not exist",
            )
    real_columns = _real_columns(cur, entity_table) if entity_table and entity_gid else set()
    has_ext = "ext" in real_columns
    has_updated_at = "updated_at" in real_columns
    fixed: dict[str, Any] = {}
    ext: dict[str, Any] = {}
    meta: dict[str, Any] = {}
    for name, value in properties.items():
        contract = contracts[name]
        db_key = str(contract["db_key"])
        if contract.get("storage_hint") == "meta" or not entity_table or not entity_gid:
            meta[name] = value
        elif db_key in real_columns:
            fixed[db_key] = value
        elif has_ext:
            ext[db_key] = value
        else:
            meta[name] = value

    if fixed:
        sets = [f"`{column}`=%s" for column in fixed]
        if has_updated_at:
            sets.append("updated_at=NOW()")
        cur.execute(
            f"UPDATE {entity_table} SET {', '.join(sets)} WHERE gid=%s",
            (*fixed.values(), entity_gid),
        )
    for key, value in ext.items():
        _update_json_property(
            cur, table=str(entity_table), column="ext", key=key, value=value,
            gid=str(entity_gid), has_updated_at=has_updated_at,
        )
    for key, value in meta.items():
        _update_json_property(
            cur, table="workmanship_bop_bop_entries", column="meta", key=key, value=value,
            gid=entry_gid, has_updated_at=True,
        )


def apply_bop_entry_change(payload: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
    operation = str(payload.get("operation") or "").strip()
    if operation not in OPERATIONS:
        raise ValueError(f"operation must be one of: {', '.join(OPERATIONS)}")
    entry_gid = _required(payload, "entry_gid")
    if operation == "update":
        updates = payload.get("updates")
        properties = payload.get("properties")
        if updates is not None and not isinstance(updates, dict):
            raise ValueError("updates must be an object")
        properties = _property_map(properties)
        if not updates and not properties:
            if "updates" in payload:
                raise ValueError("updates must be a non-empty object")
            raise ValueError("properties must be a non-empty object")
        unknown = set(updates or {}) - _UPDATE_FIELDS
        if unknown:
            raise ValueError(f"unsupported update fields: {', '.join(sorted(unknown))}")

    with get_craft_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT e.gid,e.version_gid,e.parent_gid,e.node_type,e.title,e.vpps,e.vpps_desc,e.parent_bop_title,"
            "e.process_flow_pic,e.process_chart_pic,e.meta "
            "FROM workmanship_bop_bop_entries e WHERE e.gid=%s AND e.is_deleted=FALSE",
            (entry_gid,),
        )
        row = cur.fetchone()
        if not row:
            raise CapabilityBusinessError("resource_not_found", f"BOP entry {entry_gid} does not exist")
        entry = dict(row)
        version_gid = str(entry["version_gid"])
        _ensure_editable(cur, version_gid, entry_gid, context)

        if operation == "update":
            updates = dict(updates or {})
            properties = dict(properties or {})
            sets: list[str] = []
            values: list[Any] = []
            for name in ("parent_gid", "node_type", "sort_order", "title", "vpps", "vpps_desc", "parent_bop_title"):
                if name in updates:
                    sets.append(f"{name}=%s")
                    values.append(updates[name])
            if "node_type" in updates:
                sets.append("ai00_level=%s")
                values.append(_AI00_LEVEL.get(updates["node_type"]))
            if "process_flow_pic" in updates:
                sets.append("process_flow_pic=%s")
                values.append(_json(updates["process_flow_pic"]))
            if "process_chart_pic" in updates:
                sets.append("process_chart_pic=%s")
                values.append(_json(updates["process_chart_pic"]))
            if "cad_sim_pics" in updates:
                sets.append("meta=JSON_SET(IFNULL(meta,'{}'),'$.cad_sim_pics',CAST(%s AS JSON))")
                values.append(_json(updates["cad_sim_pics"]))
            elif "meta" in updates:
                sets.append("meta=CAST(%s AS JSON)")
                values.append(_json(updates["meta"]))
            if sets:
                sets.append("updated_at=NOW()")
                cur.execute(f"UPDATE workmanship_bop_bop_entries SET {', '.join(sets)} WHERE gid=%s AND is_deleted=FALSE", [*values, entry_gid])
                if cur.rowcount == 0:
                    cur.execute(
                        "SELECT 1 AS present FROM workmanship_bop_bop_entries "
                        "WHERE gid=%s AND is_deleted=FALSE",
                        (entry_gid,),
                    )
                    if not cur.fetchone():
                        raise CapabilityBusinessError("resource_not_found", f"BOP entry {entry_gid} does not exist")
            if properties:
                contracts = _validate_property_updates(str(entry["node_type"]), properties)
                advisory = _validate_property_rules(
                    node_type=str(entry["node_type"]), entry_gid=entry_gid,
                    properties=properties, contracts=contracts, conn=conn,
                )
                cur.execute(
                    "SELECT entity_gid,link_type FROM workmanship_bop_bop_entry_links "
                    "WHERE entry_gid=%s AND is_primary=TRUE AND deleted_at IS NULL LIMIT 1",
                    (entry_gid,),
                )
                primary = dict(cur.fetchone() or {})
                target = _LINK_TARGET_TABLES.get(primary.get("link_type"))
                _persist_property_updates(
                    cur,
                    entry_gid=entry_gid,
                    entity_table=target[0] if target else None,
                    entity_gid=primary.get("entity_gid"),
                    contracts=contracts,
                    properties=properties,
                )
            if "title" in updates:
                cur.execute("SELECT entity_gid,link_type FROM workmanship_bop_bop_entry_links WHERE entry_gid=%s AND is_primary=TRUE LIMIT 1", (entry_gid,))
                link = cur.fetchone()
                if link:
                    link = dict(link)
                    sync = _ENTITY_TITLE_SYNC.get(link.get("link_type"))
                    if sync:
                        cur.execute(f"UPDATE {sync[0]} SET {sync[1]}=%s WHERE gid=%s", (updates["title"], link["entity_gid"]))
            if "parent_gid" in updates and updates["parent_gid"] and updates["parent_gid"] != entry.get("parent_gid"):
                _sync_child_vpps(cur, updates["parent_gid"], version_gid)
            _log_entry_op(cur, version_gid=version_gid, entry_gid=entry_gid, entry_title=str(updates.get("title") or entry.get("title") or ""), op_type="update_entry",
                          old_state=entry, new_state={**updates, "properties": properties} if properties else updates, user_gid=context.user_gid, user_name=context.user_gid)
            cur.execute(_ENTRY_BY_GID_SQL, (entry_gid,))
            result = jsonable_encoder({"data": dict(cur.fetchone() or {}), "version_gid": version_gid})
            if properties and advisory:
                result["warnings"] = jsonable_encoder(advisory)
            conn.commit()
            return result

        cur.execute("SELECT parent_gid,title,node_type,vpps FROM workmanship_bop_bop_entries WHERE gid=%s", (entry_gid,))
        current = dict(cur.fetchone() or {})
        cur.execute("UPDATE workmanship_bop_bop_entries SET is_deleted=TRUE,deleted_at=NOW() WHERE gid=%s AND is_deleted=FALSE", (entry_gid,))
        if cur.rowcount == 0:
            raise CapabilityBusinessError("resource_not_found", f"BOP entry {entry_gid} does not exist")
        cur.execute("SELECT entity_gid,link_type,is_primary FROM workmanship_bop_bop_entry_links WHERE entry_gid=%s AND deleted_at IS NULL", (entry_gid,))
        links = [dict(item) for item in cur.fetchall()]
        for link in links:
            if link.get("link_type") not in _OWNED_ENTITY_TYPES:
                continue
            table_info = _LINK_TARGET_TABLES.get(link["link_type"])
            if table_info:
                cur.execute(
                    f"UPDATE {table_info[0]} SET is_deleted=TRUE, deleted_at=NOW() "
                    f"WHERE {table_info[1]}=%s AND is_deleted=FALSE AND deleted_at IS NULL",
                    (link["entity_gid"],),
                )
        cur.execute(
            "UPDATE workmanship_bop_bop_entry_links "
            "SET is_deleted=TRUE, deleted_at=NOW() "
            "WHERE entry_gid=%s AND is_deleted=FALSE AND deleted_at IS NULL",
            (entry_gid,),
        )
        if current.get("parent_gid"):
            _sync_child_vpps(cur, current["parent_gid"], version_gid)
        _log_entry_op(cur, version_gid=version_gid, entry_gid=entry_gid, entry_title=current.get("title") or "", op_type="delete_entry",
                      old_state={**current, "links": links}, new_state=None, user_gid=context.user_gid, user_name=context.user_gid)
        conn.commit()
    return {"data": {"deleted": True, "gid": entry_gid}, "version_gid": version_gid}


def register_bop_entry_change_capability(registry: Any) -> None:
    registry.register(CapabilitySpec(
        id="craft.bop.entry.change.apply", owner="craft",
        description="Update or soft-delete an active BOP main-tree entry with linked-entity and audit semantics.",
        use_when="A governed Craft consumer edits fields on, or removes, one active BOP entry.",
        do_not_use_when="The request creates/copies/imports entries, changes links only, or operates on staging.",
        risk="write", confirmation="user", idempotent=True, permissions=("craft.write",),
        input_schema={"type": "object", "required": ["operation", "entry_gid"], "additionalProperties": False},
        output_schema={"type": "object", "additionalProperties": True},
        tags=("craft", "bop", "entry", "write"),
    ), apply_bop_entry_change)


__all__ = ["OPERATIONS", "apply_bop_entry_change", "register_bop_entry_change_capability"]
