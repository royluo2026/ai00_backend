"""Public notification command surface for official domains."""

from backend.db.connection import get_conn
from backend.utils.notif import create_notification


def publish_notification(
    user_gid: str,
    type_: str,
    item_type: str | None,
    item_gid: str | None,
    title: str,
    body: str = "",
) -> str | None:
    """Create and commit a Base-owned notification without sharing a domain transaction."""
    with get_conn() as conn:
        gid = create_notification(conn, user_gid, type_, item_type, item_gid, title, body)
        conn.commit()
    return gid


__all__ = ["create_notification", "publish_notification"]