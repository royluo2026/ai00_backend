"""Fenced, resumable legacy BOP repository backfill; report-only by default."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any

from backend.platform_sdk.ids import next_gid
from plugins.craft.craft_backend.data.connection import get_craft_conn

MIGRATION_KEY = "repository-v1"


class MigrationFenced(RuntimeError):
    pass


@dataclass(frozen=True)
class LegacyOutcome:
    operation_gid: str


@dataclass(frozen=True)
class BackfillResult:
    migrated_operation_gids: tuple[str, ...]
    lost_write_count: int
    final_high_water_gid: str | None


class BackfillHarness:
    """Small race model used to prove the fence protocol independently of MySQL."""

    def __init__(self, operations=()):
        self.operations = list(map(str, operations))
        self.migrated: set[str] = set()
        self.preliminary_gid = self.final_gid = self.fence_token = None

    def preliminary(self):
        self.preliminary_gid = max(self.operations, key=int) if self.operations else None
        return self.preliminary_gid

    def legacy_write_after(self, _watermark):
        if self.fence_token:
            raise MigrationFenced("migration_write_fenced")
        gid = str(max(map(int, self.operations), default=0) + 1)
        self.operations.append(gid)
        return LegacyOutcome(gid)

    def activate_fence_and_drain(self):
        if not self.fence_token:
            self.fence_token = str(next_gid())
            self.final_gid = max(self.operations, key=int) if self.operations else None
        return self.fence_token

    def backfill(self, limit=None):
        if not self.fence_token:
            raise RuntimeError("fence_required")
        pending = [x for x in self.operations if (self.final_gid is None or int(x) <= int(self.final_gid)) and x not in self.migrated]
        self.migrated.update(pending[:limit])
        expected = {x for x in self.operations if self.final_gid is None or int(x) <= int(self.final_gid)}
        return BackfillResult(tuple(sorted(self.migrated, key=int)), len(expected - self.migrated), self.final_gid)


def mutation_enabled(*, requested):
    return bool(requested and os.getenv("AI00_BOP_REPOSITORY_BACKFILL_MUTATION") == "1")


def _json(value: Any) -> str:
    if value is None:
        return "{}"
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_json(value).encode()).hexdigest()


class SqlBackfill:
    """Project the fenced legacy snapshot into one Craft team space per project."""

    def __init__(self, tenant_gid: str, actor_gid: str, connection_factory=get_craft_conn):
        if not tenant_gid or not actor_gid:
            raise ValueError("tenant_gid_and_actor_gid_required")
        self.tenant_gid, self.actor_gid = str(tenant_gid), str(actor_gid)
        self.connection_factory = connection_factory

    def report(self):
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) total FROM workmanship_bop_bop_versions WHERE is_deleted=FALSE")
            versions = int(cur.fetchone()["total"])
            cur.execute("SELECT COUNT(*) total FROM workmanship_bop_bop_entries WHERE is_deleted=FALSE")
            entries = int(cur.fetchone()["total"])
            cur.execute("SELECT COUNT(*) total FROM workmanship_bop_bop_versions WHERE is_deleted=FALSE AND project_gid IS NULL")
            unscoped = int(cur.fetchone()["total"])
        return {"mode": "report_only", "legacy_versions": versions, "legacy_entries": entries,
                "unscoped_versions": unscoped, "mutation_required": True, "cutover_enabled": False}

    def preliminary(self):
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute("INSERT IGNORE INTO workmanship_craft_bop_repository_migration_control (migration_key,status) VALUES (%s,'report_only')", (MIGRATION_KEY,))
            cur.execute("SELECT preliminary_high_water_gid,preliminary_at FROM workmanship_craft_bop_repository_migration_control WHERE migration_key=%s FOR UPDATE", (MIGRATION_KEY,))
            row = cur.fetchone()
            if row["preliminary_at"] is None:
                cur.execute("SELECT COALESCE(MAX(journal_seq),0) high_water FROM workmanship_craft_bop_repository_write_journal")
                high = int(cur.fetchone()["high_water"])
                cur.execute("UPDATE workmanship_craft_bop_repository_migration_control SET preliminary_high_water_gid=%s,preliminary_at=NOW(6),row_version=row_version+1 WHERE migration_key=%s", (high, MIGRATION_KEY))
            else:
                high = int(row["preliminary_high_water_gid"] or 0)
        return {"preliminary_high_water_gid": str(high)}

    def activate_fence(self):
        """Activate once; retry this call until every pre-fence lease has drained."""
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute("SELECT fence_activation_gid FROM workmanship_craft_bop_repository_migration_control WHERE migration_key=%s FOR UPDATE", (MIGRATION_KEY,))
            row = cur.fetchone()
            if not row:
                raise RuntimeError("preliminary_required")
            token = str(row["fence_activation_gid"] or next_gid())
            cur.execute("DELETE FROM workmanship_craft_bop_repository_migration_leases WHERE expires_at<=NOW(6)")
            cur.execute("SELECT COUNT(*) total FROM workmanship_craft_bop_repository_migration_leases")
            active = int(cur.fetchone()["total"])
            cur.execute("UPDATE workmanship_craft_bop_repository_migration_control SET status='fencing',fence_activation_gid=%s,active_lease_count=%s,row_version=row_version+1 WHERE migration_key=%s", (token, active, MIGRATION_KEY))
        if active:
            return {"fence_activation_gid": token, "active_lease_count": active, "drained": False}
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute("SELECT COALESCE(MAX(journal_seq),0) high_water FROM workmanship_craft_bop_repository_write_journal")
            final = int(cur.fetchone()["high_water"])
            cur.execute("UPDATE workmanship_craft_bop_repository_migration_control SET status='fenced',final_high_water_gid=%s,fenced_at=COALESCE(fenced_at,NOW(6)),active_lease_count=0,row_version=row_version+1 WHERE migration_key=%s", (final, MIGRATION_KEY))
        return {"fence_activation_gid": token, "active_lease_count": 0, "drained": True, "final_high_water_gid": str(final)}

    def backfill(self, limit=500):
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute("SELECT status FROM workmanship_craft_bop_repository_migration_control WHERE migration_key=%s FOR UPDATE", (MIGRATION_KEY,))
            row = cur.fetchone()
            if not row or row["status"] not in {"fenced", "backfilling", "cutover_ready"}:
                raise RuntimeError("fence_required")
            cur.execute("UPDATE workmanship_craft_bop_repository_migration_control SET status='backfilling',row_version=row_version+1 WHERE migration_key=%s", (MIGRATION_KEY,))
        versions = entries = quarantined = 0
        while True:
            batch = self._pending_versions(limit)
            if not batch:
                break
            for version in batch:
                if not version.get("project_gid"):
                    self._quarantine("version", version["gid"], "project_required", version)
                    quarantined += 1
                    continue
                self._migrate_version(version)
                versions += 1
                entries += self._migrate_entries(version)
        return {**self.reconcile(), "migrated_versions": versions, "migrated_entries": entries,
                "quarantined_this_run": quarantined}

    def _pending_versions(self, limit):
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute("SELECT v.* FROM workmanship_bop_bop_versions v LEFT JOIN workmanship_craft_bop_repository_id_map m ON m.legacy_kind='version' AND m.legacy_gid=CAST(v.gid AS UNSIGNED) LEFT JOIN workmanship_craft_bop_repository_quarantine q ON q.legacy_kind='version' AND q.legacy_gid=CAST(v.gid AS UNSIGNED) AND q.resolved_at IS NULL WHERE v.is_deleted=FALSE AND m.legacy_gid IS NULL AND q.legacy_gid IS NULL ORDER BY CAST(v.gid AS UNSIGNED) LIMIT %s", (limit,))
            return list(cur.fetchall())

    def _migrate_version(self, version):
        legacy_gid, project_gid = str(version["gid"]), str(version["project_gid"])
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute("SELECT gid FROM workmanship_craft_bop_repositories WHERE tenant_gid=%s AND project_gid=%s AND deleted_at IS NULL", (self.tenant_gid, project_gid))
            row = cur.fetchone()
            repository_gid = str(row["gid"]) if row else str(next_gid())
            if not row:
                cur.execute("INSERT INTO workmanship_craft_bop_repositories (gid,tenant_gid,project_gid,created_by) VALUES (%s,%s,%s,%s)", (repository_gid, self.tenant_gid, project_gid, self.actor_gid))
                space_gid, head_gid = str(next_gid()), str(next_gid())
                cur.execute("INSERT INTO workmanship_craft_bop_spaces (gid,repository_gid,tenant_gid,space_kind,created_by) VALUES (%s,%s,%s,'team',%s)", (space_gid, repository_gid, self.tenant_gid, self.actor_gid))
                cur.execute("INSERT INTO workmanship_craft_bop_space_heads (gid,space_gid,tenant_gid,content_hash,updated_by) VALUES (%s,%s,%s,%s,%s)", (head_gid, space_gid, self.tenant_gid, _hash([]), self.actor_gid))
            cur.execute("INSERT INTO workmanship_craft_bop_repository_id_map (legacy_kind,legacy_gid,repository_gid,mapping_hash) VALUES ('version',%s,%s,%s)", (legacy_gid, repository_gid, _hash({"legacy_gid": legacy_gid, "project_gid": project_gid})))

    def _migrate_entries(self, version):
        legacy_version_gid = str(version["gid"])
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute("SELECT repository_gid FROM workmanship_craft_bop_repository_id_map WHERE legacy_kind='version' AND legacy_gid=%s", (legacy_version_gid,))
            repository_gid = str(cur.fetchone()["repository_gid"])
            cur.execute("SELECT h.gid FROM workmanship_craft_bop_space_heads h JOIN workmanship_craft_bop_spaces s ON s.gid=h.space_gid WHERE s.repository_gid=%s AND s.space_kind='team' AND s.deleted_at IS NULL", (repository_gid,))
            head_gid = str(cur.fetchone()["gid"])
            cur.execute("SELECT e.* FROM workmanship_bop_bop_entries e LEFT JOIN workmanship_craft_bop_repository_id_map m ON m.legacy_kind='entry' AND m.legacy_gid=CAST(e.gid AS UNSIGNED) WHERE e.version_gid=%s AND e.is_deleted=FALSE AND m.legacy_gid IS NULL ORDER BY COALESCE(e.level,0),e.sort_order,CAST(e.gid AS UNSIGNED)", (legacy_version_gid,))
            rows = list(cur.fetchall())
        migrated = 0
        for entry in rows:
            parent_node_gid = None
            if entry.get("parent_gid"):
                with self.connection_factory() as conn, conn.cursor() as cur:
                    cur.execute("SELECT logical_gid FROM workmanship_craft_bop_repository_id_map WHERE legacy_kind='entry' AND legacy_gid=%s", (str(entry["parent_gid"]),))
                    parent = cur.fetchone()
                if not parent:
                    self._quarantine("entry", entry["gid"], "parent_not_migrated", {"parent_gid": entry["parent_gid"]})
                    continue
                parent_node_gid = str(parent["logical_gid"])
            keys = ("title", "vpps", "vpps_desc", "vpps_part", "part_feed", "catia_occurrence_name", "parent_vpps_name", "process_flow_pic", "process_chart_pic", "child_vpps", "bom_row_owner", "meta")
            properties = {key: entry.get(key) for key in keys}
            content_hash = _hash({"parent": parent_node_gid, "type": entry["node_type"], "order": entry["sort_order"], "properties": properties})
            node_gid, revision_gid = str(next_gid()), str(next_gid())
            with self.connection_factory() as conn, conn.cursor() as cur:
                cur.execute("INSERT INTO workmanship_craft_bop_nodes (gid,repository_gid,tenant_gid,lineage_gid,source_version_gid,created_by) VALUES (%s,%s,%s,%s,%s,%s)", (node_gid, repository_gid, self.tenant_gid, node_gid, legacy_version_gid, self.actor_gid))
                cur.execute("INSERT INTO workmanship_craft_bop_node_revisions (gid,node_gid,tenant_gid,parent_node_gid,node_type,order_key,properties_json,content_hash,actor_gid,actor_type,evidence_refs_json) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'system',%s)", (revision_gid, node_gid, self.tenant_gid, parent_node_gid, str(entry["node_type"])[:32], str(entry["sort_order"]), _json(properties), content_hash, self.actor_gid, _json({"legacy_version_gid": legacy_version_gid, "legacy_entry_gid": str(entry["gid"])})))
                cur.execute("INSERT INTO workmanship_craft_bop_space_head_members (gid,space_head_gid,member_kind,logical_gid,node_revision_gid,is_tombstone) VALUES (%s,%s,'node',%s,%s,0)", (str(next_gid()), head_gid, node_gid, revision_gid))
                cur.execute("INSERT INTO workmanship_craft_bop_repository_id_map (legacy_kind,legacy_gid,repository_gid,logical_gid,revision_gid,mapping_hash) VALUES ('entry',%s,%s,%s,%s,%s)", (str(entry["gid"]), repository_gid, node_gid, revision_gid, content_hash))
            migrated += 1
        return migrated

    def _quarantine(self, kind, gid, reason, details):
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute("INSERT IGNORE INTO workmanship_craft_bop_repository_quarantine (gid,legacy_kind,legacy_gid,reason_code,details_json) VALUES (%s,%s,%s,%s,%s)", (str(next_gid()), kind, str(gid), reason, _json(details)))

    def reconcile(self):
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute("SELECT preliminary_high_water_gid,final_high_water_gid FROM workmanship_craft_bop_repository_migration_control WHERE migration_key=%s", (MIGRATION_KEY,))
            control = cur.fetchone()
            cur.execute("SELECT COUNT(*) total FROM workmanship_craft_bop_repository_quarantine WHERE resolved_at IS NULL")
            quarantine = int(cur.fetchone()["total"])
            queries = {
                "versions": "SELECT COUNT(*) total FROM workmanship_bop_bop_versions v LEFT JOIN workmanship_craft_bop_repository_id_map m ON m.legacy_kind='version' AND m.legacy_gid=CAST(v.gid AS UNSIGNED) LEFT JOIN workmanship_craft_bop_repository_quarantine q ON q.legacy_kind='version' AND q.legacy_gid=CAST(v.gid AS UNSIGNED) AND q.resolved_at IS NULL WHERE v.is_deleted=FALSE AND m.legacy_gid IS NULL AND q.legacy_gid IS NULL",
                "entries": "SELECT COUNT(*) total FROM workmanship_bop_bop_entries e LEFT JOIN workmanship_craft_bop_repository_id_map m ON m.legacy_kind='entry' AND m.legacy_gid=CAST(e.gid AS UNSIGNED) LEFT JOIN workmanship_craft_bop_repository_quarantine q ON q.legacy_kind='entry' AND q.legacy_gid=CAST(e.gid AS UNSIGNED) AND q.resolved_at IS NULL WHERE e.is_deleted=FALSE AND m.legacy_gid IS NULL AND q.legacy_gid IS NULL",
            }
            counts = {}
            for key, query in queries.items():
                cur.execute(query)
                counts[key] = int(cur.fetchone()["total"])
            start, end = int(control["preliminary_high_water_gid"] or 0), int(control["final_high_water_gid"] or 0)
            cur.execute("SELECT COUNT(*) total FROM workmanship_craft_bop_repository_write_journal WHERE journal_seq>%s AND journal_seq<=%s", (start, end))
            delta = int(cur.fetchone()["total"])
            ready = quarantine == counts["versions"] == counts["entries"] == 0
            if ready:
                cur.execute("UPDATE workmanship_craft_bop_repository_migration_control SET status='cutover_ready',row_version=row_version+1 WHERE migration_key=%s AND status='backfilling'", (MIGRATION_KEY,))
        return {"lost_write_count": counts["versions"] + counts["entries"], "unresolved_quarantine": quarantine,
                "delta_journal_count": delta, "cutover_ready": ready, "cutover_enabled": False,
                "final_high_water_gid": str(end)}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--tenant-gid", default=os.getenv("AI00_BOP_REPOSITORY_BACKFILL_TENANT_GID"))
    parser.add_argument("--actor-gid", default=os.getenv("AI00_BOP_REPOSITORY_BACKFILL_ACTOR_GID"))
    args = parser.parse_args(argv)
    if not mutation_enabled(requested=args.apply):
        print(json.dumps({"mode": "report_only", "mutation_requested": args.apply, "requires_fence": True, "cutover_enabled": False}))
        return 0
    runner = SqlBackfill(args.tenant_gid, args.actor_gid)
    runner.preliminary()
    fence = runner.activate_fence()
    if not fence["drained"]:
        print(json.dumps({"mode": "fencing", **fence}))
        return 2
    print(json.dumps({"mode": "apply", **runner.backfill()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
