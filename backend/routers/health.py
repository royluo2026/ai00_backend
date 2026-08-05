import os
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

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


@router.get("/ready")
def ready(request: Request):
    """Deployment readiness: routes, migrations and domain DB credentials must work."""
    checks: dict[str, str] = {}

    required_routes = {
        "/api/tasks",
        "/api/projects",
        "/api/bop/versions",
        "/api/v1/plugin-marketplace/registry",
    }
    mounted = set(request.app.openapi().get("paths", {}))
    missing_routes = sorted(required_routes - mounted)
    checks["routes"] = "ok" if not missing_routes else "missing: " + ", ".join(missing_routes)

    required_urls = (
        "USERS_DB_URL",
        "AI00_CRAFT_DB_URL",
        "AI00_AGENT_DB_URL",
        "AI00_SIMULATION_DB_URL",
        "AI00_DEVICE_DB_URL",
    )
    missing_urls = [name for name in required_urls if not os.getenv(name, "").strip()]
    checks["domain_db_config"] = "ok" if not missing_urls else "missing: " + ", ".join(missing_urls)

    try:
        from backend.db.connection import get_conn
        from backend.db.migration_readiness import assert_migrations_applied
        with get_conn() as conn:
            assert_migrations_applied(conn)
        checks["migrations"] = "ok"
    except Exception as exc:
        checks["migrations"] = f"error: {type(exc).__name__}"

    try:
        from craft_backend.data.connection import get_craft_conn
        with get_craft_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        checks["craft_db"] = "ok"
    except Exception as exc:
        checks["craft_db"] = f"error: {type(exc).__name__}"

    is_ready = all(value == "ok" for value in checks.values())
    payload = {"status": "ready" if is_ready else "not_ready", "checks": checks}
    return JSONResponse(status_code=200 if is_ready else 503, content=payload)
