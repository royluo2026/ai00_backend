"""Bounded retention for unreferenced automatic VM projection payloads."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta


class VmRetentionService:
    def __init__(self, snapshot_repository, diff_repository, *, clock=None, batch_size=100,
                 max_unreferenced=20, max_age_days=30):
        self.snapshots, self.reports = snapshot_repository, diff_repository
        self.clock = clock or (lambda: datetime.now(UTC))
        self.batch_size = max(1, min(int(batch_size), 200))
        self.max_unreferenced, self.max_age = int(max_unreferenced), timedelta(days=max_age_days)

    def run(self, *, document_gid, tenant_gid, owner_gid):
        scope = {"document_gid": str(document_gid), "tenant_gid": str(tenant_gid), "owner_gid": str(owner_gid)}
        rows = self.snapshots.list_retention_candidates(**scope)
        protected = self.snapshots.protected_snapshot_gids(**scope)
        eligible = [row for row in rows if str(row["snapshot_gid"]) not in protected]
        def captured(row):
            value = row["captured_at"]
            return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        now = self.clock(); now = now.replace(tzinfo=UTC) if now.tzinfo is None else now.astimezone(UTC)
        newest = sorted(eligible, key=lambda row: (captured(row), int(row["sequence"])), reverse=True)
        keep = {str(row["snapshot_gid"]) for row in newest[:self.max_unreferenced]
                if now - captured(row) <= self.max_age}
        stale = [row for row in eligible if str(row["snapshot_gid"]) not in keep]
        stale.sort(key=lambda row: (captured(row), int(row["sequence"])), reverse=True)
        pruned = 0
        for row in stale[:self.batch_size]:
            gid = str(row["snapshot_gid"])
            self.reports.compact_automatic_reports_for_snapshot(gid, tenant_gid=tenant_gid, owner_gid=owner_gid)
            self.snapshots.prune_snapshot_payload(gid, **scope)
            pruned += 1
        return {"pruned": pruned, "protected": len(protected), "eligible": len(eligible),
                "remaining": max(0, len(stale) - pruned)}


__all__ = ["VmRetentionService"]
