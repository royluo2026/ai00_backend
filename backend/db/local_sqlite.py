"""
backend/db/local_sqlite.py
───────────────────────────
本地 SQLite 连接管理（自我标注私有数据）

路径优先级：环境变量 LOCAL_SQLITE_PATH → 后端根目录 local_annotations.db
"""
import os
import sqlite3
import threading
from pathlib import Path

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _db_path() -> str:
    return os.environ.get(
        "LOCAL_SQLITE_PATH",
        str(Path(__file__).parent.parent / "local_annotations.db"),
    )


def get_local_db() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            _conn = sqlite3.connect(_db_path(), check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            _ensure_table(_conn)
        return _conn


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS self_annotations (
            item_gid          TEXT NOT NULL,
            user_gid          TEXT NOT NULL DEFAULT '',
            module            TEXT NOT NULL DEFAULT '',
            item_title        TEXT NOT NULL DEFAULT '',
            self_status       TEXT NOT NULL DEFAULT '',
            self_schedule     TEXT NOT NULL DEFAULT '',
            self_note         TEXT NOT NULL DEFAULT '',
            self_attachments  TEXT NOT NULL DEFAULT '[]',
            updated_at        TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (item_gid, user_gid)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sa_user ON self_annotations(user_gid)"
    )
    # 旧数据库迁移：补 item_title 列
    try:
        conn.execute(
            "ALTER TABLE self_annotations ADD COLUMN item_title TEXT NOT NULL DEFAULT ''"
        )
    except Exception:
        pass  # 列已存在
    conn.commit()
