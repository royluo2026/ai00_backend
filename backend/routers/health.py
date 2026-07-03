import time

from fastapi import APIRouter

router = APIRouter(tags=["system"])

_start_time = time.time()


@router.get("/health")
def health():
    from backend.db.connection import get_conn, get_pool_status
    import logging
    _log = logging.getLogger(__name__)
    pool = get_pool_status()
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        db_ok = True
    except Exception as e:
        db_ok = False
        _log.error("Health check DB ping failed: %s", e)
    return {
        "status": "ok" if db_ok else "degraded",
        "db": "ok" if db_ok else "error",
        "pool": pool,
        "uptime_s": int(time.time() - _start_time),
    }
