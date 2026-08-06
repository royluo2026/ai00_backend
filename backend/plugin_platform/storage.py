"""Tenant/plugin isolated JSON key-value storage capabilities."""
from __future__ import annotations

import json
from typing import Any

from backend.capabilities.models_next import CapabilityRisk, CapabilitySpec

MAX_VALUE_BYTES = 256 * 1024
MAX_LIST_LIMIT = 200


def _identity(context) -> tuple[str, str]:
    plugin_id = getattr(context, "plugin_id", None)
    if context.source != "plugin" or not plugin_id:
        raise PermissionError("plugin namespace storage requires an authorized plugin context")
    return context.team_gid or f"user:{context.user_gid}", str(plugin_id)


def _key(payload: dict) -> str:
    value = str(payload.get("key", "")).strip()
    if not value or len(value) > 512 or value.startswith("/") or ".." in value.split("/"):
        raise ValueError("storage key must be a safe relative key up to 512 characters")
    return value


def _encoded(value: Any) -> str:
    result = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    if len(result.encode("utf-8")) > MAX_VALUE_BYTES:
        raise ValueError("plugin storage value exceeds 256 KiB")
    return result


def get_value(payload: dict, context) -> dict:
    tenant, plugin_id = _identity(context); key = _key(payload)
    from backend.db.connection import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT value_json,version,updated_at FROM workmanship_plugin_namespace_kv "
                "WHERE tenant_gid=%s AND plugin_id=%s AND storage_key=%s",
                (tenant, plugin_id, key),
            )
            row = cur.fetchone()
    if not row:
        raise LookupError("plugin storage key not found")
    value = row["value_json"] if not isinstance(row["value_json"], str) else json.loads(row["value_json"])
    updated = row.get("updated_at")
    return {"key": key, "value": value, "version": int(row["version"]), "updated_at": updated.isoformat() if hasattr(updated, "isoformat") else str(updated or "")}


def list_values(payload: dict, context) -> dict:
    tenant, plugin_id = _identity(context)
    prefix = str(payload.get("prefix", ""))
    limit = max(1, min(int(payload.get("limit") or 100), MAX_LIST_LIMIT))
    from backend.db.connection import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT storage_key,version,updated_at FROM workmanship_plugin_namespace_kv "
                "WHERE tenant_gid=%s AND plugin_id=%s AND storage_key LIKE %s "
                "ORDER BY storage_key LIMIT %s",
                (tenant, plugin_id, prefix + "%", limit),
            )
            rows = [dict(row) for row in cur.fetchall()]
    for row in rows:
        row["key"] = row.pop("storage_key")
        updated = row.get("updated_at")
        row["updated_at"] = updated.isoformat() if hasattr(updated, "isoformat") else str(updated or "")
    return {"items": rows, "limit": limit}


def put_value(payload: dict, context) -> dict:
    tenant, plugin_id = _identity(context); key = _key(payload); encoded = _encoded(payload.get("value"))
    expected = payload.get("expected_version")
    from backend.db.connection import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT version FROM workmanship_plugin_namespace_kv WHERE tenant_gid=%s AND plugin_id=%s AND storage_key=%s FOR UPDATE",
                (tenant, plugin_id, key),
            )
            row = cur.fetchone()
            if row:
                current = int(row["version"])
                if expected is not None and int(expected) != current:
                    raise ValueError(f"plugin storage version conflict: expected {expected}, current {current}")
                version = current + 1
                cur.execute(
                    "UPDATE workmanship_plugin_namespace_kv SET value_json=%s,version=%s,updated_by=%s "
                    "WHERE tenant_gid=%s AND plugin_id=%s AND storage_key=%s",
                    (encoded, version, context.user_gid, tenant, plugin_id, key),
                )
            else:
                if expected not in (None, 0):
                    raise ValueError("plugin storage version conflict: key does not exist")
                version = 1
                cur.execute(
                    "INSERT INTO workmanship_plugin_namespace_kv "
                    "(tenant_gid,plugin_id,storage_key,value_json,version,created_by,updated_by) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (tenant, plugin_id, key, encoded, version, context.user_gid, context.user_gid),
                )
        conn.commit()
    return {"key": key, "version": version}


def delete_value(payload: dict, context) -> dict:
    tenant, plugin_id = _identity(context); key = _key(payload)
    expected = payload.get("expected_version")
    from backend.db.connection import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT version FROM workmanship_plugin_namespace_kv WHERE tenant_gid=%s AND plugin_id=%s AND storage_key=%s FOR UPDATE",
                (tenant, plugin_id, key),
            )
            row = cur.fetchone()
            if not row:
                return {"key": key, "deleted": False}
            if expected is not None and int(expected) != int(row["version"]):
                raise ValueError(f"plugin storage version conflict: expected {expected}, current {row['version']}")
            cur.execute(
                "DELETE FROM workmanship_plugin_namespace_kv WHERE tenant_gid=%s AND plugin_id=%s AND storage_key=%s",
                (tenant, plugin_id, key),
            )
        conn.commit()
    return {"key": key, "deleted": True}


def register_plugin_storage_capabilities(registry) -> None:
    key_schema = {"type": "object", "required": ["key"], "properties": {"key": {"type": "string"}}, "additionalProperties": False}
    list_schema = {"type": "object", "properties": {"prefix": {"type": "string"}, "limit": {"type": "integer"}}, "additionalProperties": False}
    put_schema = {"type": "object", "required": ["key", "value"], "properties": {"key": {"type": "string"}, "value": {}, "expected_version": {"type": "integer"}}, "additionalProperties": False}
    delete_schema = {"type": "object", "required": ["key"], "properties": {"key": {"type": "string"}, "expected_version": {"type": "integer"}}, "additionalProperties": False}
    common = {"version": 1, "owner": "plugin", "plugin_callable": True, "output_schema": {"type": "object"}, "tags": ("plugin", "storage")}
    registry.register(CapabilitySpec(id="plugin.storage.get", description="Read a value from the caller plugin namespace.", input_schema=key_schema, **common), get_value)
    registry.register(CapabilitySpec(id="plugin.storage.list", description="List keys in the caller plugin namespace.", input_schema=list_schema, **common), list_values)
    registry.register(CapabilitySpec(id="plugin.storage.put", description="Create or replace a value using optimistic versioning.", risk=CapabilityRisk.WRITE, idempotent=False, input_schema=put_schema, **common), put_value)
    registry.register(CapabilitySpec(id="plugin.storage.delete", description="Delete a value using optional optimistic versioning.", risk=CapabilityRisk.WRITE, idempotent=True, input_schema=delete_schema, **common), delete_value)