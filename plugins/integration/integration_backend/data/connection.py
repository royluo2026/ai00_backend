from __future__ import annotations

import os
from contextlib import contextmanager
from threading import Lock
from urllib.parse import unquote, urlparse

_pool = None
_lock = Lock()


def _params() -> dict:
    raw = os.getenv("AI00_INTEGRATION_DB_URL", "")
    if not raw:
        raise RuntimeError("AI00_INTEGRATION_DB_URL is required; Base DB credentials are not a fallback")
    parsed = urlparse(raw)
    if parsed.scheme not in {"mysql", "mysql+pymysql"} or not parsed.hostname or not parsed.path.strip("/"):
        raise RuntimeError("AI00_INTEGRATION_DB_URL must be an explicit mysql:// database URL")
    return {"host": parsed.hostname, "port": parsed.port or 3306, "user": unquote(parsed.username or ""), "password": unquote(parsed.password or ""), "database": parsed.path.lstrip("/")}


def _get_pool():
    global _pool
    if _pool is None:
        with _lock:
            if _pool is None:
                import pymysql
                import pymysql.cursors
                from dbutils.pooled_db import PooledDB
                _pool = PooledDB(creator=pymysql, maxconnections=10, mincached=1, blocking=True, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor, autocommit=False, connect_timeout=3, **_params())
    return _pool


@contextmanager
def get_integration_conn():
    conn = _get_pool().connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

