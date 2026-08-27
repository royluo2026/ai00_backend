"""Public in-process boundary for reading runtime file-store configuration."""
from __future__ import annotations

import json
import logging
from typing import Any

from backend.db.connection import get_conn


_log = logging.getLogger(__name__)


def _db_config(key: str) -> dict[str, Any]:
    try:
        with get_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT `value` FROM workmanship_app_system_config WHERE `key`=%s",
                    (key,),
                )
                row = cursor.fetchone()
        value = row.get("value") if isinstance(row, dict) else None
        if isinstance(value, str):
            value = json.loads(value)
        return dict(value) if isinstance(value, dict) else {}
    except Exception as exc:
        _log.warning("file_store_config: DB query failed: %s", exc)
        return {}


def read_runtime_file_store_config() -> dict[str, Any]:
    """Return raw configuration only to trusted in-process projection code."""
    minio = _db_config("minio_config")
    source = "db" if minio.get("endpoint") else "none"
    try:
        from backend.config import get_settings

        settings = get_settings()
        if not minio.get("endpoint") and settings.minio_enabled:
            minio = {
                "endpoint": settings.minio_endpoint,
                "access_key": settings.minio_access_key,
                "secret_key": settings.minio_secret_key,
                "bucket": settings.minio_bucket,
                "public_url": settings.minio_public_url,
            }
            source = "env"
        ois_env = {
            "identify": settings.ois_identify,
            "env": settings.ois_env,
            "ois3_url": settings.ois_ois3_url,
            "region": settings.ois_region,
            "licloud_appid": settings.ois_licloud_appid,
            "idaas_url": settings.ois_idaas_url,
            "idaas_client_id": settings.ois_idaas_client_id,
            "idaas_service_id": settings.ois_idaas_service_id,
            "public_base_url": settings.ois_public_base_url,
        }
    except Exception:
        ois_env = {}
    ois_db = _db_config("ois_config")
    ois = ois_db if ois_db.get("identify") else ois_env
    return {
        **minio,
        "source": source,
        "ois": ois,
        "ois_source": "db" if ois_db.get("identify") else ("env" if ois_env.get("identify") else "none"),
    }


__all__ = ["read_runtime_file_store_config"]
