"""Lightweight normalized plugin usage metrics and immutable monthly snapshots."""
from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime

_log = logging.getLogger(__name__)


def parse_month(value: str) -> date:
    try:
        parsed = datetime.strptime(value, "%Y-%m").date().replace(day=1)
    except (TypeError, ValueError) as exc:
        raise ValueError("month must use YYYY-MM") from exc
    return parsed


def previous_month(value: date) -> date:
    return date(value.year - 1, 12, 1) if value.month == 1 else date(value.year, value.month - 1, 1)


def next_month(value: date) -> date:
    return date(value.year + 1, 1, 1) if value.month == 12 else date(value.year, value.month + 1, 1)


def usage_dedupe_key(context, capability_id: str) -> str:
    tenant = context.team_gid or f"user:{context.user_gid}"
    plugin_id = str(getattr(context, "plugin_id", ""))
    if context.source == "agent":
        run_id = str(getattr(context, "agent_run_id", ""))
        if not run_id:
            raise ValueError("agent plugin usage requires agent_run_id")
        raw = f"agent|{tenant}|{plugin_id}|{run_id}"
    else:
        request_id = str(context.request_id or "")
        if not request_id:
            raise ValueError("web plugin usage requires request_id")
        raw = f"web|{tenant}|{plugin_id}|{request_id}|{capability_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def record_usage(context, capability_id: str, succeeded: bool) -> None:
    plugin_id = str(getattr(context, "plugin_id", ""))
    if not plugin_id:
        return
    try:
        dedupe = usage_dedupe_key(context, capability_id)
        tenant = context.team_gid or f"user:{context.user_gid}"
        channel = "agent" if context.source == "agent" else "web"
        version = str(getattr(context, "plugin_version", ""))
        from backend.db.connection import get_conn
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO workmanship_plugin_usage_events "
                    "(dedupe_key,tenant_gid,plugin_id,plugin_version,channel,capability_id,user_gid,succeeded) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
                    "ON DUPLICATE KEY UPDATE succeeded=LEAST(succeeded,VALUES(succeeded))",
                    (dedupe, tenant, plugin_id, version, channel, capability_id, context.user_gid, bool(succeeded)),
                )
            conn.commit()
    except Exception as exc:
        _log.warning("Plugin usage metric was not persisted: %s", exc)


def _close_tenant_month(tenant: str, actor_gid: str, month_start: date) -> dict:
    """Atomically claim and materialize one immutable tenant-month snapshot."""
    month_end = next_month(month_start)
    month = month_start.strftime("%Y-%m")
    from backend.db.connection import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT IGNORE INTO workmanship_plugin_usage_month_closures "
                "(tenant_gid,month_start,closed_by) VALUES (%s,%s,%s)",
                (tenant, month_start, actor_gid),
            )
            if cur.rowcount == 0:
                return {"tenant_gid": tenant, "month": month, "closed": True, "already_closed": True, "plugins": 0}
            cur.execute(
                "SELECT plugin_id,COUNT(*) AS attempt_count,SUM(CASE WHEN succeeded THEN 1 ELSE 0 END) AS usage_count "
                "FROM workmanship_plugin_usage_events WHERE tenant_gid=%s AND occurred_at >= %s AND occurred_at < %s "
                "GROUP BY plugin_id",
                (tenant, month_start, month_end),
            )
            rows = [dict(row) for row in cur.fetchall()]
            for row in rows:
                attempts = int(row["attempt_count"] or 0); uses = int(row["usage_count"] or 0)
                rate = round(uses / attempts, 4) if attempts else 0
                cur.execute(
                    "INSERT INTO workmanship_plugin_usage_monthly "
                    "(tenant_gid,plugin_id,month_start,usage_count,attempt_count,success_rate) VALUES (%s,%s,%s,%s,%s,%s)",
                    (tenant, row["plugin_id"], month_start, uses, attempts, rate),
                )
        conn.commit()
    return {"tenant_gid": tenant, "month": month, "closed": True, "already_closed": False, "plugins": len(rows)}


def close_month(user: dict, month: str) -> dict:
    month_start = parse_month(month)
    if next_month(month_start) > date.today().replace(day=1):
        raise ValueError("only a completed month can be closed")
    tenant = user.get("team_id") or f"user:{user['gid']}"
    return _close_tenant_month(tenant, user["gid"], month_start)


def close_previous_month_all_tenants(actor_gid: str = "system:plugin-usage-monthly", today: date | None = None) -> dict:
    """Close the previous month for every tenant that produced plugin usage facts."""
    current = (today or date.today()).replace(day=1)
    month_start = previous_month(current)
    month_end = current
    from backend.db.connection import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT tenant_gid FROM workmanship_plugin_usage_events "
                "WHERE occurred_at >= %s AND occurred_at < %s ORDER BY tenant_gid",
                (month_start, month_end),
            )
            tenants = [str(row["tenant_gid"]) for row in cur.fetchall()]
    results = [_close_tenant_month(tenant, actor_gid, month_start) for tenant in tenants]
    return {
        "month": month_start.strftime("%Y-%m"),
        "tenants": len(results),
        "newly_closed": sum(not item["already_closed"] for item in results),
        "already_closed": sum(item["already_closed"] for item in results),
        "plugins": sum(item["plugins"] for item in results),
    }

def monthly_ranking(user: dict, month: str) -> dict:
    current = parse_month(month); previous = previous_month(current)
    tenant = user.get("team_id") or f"user:{user['gid']}"
    from backend.db.connection import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT plugin_id,month_start,usage_count,attempt_count,success_rate FROM workmanship_plugin_usage_monthly "
                "WHERE tenant_gid=%s AND month_start IN (%s,%s)",
                (tenant, current, previous),
            )
            rows = [dict(row) for row in cur.fetchall()]
    by_plugin: dict[str, dict] = {}
    for row in rows:
        item = by_plugin.setdefault(row["plugin_id"], {"plugin_id": row["plugin_id"], "current_usage": 0, "previous_usage": 0, "success_rate": 0})
        if row["month_start"] == current:
            item["current_usage"] = int(row["usage_count"]); item["success_rate"] = float(row["success_rate"])
        else:
            item["previous_usage"] = int(row["usage_count"])
    items = []
    for item in by_plugin.values():
        item["monthly_delta"] = item["current_usage"] - item["previous_usage"]
        items.append(item)
    items.sort(key=lambda item: (-item["current_usage"], -item["monthly_delta"], item["plugin_id"]))
    return {"month": month, "previous_month": previous.strftime("%Y-%m"), "items": items}