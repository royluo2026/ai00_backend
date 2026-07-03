"""
backend/infra/vpps_audit_pg.py
────────────────────────────────
PgVppsOperationRepository — psycopg2 PostgreSQL 实现
"""
from datetime import datetime, timezone
from typing import Optional

from backend.domain.vpps_audit.models import VppsOperation
from backend.domain.vpps_audit.repository import IVppsOperationRepository

_TABLE = "bop.vpps_operations"


def _row_to_op(row: dict) -> VppsOperation:
    return VppsOperation(
        gid=row["gid"],
        pbom_version_gid=row["pbom_version_gid"],
        pbom_row_gid=row["pbom_row_gid"],
        operation_type=row["operation_type"],
        rule_no=row.get("rule_no"),
        field_name=row.get("field_name"),
        original_value=row.get("original_value"),
        new_value=row.get("new_value"),
        actor_gid=row["actor_gid"],
        actor_name=row.get("actor_name"),
        created_at=row["created_at"],
        notes=row.get("notes"),
        is_active=row.get("is_active", True),
        reverted_at=row.get("reverted_at"),
        reverted_by_gid=row.get("reverted_by_gid"),
        reverted_by_name=row.get("reverted_by_name"),
    )


class PgVppsOperationRepository(IVppsOperationRepository):
    """
    构造函数接受 psycopg2 connection（由 Router 从 get_conn() 注入）。
    不持有 connection —— 由调用方负责事务提交。
    """

    def __init__(self, conn) -> None:
        self._conn = conn

    def save(self, op: VppsOperation) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {_TABLE}
                    (gid, pbom_version_gid, pbom_row_gid, operation_type,
                     rule_no, field_name, original_value, new_value,
                     actor_gid, actor_name, created_at, notes, is_active)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (gid) DO NOTHING
                """,
                (
                    op.gid, op.pbom_version_gid, op.pbom_row_gid, op.operation_type,
                    op.rule_no, op.field_name, op.original_value, op.new_value,
                    op.actor_gid, op.actor_name, op.created_at, op.notes, op.is_active,
                ),
            )

    def save_batch(self, ops: list[VppsOperation]) -> None:
        if not ops:
            return
        rows = [
            (
                op.gid, op.pbom_version_gid, op.pbom_row_gid, op.operation_type,
                op.rule_no, op.field_name, op.original_value, op.new_value,
                op.actor_gid, op.actor_name, op.created_at, op.notes, op.is_active,
            )
            for op in ops
        ]
        with self._conn.cursor() as cur:
            cur.executemany(
                f"""
                INSERT INTO {_TABLE}
                    (gid, pbom_version_gid, pbom_row_gid, operation_type,
                     rule_no, field_name, original_value, new_value,
                     actor_gid, actor_name, created_at, notes, is_active)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (gid) DO NOTHING
                """,
                rows,
            )

    def get_active_by_version(
        self,
        pbom_version_gid: str,
        operation_type: Optional[str] = None,
    ) -> list[VppsOperation]:
        with self._conn.cursor() as cur:
            if operation_type:
                cur.execute(
                    f"SELECT * FROM {_TABLE} WHERE pbom_version_gid=%s AND operation_type=%s AND is_active=TRUE ORDER BY created_at DESC",
                    (pbom_version_gid, operation_type),
                )
            else:
                cur.execute(
                    f"SELECT * FROM {_TABLE} WHERE pbom_version_gid=%s AND is_active=TRUE ORDER BY created_at DESC",
                    (pbom_version_gid,),
                )
            return [_row_to_op(dict(r)) for r in cur.fetchall()]

    def revert(
        self,
        gid: str,
        reverted_by_gid: str,
        reverted_by_name: str,
    ) -> Optional[VppsOperation]:
        now = datetime.now(tz=timezone.utc)
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE {_TABLE}
                   SET is_active=FALSE, reverted_at=%s, reverted_by_gid=%s, reverted_by_name=%s
                 WHERE gid=%s AND is_active=TRUE
                RETURNING *
                """,
                (now, reverted_by_gid, reverted_by_name, gid),
            )
            row = cur.fetchone()
        return _row_to_op(dict(row)) if row else None

    def get_active_rule4_ignores(self, pbom_version_gid: str) -> set[str]:
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT pbom_row_gid FROM {_TABLE}
                 WHERE pbom_version_gid=%s
                   AND operation_type='rule4_bulk_ignore'
                   AND is_active=TRUE
                """,
                (pbom_version_gid,),
            )
            return {row["pbom_row_gid"] for row in cur.fetchall()}
