from datetime import datetime, timezone
from typing import Optional

from .models import VppsOperation
from .repository import VppsOperationRepository

_TABLE = "workmanship_bop_vpps_operations"
_COLUMNS = (
    "gid,pbom_version_gid,pbom_row_gid,operation_type,rule_no,field_name,"
    "original_value,new_value,actor_gid,actor_name,created_at,notes,is_active,"
    "reverted_at,reverted_by_gid,reverted_by_name"
)


def _row_to_operation(row: dict) -> VppsOperation:
    return VppsOperation(
        gid=row["gid"], pbom_version_gid=row["pbom_version_gid"],
        pbom_row_gid=row["pbom_row_gid"], operation_type=row["operation_type"],
        rule_no=row.get("rule_no"), field_name=row.get("field_name"),
        original_value=row.get("original_value"), new_value=row.get("new_value"),
        actor_gid=row["actor_gid"], actor_name=row.get("actor_name"),
        created_at=row["created_at"], notes=row.get("notes"),
        is_active=bool(row.get("is_active", True)), reverted_at=row.get("reverted_at"),
        reverted_by_gid=row.get("reverted_by_gid"),
        reverted_by_name=row.get("reverted_by_name"),
    )


def _values(op: VppsOperation) -> tuple:
    return (
        op.gid, op.pbom_version_gid, op.pbom_row_gid, op.operation_type,
        op.rule_no, op.field_name, op.original_value, op.new_value,
        op.actor_gid, op.actor_name, op.created_at, op.notes, int(op.is_active),
        op.reverted_at, op.reverted_by_gid, op.reverted_by_name,
    )


class MySqlVppsOperationRepository(VppsOperationRepository):
    def __init__(self, conn) -> None:
        self._conn = conn

    def save(self, op: VppsOperation) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                f"INSERT IGNORE INTO {_TABLE} ({_COLUMNS}) VALUES ({','.join(['%s'] * 16)})",
                _values(op),
            )

    def save_batch(self, ops: list[VppsOperation]) -> None:
        if not ops:
            return
        with self._conn.cursor() as cur:
            cur.executemany(
                f"INSERT IGNORE INTO {_TABLE} ({_COLUMNS}) VALUES ({','.join(['%s'] * 16)})",
                [_values(op) for op in ops],
            )

    def get_active_by_version(
        self, pbom_version_gid: str, operation_type: Optional[str] = None,
    ) -> list[VppsOperation]:
        sql = f"SELECT {_COLUMNS} FROM {_TABLE} WHERE pbom_version_gid=%s AND is_active=1"
        params: list[object] = [pbom_version_gid]
        if operation_type:
            sql += " AND operation_type=%s"
            params.append(operation_type)
        sql += " ORDER BY created_at DESC"
        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            return [_row_to_operation(dict(row)) for row in cur.fetchall()]

    def revert(
        self, gid: str, reverted_by_gid: str, reverted_by_name: str,
    ) -> Optional[VppsOperation]:
        now = datetime.now(tz=timezone.utc)
        with self._conn.cursor() as cur:
            cur.execute(
                f"UPDATE {_TABLE} SET is_active=0,reverted_at=%s,reverted_by_gid=%s,"
                "reverted_by_name=%s WHERE gid=%s AND is_active=1",
                (now, reverted_by_gid, reverted_by_name, gid),
            )
            if cur.rowcount != 1:
                return None
            cur.execute(f"SELECT {_COLUMNS} FROM {_TABLE} WHERE gid=%s", (gid,))
            row = cur.fetchone()
        return _row_to_operation(dict(row)) if row else None

    def get_active_rule4_ignores(self, pbom_version_gid: str) -> set[str]:
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT pbom_row_gid FROM {_TABLE} WHERE pbom_version_gid=%s "
                "AND operation_type='rule4_bulk_ignore' AND is_active=1",
                (pbom_version_gid,),
            )
            return {str(row["pbom_row_gid"]) for row in cur.fetchall()}
