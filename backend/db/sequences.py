"""
backend/db/sequences.py
────────────────────────
替代 PostgreSQL SEQUENCE 的辅助计数表方案。

使用 UPDATE + SELECT 原子操作，等价于 PG 的 nextval()。
"""
from backend.db.connection import get_conn


def next_display_id(seq_name: str) -> int:
    """原子获取下一个序列值，等价于 PG nextval()。
    seq_name 对应 workmanship_display_id_counters.seq_name 列。
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_display_id_counters "
                "SET val = val + 1 WHERE seq_name = %s",
                [seq_name],
            )
            cur.execute(
                "SELECT val FROM workmanship_display_id_counters "
                "WHERE seq_name = %s",
                [seq_name],
            )
            row = cur.fetchone()
            if not row:
                raise RuntimeError(f"序列 {seq_name!r} 不存在，请检查 mysql_schema.sql 初始化")
            return row["val"]
