"""Lease and journal boundary for legacy BOP writes during repository cutover."""
from __future__ import annotations
import hashlib,json,os
from contextlib import contextmanager
from backend.platform_sdk.ids import next_gid
from .connection import get_craft_conn


class MigrationWriteFenced(RuntimeError):pass


def fence_enabled():
    return os.getenv("AI00_BOP_REPOSITORY_MIGRATION_FENCE_ENABLED") == "1"


@contextmanager
def legacy_write_lease(capability_id,context,connection_factory=get_craft_conn):
    if not fence_enabled():
        yield {}
        return
    lease_gid=str(next_gid());actor=str(context.user_gid)
    with connection_factory() as conn,conn.cursor() as cur:
        cur.execute("INSERT IGNORE INTO workmanship_craft_bop_repository_migration_control (migration_key,status) VALUES ('repository-v1','report_only')")
        cur.execute("SELECT status FROM workmanship_craft_bop_repository_migration_control WHERE migration_key='repository-v1' FOR UPDATE");row=cur.fetchone()
        if row and row["status"] in {"fencing","fenced","backfilling","cutover_ready"}:raise MigrationWriteFenced("migration_write_fenced")
        cur.execute("INSERT INTO workmanship_craft_bop_repository_migration_leases (gid,capability_id,actor_gid,expires_at) VALUES (%s,%s,%s,DATE_ADD(NOW(6),INTERVAL 10 MINUTE))",(lease_gid,capability_id,actor))
    try:
        box={};yield box
        digest="sha256:"+hashlib.sha256(json.dumps(box.get("result"),sort_keys=True,default=str).encode()).hexdigest()
        with connection_factory() as conn,conn.cursor() as cur:
            cur.execute("INSERT INTO workmanship_craft_bop_repository_write_journal (lease_gid,capability_id,actor_gid,result_hash,result_json) VALUES (%s,%s,%s,%s,%s)",(lease_gid,capability_id,actor,digest,json.dumps(box.get("result"),default=str,ensure_ascii=False)));cur.execute("DELETE FROM workmanship_craft_bop_repository_migration_leases WHERE gid=%s",(lease_gid,))
    except Exception:
        with connection_factory() as conn,conn.cursor() as cur:cur.execute("DELETE FROM workmanship_craft_bop_repository_migration_leases WHERE gid=%s",(lease_gid,))
        raise
