"""Device control-plane storage and explicit VisMockup local capabilities."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.domain_ports.local_integration import (
    LocalOperationEnvelope,
    PROTOCOL_V2,
    content_hash,
    sign_operation_envelope,
)

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


_FORBIDDEN_RESULT_KEYS = {"path", "file_path", "uri", "download_url", "object_key", "secret", "token"}


def _safe_result_json(result: Any) -> str:
    def inspect(value: Any) -> None:
        if isinstance(value, dict):
            forbidden = _FORBIDDEN_RESULT_KEYS.intersection(str(key).lower() for key in value)
            if forbidden:
                raise ValueError("local_result_contains_forbidden_transport_field")
            for child in value.values():
                inspect(child)
        elif isinstance(value, list):
            for child in value:
                inspect(child)
    inspect(result)
    encoded = _json(result)
    if len(encoded.encode("utf-8")) > 1024 * 1024:
        raise ValueError("local_result_too_large")
    return encoded


def _operation_signing_key() -> tuple[str, str]:
    key_id = os.environ.get("AI00_LOCAL_OPERATION_SIGNING_KEY_ID", "")
    secret = os.environ.get("AI00_LOCAL_OPERATION_SIGNING_SECRET", "")
    if not key_id or len(secret.encode("utf-8")) < 32:
        raise RuntimeError("local_operation_signing_key_unavailable")
    return key_id, secret


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def build_signed_lease(row: dict, lease_id: str, *, now: datetime | None = None) -> dict:
    """Build the exact signed cloud-to-device protocol document."""
    issued_at = _as_utc(now or datetime.now(timezone.utc)).replace(microsecond=0)
    expires_at = min(_as_utc(row["expires_at"]), issued_at + timedelta(minutes=5)).replace(microsecond=0)
    payload = _decode(row["payload"])
    stored_hash = str(row.get("payload_hash") or "")
    actual_stored_hash = hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()
    if stored_hash and not secrets.compare_digest(stored_hash.removeprefix("sha256:"), actual_stored_hash):
        raise RuntimeError("queued_payload_integrity_failed")
    key_id, secret = _operation_signing_key()
    envelope = LocalOperationEnvelope(
        protocol=PROTOCOL_V2,
        operation_id=str(row["gid"]),
        tenant_id=str(row.get("team_gid") or row["requested_by"]),
        capability_id=str(row["capability_id"]),
        payload=payload,
        payload_hash=content_hash(payload),
        key_id=key_id,
        issued_at=issued_at,
        expires_at=expires_at,
    )
    return {
        "operation": envelope.model_dump(mode="json"),
        "signature": sign_operation_envelope(envelope, secret),
        "lease_id": lease_id,
    }


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


def can_use_device(device_gid: str, user_gid: str, team_gid: str | None) -> bool:
    with get_device_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid FROM workmanship_runtime_devices WHERE gid=%s AND status<>'revoked' AND (owner_user_gid=%s OR (team_gid IS NOT NULL AND team_gid=%s)) LIMIT 1",
                (device_gid, user_gid, team_gid),
            )
            return bool(cur.fetchone())


def heartbeat(device_gid: str, runtime_version: str, capabilities: list[str]) -> None:

    with get_device_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_runtime_devices SET runtime_version=%s, capabilities=%s, status='online', last_seen_at=NOW(), updated_at=NOW() WHERE gid=%s",
                (runtime_version[:64], _json(sorted(set(capabilities))), device_gid),
            )
        conn.commit()


def enqueue_command(capability_id: str, version: int, payload: dict, user_gid: str, ttl_seconds: int = 300, operation_id: str | None = None, team_gid: str | None = None) -> dict:

    device_gid = str(payload.get("device_id") or payload.get("device_gid") or "")
    if not device_gid:
        raise ValueError("device_id is required")
    command_payload = {key: value for key, value in payload.items() if key not in {"device_id", "device_gid"}}
    command_payload["device_id"] = device_gid
    encoded = _json(command_payload)
    command_gid = operation_id or _gid("cmd")
    ttl_seconds = max(30, min(int(ttl_seconds), 3600))
    with get_device_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid, capabilities FROM workmanship_runtime_devices WHERE gid=%s AND (owner_user_gid=%s OR (team_gid IS NOT NULL AND team_gid=%s)) LIMIT 1",
                (device_gid, user_gid, team_gid),
            )
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
            cur.execute("UPDATE workmanship_runtime_commands SET status='pending_failed', error='operation_expired', updated_at=NOW() WHERE device_gid=%s AND status='queued' AND expires_at<=NOW()", (device_gid,))
            cur.execute("UPDATE workmanship_runtime_commands SET status='pending_failed', error='operation_expired', updated_at=NOW() WHERE device_gid=%s AND status='leased' AND expires_at<=NOW()", (device_gid,))
            cur.execute("UPDATE workmanship_runtime_commands SET status='queued', lease_id=NULL, lease_until=NULL, updated_at=NOW() WHERE device_gid=%s AND status='leased' AND lease_until<=NOW() AND expires_at>NOW() AND attempts<3", (device_gid,))
            cur.execute("UPDATE workmanship_runtime_commands SET status='pending_failed', error='lease_retry_limit_reached', updated_at=NOW() WHERE device_gid=%s AND status='leased' AND lease_until<=NOW() AND attempts>=3", (device_gid,))
            cur.execute(
                "SELECT c.*,d.team_gid FROM workmanship_runtime_commands c JOIN workmanship_runtime_devices d ON d.gid=c.device_gid WHERE c.device_gid=%s AND c.status='queued' AND c.expires_at>NOW() ORDER BY c.created_at LIMIT 1 FOR UPDATE SKIP LOCKED",
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
    return build_signed_lease(dict(row), lease_id)


def complete_command(device_gid: str, command_gid: str, lease_id: str, status: str, result: Any = None, error_code: str = "") -> None:

    allowed = {"completed", "failed", "outcome_unknown"}
    if status not in allowed:
        raise ValueError("invalid_completion_status")
    if status != "completed" and not error_code:
        raise ValueError("error_code_required")
    if len(error_code) > 128 or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789_.-" for character in error_code):
        raise ValueError("invalid_error_code")
    encoded_result = _safe_result_json(result)
    pending_status = "pending_" + status
    with get_device_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_runtime_commands SET status=%s, result=%s, error=%s, updated_at=NOW() WHERE gid=%s AND device_gid=%s AND status='leased' AND lease_id=%s AND lease_until>NOW()",
                (pending_status, encoded_result, error_code or None, command_gid, device_gid, lease_id),
            )
            if cur.rowcount != 1:
                cur.execute("SELECT status,lease_id FROM workmanship_runtime_commands WHERE gid=%s AND device_gid=%s LIMIT 1", (command_gid, device_gid))
                existing = cur.fetchone()
                if not existing or existing.get("status") not in {pending_status, status} or existing.get("lease_id") != lease_id:
                    raise ValueError("Command lease is invalid or expired")
        conn.commit()


def pending_reconciliations(device_gid: str) -> list[dict]:
    with get_device_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid,status,error,lease_id FROM workmanship_runtime_commands WHERE device_gid=%s AND status IN ('pending_completed','pending_failed','pending_outcome_unknown') ORDER BY updated_at LIMIT 100",
                (device_gid,),
            )
            return [dict(row) for row in cur.fetchall()]


def mark_command_reconciled(device_gid: str, command_gid: str, pending_status: str) -> None:
    if pending_status not in {"pending_completed", "pending_failed", "pending_outcome_unknown"}:
        raise ValueError("invalid_pending_status")
    final_status = pending_status.removeprefix("pending_")
    with get_device_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_runtime_commands SET status=%s,updated_at=NOW() WHERE gid=%s AND device_gid=%s AND status=%s",
                (final_status, command_gid, device_gid, pending_status),
            )
        conn.commit()


def authorize_command_artifact(device_gid: str, command_gid: str, lease_id: str, artifact_id: str) -> dict:
    """Resolve only an ArtifactRef already authorized and signed into this active lease."""
    with get_device_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT payload FROM workmanship_runtime_commands WHERE gid=%s AND device_gid=%s AND status='leased' AND lease_id=%s AND lease_until>NOW() AND expires_at>NOW() LIMIT 1",
                (command_gid, device_gid, lease_id),
            )
            row = cur.fetchone()
    if not row:
        raise PermissionError("artifact_lease_invalid")
    payload = _decode(row["payload"])
    ref = payload.get("artifact_ref") if isinstance(payload, dict) else None
    if not isinstance(ref, dict) or ref.get("artifact_id") != artifact_id:
        raise PermissionError("artifact_not_bound_to_operation")
    return dict(ref)


def authorize_active_lease(device_gid: str, command_gid: str, lease_id: str, capability_id: str) -> dict:
    with get_device_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT capability_id,payload FROM workmanship_runtime_commands WHERE gid=%s AND device_gid=%s AND status='leased' AND lease_id=%s AND lease_until>NOW() AND expires_at>NOW() LIMIT 1",
                (command_gid, device_gid, lease_id),
            )
            row = cur.fetchone()
    if not row or row.get("capability_id") != capability_id:
        raise PermissionError("operation_lease_invalid")
    return {"capability_id": row["capability_id"], "payload": _decode(row["payload"])}


def list_devices(user_gid: str, team_gid: str | None = None) -> list[dict]:

    with get_device_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT gid, display_name, platform, runtime_version, capabilities, IF(last_seen_at < DATE_SUB(NOW(), INTERVAL 2 MINUTE), 'offline', status) AS status, last_seen_at, created_at FROM workmanship_runtime_devices WHERE owner_user_gid=%s OR (team_gid IS NOT NULL AND team_gid=%s) ORDER BY updated_at DESC", (user_gid, team_gid))
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
    if str(row.get("status") or "").startswith("pending_"):
        row["status"] = "reconciling"
        row["result"] = None
    row["result"] = _decode(row.get("result"))
    for key in ("created_at", "updated_at"):
        if row.get(key) and hasattr(row[key], "isoformat"):
            row[key] = row[key].isoformat()
    return row
