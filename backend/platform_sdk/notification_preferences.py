"""Base-owned notification preference projection and command."""
from __future__ import annotations

import json
from backend.db.connection import get_conn

DEFAULTS = {"scope_approved": True, "scope_rejected": True, "item_status": True, "new_follower": True}


def _normalize(raw) -> dict[str, bool]:
    if isinstance(raw, str):
        try: raw = json.loads(raw)
        except ValueError: raw = {}
    if not isinstance(raw, dict): raw = {}
    return {key: bool(raw.get(key, default)) for key, default in DEFAULTS.items()}


def get_notification_preferences(user_gid: str) -> dict[str, bool]:
    with get_conn() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT notification_prefs FROM workmanship_auth_users WHERE gid=%s", (user_gid,)); row = cursor.fetchone()
    return _normalize((row or {}).get("notification_prefs") if isinstance(row, dict) else row[0] if row else {})


def update_notification_preferences(user_gid: str, changes: dict) -> dict[str, bool]:
    current = get_notification_preferences(user_gid)
    for key in DEFAULTS:
        if key in changes: current[key] = bool(changes[key])
    with get_conn() as connection:
        with connection.cursor() as cursor: cursor.execute("UPDATE workmanship_auth_users SET notification_prefs=%s WHERE gid=%s", (json.dumps(current), user_gid))
        connection.commit()
    return current


__all__ = ["DEFAULTS", "get_notification_preferences", "update_notification_preferences"]
