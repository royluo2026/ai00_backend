"""Read-only tenant-safe visibility into legacy Markdown migration readiness and runs."""
from __future__ import annotations

from typing import Any

from .models_next import CapabilityBusinessError, CapabilityContext, CapabilitySpec
from backend.knowledge.contracts import MIGRATION_STATUS_SCHEMA, transport_value
from backend.knowledge.provider import register_capability


def _tenant(context: CapabilityContext) -> str:
    tenant = str(context.team_gid or "").strip()
    if not tenant:
        raise CapabilityBusinessError(
            "tenant_scope_denied", "Knowledge migration status requires a team tenant."
        )
    return tenant


def migration_status(payload: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
    tenant = _tenant(context)
    scan_limit = max(1, min(int(payload.get("scan_limit") or 10000), 100000))
    run_gid = str(payload.get("run_gid") or "").strip()
    from backend.knowledge.data.connection import get_knowledge_conn as get_conn
    from backend.platform_sdk.identity import get_user_summaries

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid,creator_gid,share_scope,OCTET_LENGTH(content_md) AS byte_size "
                "FROM workmanship_know_entries WHERE content_md IS NOT NULL AND content_md<>'' "
                "ORDER BY gid LIMIT %s",
                (scan_limit,),
            )
            source_rows = [dict(row) for row in cur.fetchall()]
            cur.execute(
                "SELECT source_entry_gid FROM workmanship_know_documents "
                "WHERE tenant_gid=%s AND source_entry_gid IS NOT NULL",
                (tenant,),
            )
            migrated = {str(row["source_entry_gid"]) for row in cur.fetchall()}
            cur.execute(
                "SELECT gid,space_gid,actor_gid,status,source_count,source_bytes,copied_count,"
                "skipped_count,failed_count,verified_count,last_error,started_at,finished_at,created_at "
                "FROM workmanship_know_migration_runs WHERE tenant_gid=%s "
                "ORDER BY created_at DESC LIMIT 20",
                (tenant,),
            )
            runs = [transport_value(dict(row)) for row in cur.fetchall()]
            items: list[dict] = []
            if run_gid:
                cur.execute(
                    "SELECT i.entry_gid,i.document_gid,i.revision_gid,i.status,i.source_sha256,"
                    "i.object_key,i.content_sha256,i.error_message,i.started_at,i.finished_at "
                    "FROM workmanship_know_migration_items i "
                    "JOIN workmanship_know_migration_runs r ON r.gid=i.run_gid "
                    "WHERE i.run_gid=%s AND r.tenant_gid=%s ORDER BY i.entry_gid LIMIT 1000",
                    (run_gid, tenant),
                )
                items = [transport_value(dict(row)) for row in cur.fetchall()]

    identities = get_user_summaries(row.get("creator_gid") for row in source_rows)
    eligible: list[dict] = []
    quarantined = other_tenant = 0
    for row in source_rows:
        creator_gid = str(row.get("creator_gid") or "")
        identity = identities.get(creator_gid)
        creator_team = str((identity or {}).get("team_id") or "")
        if not creator_gid or not identity or not creator_team:
            quarantined += 1
        elif creator_team != tenant:
            other_tenant += 1
        elif str(row.get("share_scope") or "team") in {"local", "team"}:
            eligible.append(row)
        else:
            quarantined += 1
    pending = [row for row in eligible if str(row["gid"]) not in migrated]
    return {
        "inventory": {
            "scanned": len(source_rows),
            "scan_limit": scan_limit,
            "scan_truncated": len(source_rows) >= scan_limit,
            "eligible": len(eligible),
            "eligible_bytes": sum(int(row.get("byte_size") or 0) for row in eligible),
            "migrated": len(eligible) - len(pending),
            "pending": len(pending),
            "quarantined": quarantined,
            "other_tenant": other_tenant,
            "source_retained": True,
        },
        "runs": runs,
        "selected_run_gid": run_gid or None,
        "items": items,
    }


def register_knowledge_migration_capabilities(registry) -> None:
    register_capability(registry,
        CapabilitySpec(owner="knowledge",
            id="knowledge.migration.status",
            version=1,
            description="Inspect tenant-safe legacy Markdown migration readiness and audited runs.",
            permissions=("knowledge.manage",),
            plugin_callable=True,
            input_schema={"type": "object", "properties": {"scan_limit": {"type": "integer", "minimum": 1, "maximum": 100000}, "run_gid": {"type": "string"}}},
            output_schema=MIGRATION_STATUS_SCHEMA,
            tags=("knowledge", "migration", "read"),
        ),
        migration_status,
    )
