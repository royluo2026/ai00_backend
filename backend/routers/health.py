import os
import time
from dataclasses import dataclass

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend.capability_v2.resource_budget import MemoryPressureSampler, MemorySnapshot

router = APIRouter(tags=["system"])

_start_time = time.time()


@router.get("/health")
def health():
    return {
        "status": "ok",
        "uptime_s": int(time.time() - _start_time),
    }


@dataclass(frozen=True, slots=True)
class MemoryReadiness:
    ready: bool
    snapshot: MemorySnapshot


def memory_readiness(sampler: MemoryPressureSampler | None = None) -> MemoryReadiness:
    snapshot = (sampler or MemoryPressureSampler()).snapshot()
    return MemoryReadiness(ready=snapshot.level != "not_ready", snapshot=snapshot)


@router.get("/ready")
def ready(request: Request):
    """Deployment readiness: routes, migrations and domain DB credentials must work."""
    checks: dict[str, str] = {}

    memory = memory_readiness()
    checks["memory"] = "ok" if memory.ready else "not_ready"

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
        "AI00_PROJECT_MANAGEMENT_DB_URL",
        "AI00_KNOWLEDGE_DB_URL",
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
