from __future__ import annotations

import os
import json
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Lock
from urllib.parse import unquote, urlparse
from backend.capability_v2.domain_resource_config import pool_limits

_pool = None
_pool_lock = Lock()
_active_transaction = ContextVar("agent_transaction", default=None)


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


class AgentTransaction:
    """Lazy Agent-owned transaction for a domain write and its durable outbox event."""

    def __init__(self):
        self._connection = None
        self._closed = False
        self._token = _active_transaction.set(self)

    def connection(self):
        if self._closed:
            raise RuntimeError("Agent transaction is closed")
        if self._connection is None:
            self._connection = _get_pool().connection()
        return self._connection

    def record_outbox(self, capability_id, major_version, context, output):
        outcome_operation_id = str(
            getattr(context, "outcome_operation_id", "") or ""
        )
        if not outcome_operation_id:
            raise RuntimeError("Gateway outcome_operation_id is required for Agent writes")
        evidence = [item.model_dump(mode="json") for item in output.evidence]
        with self.connection().cursor() as cursor:
            cursor.execute(
                "INSERT INTO workmanship_agent_capability_outbox "
                "(event_id,outcome_operation_id,async_operation_id,request_id,"
                "capability_id,major_version,payload_json,state) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,'pending')",
                (
                    str(uuid.uuid4()),
                    outcome_operation_id,
                    str(getattr(context, "async_operation_id", "") or "") or None,
                    str(getattr(context, "request_id", "") or ""), capability_id,
                    int(major_version),
                    json.dumps({"data": output.data, "evidence": evidence}, ensure_ascii=False),
                ),
            )

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


def rollback_agent_transaction(transaction) -> None:
    try:
        transaction.rollback()
    except Exception:
        pass


def close_agent_transaction(transaction) -> None:
    try:
        transaction.close()
    except Exception:
        pass


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
