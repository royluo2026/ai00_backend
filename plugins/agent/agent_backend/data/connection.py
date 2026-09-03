from __future__ import annotations

import os
import re
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Lock
from urllib.parse import unquote, urlparse
from backend.capability_v2.domain_resource_config import pool_limits

_pool = None
_pool_lock = Lock()
_active_transaction = ContextVar("agent_transaction", default=None)
_BASE_TRANSACTION_TABLES = (
    "workmanship_base_capability_outcomes",
    "workmanship_base_capability_audit_outbox",
)


def _connection_params() -> dict:
    raw = os.environ.get("AI00_AGENT_DB_URL", "")
    if not raw:
        raise RuntimeError(
            "AI00_AGENT_DB_URL is required for Agent persistence; "
            "the Base application database credential is not a fallback"
        )
    parsed = urlparse(raw)
    if parsed.scheme not in {"mysql", "mysql+pymysql"} or not parsed.hostname or not parsed.path.strip("/"):
        raise RuntimeError("AI00_AGENT_DB_URL must be a mysql:// URL with an explicit database")
    return {
        "host": parsed.hostname,
        "port": parsed.port or 3306,
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "database": parsed.path.lstrip("/"),
    }


def _get_pool():
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is None:
            import pymysql
            import pymysql.cursors
            from dbutils.pooled_db import PooledDB
            limits = pool_limits("agent")

            _pool = PooledDB(
                creator=pymysql,
                maxconnections=limits.maximum,
                mincached=limits.minimum,
                blocking=True,
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=False,
                connect_timeout=3,
                **_connection_params(),
            )
    return _pool


def _database_name(env_name: str) -> str:
    raw = os.environ.get(env_name, "")
    name = urlparse(raw).path.lstrip("/") if raw else ""
    if name and not re.fullmatch(r"[A-Za-z0-9_]+", name):
        raise RuntimeError(f"{env_name} contains an invalid database name")
    return name


class _TransactionCursor:
    def __init__(self, cursor, base_database: str):
        self._cursor = cursor
        self._base_database = base_database

    def __enter__(self):
        self._cursor.__enter__()
        return self

    def __exit__(self, *args):
        return self._cursor.__exit__(*args)

    def __getattr__(self, name):
        return getattr(self._cursor, name)

    def execute(self, query, args=None):
        if self._base_database:
            for table in _BASE_TRANSACTION_TABLES:
                query = query.replace(table, f"`{self._base_database}`.`{table}`")
        return self._cursor.execute(query, args)


class AgentTransaction:
    """Lazy Agent DB transaction that can atomically enlist Base outcome tables."""

    def __init__(self):
        self._connection = None
        self._closed = False
        self._token = _active_transaction.set(self)
        self._base_database = _database_name("AI00_BASE_DB_URL")

    def connection(self):
        if self._closed:
            raise RuntimeError("Agent transaction is closed")
        if self._connection is None:
            self._connection = _get_pool().connection()
        return self._connection

    def cursor(self):
        return _TransactionCursor(self.connection().cursor(), self._base_database)

    def commit(self):
        if self._connection is not None:
            self._connection.commit()

    def rollback(self):
        if self._connection is not None:
            self._connection.rollback()

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            _active_transaction.reset(self._token)
        except ValueError:
            if _active_transaction.get() is self:
                _active_transaction.set(None)
        if self._connection is not None:
            self._connection.close()


def begin_agent_transaction() -> AgentTransaction:
    if _active_transaction.get() is not None:
        raise RuntimeError("nested Agent transactions are not supported")
    return AgentTransaction()


@contextmanager
def get_agent_conn():
    transaction = _active_transaction.get()
    if transaction is not None:
        yield transaction.connection()
        return
    conn = _get_pool().connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
