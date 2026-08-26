"""Base-owned governed runtime database configuration outcomes."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import pymysql

from backend.capability_v2.contracts import ExposurePolicy
from backend.capability_v2.provider_contracts import CapabilitySpec

from .contracts import INPUT_SCHEMAS, OUTPUT_SCHEMAS
from .provider import descriptor_for


CAPABILITY_IDS = (
    "base.runtime.database_config.get",
    "base.runtime.database_config.change.apply",
    "base.runtime.database_connection.test",
)


def system_json_path() -> Path:
    return Path.home() / ".ai00" / "config" / "system.json"


def load_system_json() -> dict[str, Any]:
    path = system_json_path()
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def save_system_json(value: dict[str, Any]) -> None:
    path = system_json_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def resolve_password(submitted: str, existing: dict[str, Any]) -> str:
    value = submitted or ""
    stripped = value.strip()
    if not stripped or set(stripped) <= {"●"}:
        return str(existing.get("password") or "")
    return value


def _validated(payload: dict[str, Any]) -> dict[str, Any]:
    host = str(payload.get("host") or "").strip()
    user = str(payload.get("user") or "").strip()
    collab_db = str(payload.get("collab_db") or "").strip()
    if not host or not user or not collab_db:
        raise ValueError("host, user and collab_db are required")
    port = int(payload.get("port") or 2883)
    if port < 1 or port > 65535:
        raise ValueError("port must be between 1 and 65535")
    return {
        "host": host,
        "port": port,
        "user": user,
        "password": str(payload.get("password") or ""),
        "collab_db": collab_db,
        "public_db": str(payload.get("public_db") or "").strip() or collab_db,
    }


def _database_url(config: dict[str, Any]) -> str:
    return (
        f"mysql://{quote(config['user'], safe='')}:{quote(config['password'], safe='')}"
        f"@{config['host']}:{config['port']}/{quote(config['collab_db'], safe='')}"
    )


def _stored_database_config(document: dict[str, Any] | None = None) -> dict[str, Any]:
    source = document if document is not None else load_system_json()
    config = source.get("cloud_db_config") or source.get("CLOUD_DB_CONFIG") or {}
    return dict(config) if isinstance(config, dict) else {}


def get_database_config(_payload: dict[str, Any], _context: object) -> dict[str, Any]:
    config = _stored_database_config()
    return {
        "host": str(config.get("host") or ""),
        "port": int(config.get("port") or 2883),
        "user": str(config.get("user") or ""),
        "password_configured": bool(config.get("password")),
        "collab_db": str(config.get("collab_db") or ""),
        "public_db": str(config.get("public_db") or ""),
    }


def save_database_config(payload: dict[str, Any], _context: object) -> dict[str, Any]:
    config = _validated(payload)
    document = load_system_json()
    existing = _stored_database_config(document)
    config["password"] = resolve_password(config["password"], existing)
    config["users_db_url"] = _database_url(config)
    document["cloud_db_config"] = config
    document.pop("CLOUD_DB_CONFIG", None)
    save_system_json(document)
    return {"saved": True, "password_configured": bool(config["password"])}


def test_database_connection(payload: dict[str, Any], _context: object) -> dict[str, Any]:
    config = _validated(payload)
    existing = _stored_database_config()
    config["password"] = resolve_password(config["password"], existing)
    connection = None
    try:
        connection = pymysql.connect(
            host=config["host"], port=config["port"], user=config["user"],
            password=config["password"], database=config["collab_db"], charset="utf8mb4",
            connect_timeout=8, read_timeout=8, write_timeout=8,
            cursorclass=pymysql.cursors.DictCursor,
        )
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 AS ok")
            cursor.fetchone()
        return {"connected": True}
    except Exception:
        return {"connected": False, "error_code": "connection_failed"}
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def register_runtime_database_capabilities(registry: Any) -> None:
    definitions = (
        (CAPABILITY_IDS[0], get_database_config, "Read redacted runtime database configuration.", "read", "none", True),
        (CAPABILITY_IDS[1], save_database_config, "Save runtime database configuration without exposing stored credentials.", "write", "user", True),
        (CAPABILITY_IDS[2], test_database_connection, "Test runtime database connectivity without persisting submitted values.", "read", "none", True),
    )
    for capability_id, handler, description, risk, confirmation, idempotent in definitions:
        spec = CapabilitySpec(
            id=capability_id, owner="base", description=description,
            use_when="A super administrator manages the server runtime database connection.",
            do_not_use_when="A business domain needs to access its own governed database.",
            risk=risk, confirmation=confirmation, idempotent=idempotent,
            permissions=("system.tech_config",), plugin_callable=False,
            input_schema=INPUT_SCHEMAS[capability_id], output_schema=OUTPUT_SCHEMAS[capability_id],
            tags=("base", "runtime", "database", "admin"),
        )
        descriptor = descriptor_for(spec).model_copy(update={
            "exposure": ExposurePolicy(web=True, api=True, plugin=False, agent=False, mcp=False),
            "agent_output_schema": None,
            "delegation_policy": "none",
            "data_classification": "restricted",
        })
        registry.register(spec, handler, descriptor=descriptor)


__all__ = [
    "CAPABILITY_IDS", "get_database_config", "load_system_json", "register_runtime_database_capabilities",
    "resolve_password", "save_database_config", "save_system_json", "system_json_path", "test_database_connection",
]
