"""Cross-worker confirmation token storage owned by the Agent database."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from threading import Lock
from typing import Any

from .connection import get_agent_conn


class InMemoryConfirmationRepository:
    def __init__(self, records: dict[str, dict[str, Any]] | None = None, lock: Lock | None = None) -> None:
        self.records = records if records is not None else {}
        self._lock = lock or Lock()

    def clear(self) -> None:
        with self._lock:
            self.records.clear()

    def save(self, token_hash: str, record: dict[str, Any]) -> None:
        with self._lock:
            self.records[token_hash] = dict(record)

    def begin(self, token_hash: str, expected: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            record = self.records.get(token_hash)
            if not record or record.get("state") != "pending" or record["expires_at"] <= datetime.now(UTC):
                return None
            if any(record.get(key) != value for key, value in expected.items()):
                return None
            from ..ai_assistant.tool_executor import _payload_hash
            if record.get("payload_hash") != _payload_hash(record.get("inputs") or {}):
                return None
            record["state"] = "inflight"
            return dict(record)

    def finish(self, token_hash: str, *, accepted: bool) -> None:
        with self._lock:
            record = self.records.get(token_hash)
            if not record or record.get("state") != "inflight":
                return
            if accepted:
                self.records.pop(token_hash, None)
            else:
                record["state"] = "pending"


class SqlConfirmationRepository:
    TABLE = "workmanship_agent_confirmation_tokens"

    def __init__(self, connection_factory=get_agent_conn) -> None:
        self._connection_factory = connection_factory

    def clear(self) -> None:
        with self._connection_factory() as conn, conn.cursor() as cur:
            cur.execute(f"DELETE FROM {self.TABLE}")

    def save(self, token_hash: str, record: dict[str, Any]) -> None:
        with self._connection_factory() as conn, conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO {self.TABLE} "
                "(token_hash,tool_name,inputs_json,session_gid,user_gid,catalog_release,capability_id,"
                "major_version,payload_hash,idempotency_key,agent_identity_json,state,expires_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',%s)",
                (
                    token_hash, record["tool_name"], json.dumps(record["inputs"], ensure_ascii=False),
                    record["session_gid"], record["user_gid"], record["catalog_release"],
                    record["capability_id"], record["major_version"], record["payload_hash"],
                    record["idempotency_key"], json.dumps(record["agent_identity"], ensure_ascii=False),
                    record["expires_at"].replace(tzinfo=None),
                ),
            )

    def begin(self, token_hash: str, expected: dict[str, Any]) -> dict[str, Any] | None:
        catalog_release = expected.get("catalog_release")
        capability_id = expected.get("capability_id")
        optional_sql = ""
        optional_values: list[Any] = []
        if catalog_release:
            optional_sql += " AND catalog_release=%s"
            optional_values.append(catalog_release)
        if capability_id:
            optional_sql += " AND capability_id=%s"
            optional_values.append(capability_id)
        with self._connection_factory() as conn, conn.cursor() as cur:
            cur.execute(
                f"UPDATE {self.TABLE} SET state='inflight' WHERE token_hash=%s AND state='pending' "
                "AND expires_at>UTC_TIMESTAMP(6) AND tool_name=%s AND session_gid=%s AND user_gid=%s "
                f"AND major_version=%s{optional_sql}",
                (
                    token_hash, expected["tool_name"], expected["session_gid"], expected["user_gid"],
                    expected["major_version"], *optional_values,
                ),
            )
            if cur.rowcount != 1:
                return None
            cur.execute(f"SELECT * FROM {self.TABLE} WHERE token_hash=%s", (token_hash,))
            row = cur.fetchone()
        if not row:
            return None
        expires_at = row["expires_at"]
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return {
            "tool_name": row["tool_name"], "inputs": _json(row["inputs_json"]),
            "session_gid": row["session_gid"], "user_gid": row["user_gid"],
            "catalog_release": row["catalog_release"], "capability_id": row["capability_id"],
            "major_version": int(row["major_version"]), "payload_hash": row["payload_hash"],
            "idempotency_key": row["idempotency_key"],
            "agent_identity": _json(row["agent_identity_json"]),
            "state": "inflight", "expires_at": expires_at,
        }

    def finish(self, token_hash: str, *, accepted: bool) -> None:
        with self._connection_factory() as conn, conn.cursor() as cur:
            if accepted:
                cur.execute(
                    f"DELETE FROM {self.TABLE} WHERE token_hash=%s AND state='inflight'", (token_hash,),
                )
            else:
                cur.execute(
                    f"UPDATE {self.TABLE} SET state='pending' WHERE token_hash=%s AND state='inflight'",
                    (token_hash,),
                )


def _json(value):
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    return json.loads(value) if isinstance(value, str) else value


__all__ = ["InMemoryConfirmationRepository", "SqlConfirmationRepository"]
