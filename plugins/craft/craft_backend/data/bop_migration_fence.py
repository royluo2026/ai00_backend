"""Lease and journal boundary for legacy BOP writes during repository cutover."""
from __future__ import annotations
import hashlib,json,os
from contextlib import contextmanager
from backend.platform_sdk.ids import next_gid
from .connection import get_craft_conn


class MigrationWriteFenced(RuntimeError):pass


def _rollback_participant(transaction, box):
    if box.get('_rolled_back') or box.get('_connection_closed'):
        return
    try:
        transaction.rollback()
    except BaseException:
        transaction.close()
        box['_connection_closed'] = True
        raise
    else:
        box['_rolled_back'] = True


class LegacyLeaseTransaction:
    """Keep the migration lease until Gateway commits or rejects the write."""
    def __init__(self, transaction, lease, box):
        self._transaction, self._lease, self._box = transaction, lease, box
        self._exited = self._committed = self._closed = False

    def __getattr__(self, name):
        return getattr(self._transaction, name)

    def commit(self):
        if self._committed:
            return
        if self._closed or self._box.get('_rolled_back'):
            raise RuntimeError('legacy lease transaction is closed')
        self._box['_transaction'] = self._transaction
        try:
            try: self._lease.__exit__(None, None, None)
            finally: self._exited = True
            self._transaction.commit()
            self._committed = True
            self._box['_lease_cleaned'] = True
        except BaseException:
            try: self.rollback()
            finally: self.close()
            raise

    def rollback(self):
        if self._committed:
            return
        self._box['_transaction'] = self._transaction
        try:
            _rollback_participant(self._transaction, self._box)
        finally:
            if self._box.get('_rolled_back') or self._box.get('_connection_closed'):
                if not self._exited:
                    error = RuntimeError('legacy transaction rolled back')
                    try: self._lease.__exit__(type(error), error, None)
                    finally: self._exited = True
                cleanup = self._box.get('_cleanup_lease')
                if cleanup and not self._box.get('_lease_cleaned'):
                    cleanup()

    def close(self):
        if self._closed:
            return
        try:
            if not self._committed:
                self.rollback()
        finally:
            if self._committed or self._box.get('_rolled_back') or self._box.get('_connection_closed'):
                if not self._box.get('_connection_closed'):
                    self._transaction.close()
                    self._box['_connection_closed'] = True
        self._closed = True


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
    box={}
    def cleanup():
        if box.get('_lease_cleaned'):
            return
        with connection_factory() as conn,conn.cursor() as cur:
            cur.execute("DELETE FROM workmanship_craft_bop_repository_migration_leases WHERE gid=%s",(lease_gid,))
        box['_lease_cleaned']=True
    box['_cleanup_lease']=cleanup
    def journal(cur, digest):
        cur.execute("INSERT INTO workmanship_craft_bop_repository_write_journal (lease_gid,capability_id,actor_gid,result_hash,result_json) VALUES (%s,%s,%s,%s,%s)",(lease_gid,capability_id,actor,digest,json.dumps(box.get("result"),default=str,ensure_ascii=False)))
        cur.execute("DELETE FROM workmanship_craft_bop_repository_migration_leases WHERE gid=%s",(lease_gid,))
    try:
        yield box
        digest="sha256:"+hashlib.sha256(json.dumps(box.get("result"),sort_keys=True,default=str).encode()).hexdigest()
        transaction=box.get('_transaction')
        if transaction is None:
            with connection_factory() as conn,conn.cursor() as cur:
                journal(cur,digest)
            box['_lease_cleaned']=True
        else:
            with transaction.cursor() as cur:
                journal(cur,digest)
    except BaseException:
        transaction=box.get('_transaction')
        try:
            if transaction is not None:
                _rollback_participant(transaction,box)
        finally:
            if transaction is None or box.get('_rolled_back') or box.get('_connection_closed'):
                cleanup()
        raise
