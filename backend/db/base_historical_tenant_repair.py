"""Single-source plan for Base historical tenant repair migration 0006."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Mapping, MutableMapping, Sequence


MIGRATION_ID = "202608280006"
LEGACY_PREFIX = "legacy-unresolved:"


class TenantRepairCollision(RuntimeError):
    pass


@dataclass(frozen=True)
class TenantRepairTable:
    name: str
    aggregate_table: str
    alias: str
    aggregate_alias: str
    aggregate_join_sql: str
    aggregate_key: str
    is_idempotency: bool


REPAIR_TABLES = (
    TenantRepairTable(
        "workmanship_base_saved_view_idempotency", "workmanship_app_view_configs", "i", "v",
        "v ON v.gid=i.view_gid", "view_gid", True,
    ),
    TenantRepairTable(
        "workmanship_base_saved_view_audit_events", "workmanship_app_view_configs", "e", "v",
        "v ON v.gid=e.view_gid", "view_gid", False,
    ),
    TenantRepairTable(
        "workmanship_base_self_annotation_idempotency", "workmanship_base_self_annotations", "i", "a",
        "a\n  ON a.item_gid=i.item_gid AND a.user_gid=i.actor_gid", "annotation", True,
    ),
    TenantRepairTable(
        "workmanship_base_self_annotation_audit_events", "workmanship_base_self_annotations", "e", "a",
        "a\n  ON a.item_gid=e.item_gid AND a.user_gid=e.actor_gid", "annotation", False,
    ),
)


def legacy_synthetic_digest(actor_gid: str, operation: str, idempotency_key: str) -> str:
    return hashlib.sha256(f"legacy:{actor_gid}:{operation}:{idempotency_key}".encode()).hexdigest()


def _row_identity(table: TenantRepairTable | str, row: Mapping[str, object]) -> str:
    is_idempotency = table.is_idempotency if isinstance(table, TenantRepairTable) else table.endswith("idempotency")
    if is_idempotency:
        return ":".join(str(row.get(key, "")) for key in ("actor_gid", "operation", "idempotency_key"))
    return str(row.get("gid", ""))


def legacy_unresolved_scope(table: TenantRepairTable | str, row: Mapping[str, object]) -> str:
    return LEGACY_PREFIX + hashlib.sha256(_row_identity(table, row).encode()).hexdigest()


def _aggregate_tenant(
    table: TenantRepairTable,
    row: Mapping[str, object],
    saved_views: Mapping[str, str],
    annotations: Mapping[tuple[str, str], str],
) -> str | None:
    if table.aggregate_key == "view_gid":
        return saved_views.get(str(row.get("view_gid") or "")) or None
    return annotations.get((str(row.get("item_gid") or ""), str(row.get("actor_gid") or ""))) or None


def resolve_tenant_scope(
    table: TenantRepairTable,
    row: Mapping[str, object],
    *,
    saved_views: Mapping[str, str],
    annotations: Mapping[tuple[str, str], str],
    users: Mapping[str, str | None],
) -> str:
    aggregate = _aggregate_tenant(table, row, saved_views, annotations)
    if aggregate:
        return aggregate
    actor_gid = str(row.get("actor_gid") or "")
    if actor_gid in users:
        return users[actor_gid] or f"user:{actor_gid}"
    return legacy_unresolved_scope(table, row)


def _repairable(scope: object) -> bool:
    return not scope or str(scope).startswith("user:")


def apply_tenant_repair(
    *,
    records: MutableMapping[str, list[dict[str, object]]],
    saved_views: Mapping[str, str],
    annotations: Mapping[tuple[str, str], str],
    users: Mapping[str, str | None],
    marker_applied: bool,
    tables: Sequence[str] | None = None,
) -> int:
    """Execute 0006's deterministic row policy for migration fixtures/recovery checks."""
    if marker_applied:
        return 0
    requested = set(tables or (table.name for table in REPAIR_TABLES))
    changed = 0
    for table in REPAIR_TABLES:
        if table.name not in requested:
            continue
        rows = records[table.name]
        scopes = [
            resolve_tenant_scope(table, row, saved_views=saved_views, annotations=annotations, users=users)
            if _repairable(row.get("tenant_gid")) else str(row["tenant_gid"])
            for row in rows
        ]
        if table.is_idempotency:
            keys = {
                (
                    scope,
                    str(row.get("actor_gid") or ""),
                    str(row.get("operation") or ""),
                    str(row.get("idempotency_key") or ""),
                )
                for scope, row in zip(scopes, rows)
            }
            if len(keys) != len(rows):
                raise TenantRepairCollision(f"primary key collision in {table.name}")
        for row, scope in zip(rows, scopes):
            if row.get("tenant_gid") != scope:
                row["tenant_gid"] = scope
                changed += 1
    return changed


def _legacy_identity_sql(table: TenantRepairTable) -> str:
    alias = table.alias
    return f"CONCAT_WS(':',{alias}.actor_gid,{alias}.operation,{alias}.idempotency_key)" if table.is_idempotency else f"{alias}.gid"


def _render_block(table: TenantRepairTable) -> str:
    alias, aggregate = table.alias, table.aggregate_alias
    return f"""-- AI00: RESUMABLE BACKFILL
UPDATE {table.name} {alias}
LEFT JOIN {table.aggregate_table} {table.aggregate_join_sql}
LEFT JOIN workmanship_auth_users u ON u.gid={alias}.actor_gid
SET {alias}.tenant_gid=COALESCE(
  NULLIF({aggregate}.tenant_gid,''),
  NULLIF(u.team_id,''),
  CASE WHEN u.gid IS NOT NULL THEN CONCAT('user:',{alias}.actor_gid)
       ELSE CONCAT('legacy-unresolved:',SHA2({_legacy_identity_sql(table)},256)) END
)
WHERE ({alias}.tenant_gid IS NULL OR {alias}.tenant_gid='' OR {alias}.tenant_gid LIKE 'user:%')
  AND NOT EXISTS (
    SELECT 1 FROM workmanship_base_schema_migrations m
    WHERE m.migration_id='{MIGRATION_ID}' AND m.status='applied'
  );"""


def render_migration_sql() -> str:
    header = """-- Reconcile historical 0005 replay/audit rows without mutating migration history.
-- The versioned ledger is the explicit completion marker: on a manual replay after
-- success, every statement is a no-op; after a partial failure, each assignment is
-- deterministic and can resume safely.
"""
    return header + "\n" + "\n\n".join(_render_block(table) for table in REPAIR_TABLES) + "\n"
