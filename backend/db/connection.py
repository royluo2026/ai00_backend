"""
backend/db/connection.py
────────────────────────
MySQL 连接池（PyMySQL + dbutils PooledDB）

连接策略：
  - init_pool()  启动时调用，连接失败只打 WARNING，不崩服务。
  - get_conn()   首次真正使用时若池未初始化则再次尝试，仍失败才抛异常。
  这样在本地开发没有 MySQL 实例时，后端服务也可以正常启动。
"""
import logging
import traceback
from contextlib import contextmanager
from typing import Optional

import pymysql
import pymysql.cursors
from dbutils.pooled_db import PooledDB

from backend.config import get_settings

_pool: Optional[PooledDB] = None
_log = logging.getLogger("backend.db")


def init_pool() -> None:
    global _pool
    s = get_settings()
    params = s.get_db_params()
    _log.info(f"🔌 尝试连接数据库: mysql://{params['host']}:{params['port']}/{params['db']}")
    try:
        _pool = PooledDB(
            creator=pymysql,
            maxconnections=20,
            mincached=2,
            blocking=True,
            host=params["host"],
            port=params["port"],
            user=params["user"],
            password=params["password"],
            database=params["db"],
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=3,
            autocommit=False,
        )
        _log.info("✅ MySQL 连接池初始化成功")
    except Exception as e:
        _pool = None
        _log.warning(
            f"⚠️  MySQL 连接池初始化失败（DB 功能不可用）: {e}\n"
            f"   如需使用用户/认证功能，请确保 USERS_DB_URL 指向可用的 MySQL 实例。\n"
            f"   详细堆栈:\n{traceback.format_exc()}"
        )


@contextmanager
def get_conn():
    global _pool
    if _pool is None:
        init_pool()
    if _pool is None:
        raise RuntimeError(
            "MySQL 不可用，请检查 USERS_DB_URL 配置和数据库连接。"
        )
    conn = _pool.connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()  # 归还到池（PooledDB 语义）


def get_pool_status() -> dict:
    """返回连接池基本状态，供 /health 端点使用。"""
    if _pool is None:
        return {"status": "not_initialized"}
    return {"status": "ok"}


def reset_pool() -> None:
    """关闭并重建连接池。gunicorn post_fork 调用，防止 fork 后多 worker 共享父进程连接。"""
    global _pool
    if _pool is not None:
        try:
            _pool._connections = []
        except Exception:
            pass
        _pool = None
    init_pool()


from backend.utils.gid import next_gid


def new_gid() -> str:
    return str(next_gid())
