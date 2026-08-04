"""Device control-plane storage and explicit VisMockup local capabilities."""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from typing import Any

from .data.connection import get_device_conn


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _decode(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def _iso_utc(value: Any) -> str:
    if not isinstance(value, datetime):
        return str(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
def _gid(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(16)}"


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def create_enrollment(user: dict, display_name: str, team_gid: str | None = None, ttl_minutes: int = 30) -> dict:

    raw_token = secrets.token_urlsafe(32)
    gid = _gid("enr")
    ttl_minutes = max(5, min(int(ttl_minutes), 1440))
    with get_device_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_runtime_enrollments (gid, token_hash, created_by, team_gid, display_name, expires_at) VALUES (%s,%s,%s,%s,%s,DATE_ADD(NOW(), INTERVAL %s MINUTE))",
                (gid, _hash_secret(raw_token), user["gid"], team_gid, display_name[:255], ttl_minutes),
            )
        conn.commit()
    return {"gid": gid, "enrollment_token": raw_token, "expires_in": ttl_minutes * 60}


def activate_device(enrollment_token: str, runtime_version: str, capabilities: list[str]) -> dict:

    device_token = secrets.token_urlsafe(48)
    device_gid = _gid("dev")
    with get_device_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM workmanship_runtime_enrollments WHERE token_hash=%s AND used_at IS NULL AND expires_at>NOW() FOR UPDATE",
                (_hash_secret(enrollment_token),),
            )
            enrollment = cur.fetchone()
            if not enrollment:
                raise ValueError("Enrollment token is invalid, expired, or already used")
            cur.execute(
                "INSERT INTO workmanship_runtime_devices (gid, owner_user_gid, team_gid, display_name, runtime_version, token_hash, capabilities, status, last_seen_at) VALUES (%s,%s,%s,%s,%s,%s,%s,'online',NOW())",
                (device_gid, enrollment["created_by"], enrollment.get("team_gid"), enrollment["display_name"], runtime_version[:64], _hash_secret(device_token), _json(sorted(set(capabilities)))),
            )
            cur.execute("UPDATE workmanship_runtime_enrollments SET used_at=NOW() WHERE gid=%s", (enrollment["gid"],))
        conn.commit()
    return {"device_gid": device_gid, "device_token": device_token}


def authenticate_device(device_gid: str, device_token: str) -> dict:

    with get_device_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM workmanship_runtime_devices WHERE gid=%s LIMIT 1", (device_gid,))
            row = cur.fetchone()
    if not row or not secrets.compare_digest(str(row["token_hash"]), _hash_secret(device_token)):
        raise PermissionError("Invalid device credentials")
    row["capabilities"] = _decode(row.get("capabilities")) or []
    return row


def heartbeat(device_gid: str, runtime_version: str, capabilities: list[str]) -> None:

    with get_device_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_runtime_devices SET runtime_version=%s, capabilities=%s, status='online', last_seen_at=NOW(), updated_at=NOW() WHERE gid=%s",
                (runtime_version[:64], _json(sorted(set(capabilities))), device_gid),
            )
        conn.commit()


def enqueue_command(capability_id: str, version: int, payload: dict, user_gid: str, ttl_seconds: int = 300) -> dict:

    device_gid = str(payload.get("device_gid") or "")
    if not device_gid:
        raise ValueError("device_gid is required")
    command_payload = {key: value for key, value in payload.items() if key != "device_gid"}
    encoded = _json(command_payload)
    command_gid = _gid("cmd")
    ttl_seconds = max(30, min(int(ttl_seconds), 3600))
    with get_device_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT gid, capabilities FROM workmanship_runtime_devices WHERE gid=%s AND owner_user_gid=%s LIMIT 1", (device_gid, user_gid))
            device = cur.fetchone()
            if not device:
                raise PermissionError("Device not found or not owned by current user")
            advertised = set(_decode(device.get("capabilities")) or [])
            if capability_id not in advertised:
                raise ValueError(f"Device does not advertise {capability_id}")
            cur.execute(
                "INSERT INTO workmanship_runtime_commands (gid, device_gid, capability_id, capability_version, payload, payload_hash, requested_by, expires_at) VALUES (%s,%s,%s,%s,%s,%s,%s,DATE_ADD(NOW(), INTERVAL %s SECOND))",
                (command_gid, device_gid, capability_id, version, encoded, hashlib.sha256(encoded.encode()).hexdigest(), user_gid, ttl_seconds),
            )
        conn.commit()
    return {"command_gid": command_gid, "device_gid": device_gid, "status": "queued", "expires_in": ttl_seconds}


def lease_command(device_gid: str, lease_seconds: int = 60) -> dict | None:

    lease_seconds = max(15, min(int(lease_seconds), 300))
    lease_id = _gid("lease")
    with get_device_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE workmanship_runtime_commands SET status='expired', updated_at=NOW() WHERE device_gid=%s AND status='queued' AND expires_at<=NOW()", (device_gid,))
            cur.execute("UPDATE workmanship_runtime_commands SET status='queued', lease_id=NULL, lease_until=NULL, updated_at=NOW() WHERE device_gid=%s AND status='leased' AND lease_until<=NOW() AND expires_at>NOW() AND attempts<3", (device_gid,))
            cur.execute("UPDATE workmanship_runtime_commands SET status='failed', error='lease retry limit reached', lease_id=NULL, lease_until=NULL, updated_at=NOW() WHERE device_gid=%s AND status='leased' AND lease_until<=NOW() AND attempts>=3", (device_gid,))
            cur.execute(
                "SELECT * FROM workmanship_runtime_commands WHERE device_gid=%s AND status='queued' AND expires_at>NOW() ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED",
                (device_gid,),
            )
            row = cur.fetchone()
            if not row:
                conn.commit()
                return None
            cur.execute(
                "UPDATE workmanship_runtime_commands SET status='leased', lease_id=%s, lease_until=DATE_ADD(NOW(), INTERVAL %s SECOND), attempts=attempts+1, updated_at=NOW() WHERE gid=%s AND status='queued'",
                (lease_id, lease_seconds, row["gid"]),
            )
        conn.commit()
    return {"command_id": row["gid"], "lease_id": lease_id, "capability": row["capability_id"], "version": row["capability_version"], "payload": _decode(row["payload"]), "payload_hash": row["payload_hash"], "expires_at": _iso_utc(row["expires_at"])}


def complete_command(device_gid: str, command_gid: str, lease_id: str, success: bool, result: Any = None, error: str = "") -> None:

    status = "succeeded" if success else "failed"
    with get_device_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_runtime_commands SET status=%s, result=%s, error=%s, lease_id=NULL, lease_until=NULL, updated_at=NOW() WHERE gid=%s AND device_gid=%s AND status='leased' AND lease_id=%s AND lease_until>NOW()",
                (status, _json(result), error[:4000] or None, command_gid, device_gid, lease_id),
            )
            if cur.rowcount != 1:
                raise ValueError("Command lease is invalid or expired")
        conn.commit()


def list_devices(user_gid: str) -> list[dict]:

    with get_device_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT gid, display_name, platform, runtime_version, capabilities, IF(last_seen_at < DATE_SUB(NOW(), INTERVAL 2 MINUTE), 'offline', status) AS status, last_seen_at, created_at FROM workmanship_runtime_devices WHERE owner_user_gid=%s ORDER BY updated_at DESC", (user_gid,))
            rows = cur.fetchall()
    return [{**row, "capabilities": _decode(row.get("capabilities")) or [], "last_seen_at": row["last_seen_at"].isoformat() if row.get("last_seen_at") else None, "created_at": row["created_at"].isoformat() if row.get("created_at") else None} for row in rows]


def revoke_device(user_gid: str, device_gid: str) -> None:

    with get_device_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE workmanship_runtime_devices SET status='revoked', token_hash=%s, updated_at=NOW() WHERE gid=%s AND owner_user_gid=%s", (_hash_secret(secrets.token_urlsafe(48)), device_gid, user_gid))
            if cur.rowcount != 1:
                raise LookupError("Device not found")
            cur.execute("UPDATE workmanship_runtime_commands SET status='cancelled', updated_at=NOW() WHERE device_gid=%s AND status IN ('queued','leased')", (device_gid,))
        conn.commit()
def get_command(command_gid: str, user_gid: str) -> dict:

    with get_device_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT gid, device_gid, capability_id, capability_version, status, result, error, created_at, updated_at FROM workmanship_runtime_commands WHERE gid=%s AND requested_by=%s LIMIT 1", (command_gid, user_gid))
            row = cur.fetchone()
    if not row:
        raise LookupError("Command not found")
    row["result"] = _decode(row.get("result"))
    for key in ("created_at", "updated_at"):
        if row.get(key) and hasattr(row[key], "isoformat"):
            row[key] = row[key].isoformat()
    return row
