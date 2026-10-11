import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from hashlib import sha256
from threading import Lock

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend.capability_v2.resource_budget import MemoryPressureSampler, MemorySnapshot

router = APIRouter(tags=["system"])

_start_time = time.time()
_domain_probe_lock = Lock()
_domain_probe_cache: tuple[bytes, float, dict[str, str]] | None = None


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


def connector_signing_readiness() -> str:
    """Report whether this backend can issue governed Connector v2 plans."""
    from plugins.simulation.simulation_backend.application.connector_protocol_v2 import PlanSigner

    try:
        return "ok" if PlanSigner.configured_from_environment() is not None else "not_configured"
    except (TypeError, ValueError):
        return "invalid_configuration"


def domain_db_configuration() -> str:
    from backend.scripts.runtime_preflight import validate_runtime_values

    return "invalid" if validate_runtime_values(os.environ, allow_local=True) else "ok"


def probe_domain_db_accounts(values, connect=None) -> dict[str, str]:
    from backend.scripts.runtime_preflight import REQUIRED_DB_URLS, _runtime_account

    if connect is None:
        import pymysql
        connect = pymysql.connect

    def probe(variable: str) -> tuple[str, str]:
        try:
            params = _runtime_account(values[variable])
            connection = connect(**params, charset="utf8mb4", autocommit=False,
                                 connect_timeout=2, read_timeout=2, write_timeout=2)
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
            finally:
                connection.close()
            return variable, "ok"
        except Exception as error:
            return variable, f"error: {type(error).__name__}"

    with ThreadPoolExecutor(max_workers=4) as executor:
        return dict(executor.map(probe, REQUIRED_DB_URLS))


def domain_db_connectivity() -> dict[str, str]:
    from backend.scripts.runtime_preflight import REQUIRED_DB_URLS

    global _domain_probe_cache
    values = {name: os.environ.get(name, "") for name in REQUIRED_DB_URLS}
    identity = (os.environ.get("AI00_DEPLOY_PROFILE", ""), os.environ.get("TABLE_PREFIX", ""),
                os.environ.get("PUBLIC_URL", ""))
    signature = sha256("\0".join((*identity, *(values[name] for name in REQUIRED_DB_URLS))).encode("utf-8")).digest()
    with _domain_probe_lock:
        now = time.monotonic()
        if _domain_probe_cache is not None:
            previous_signature, expires, result = _domain_probe_cache
            if signature == previous_signature and now < expires:
                return dict(result)
        result = probe_domain_db_accounts(values)
        _domain_probe_cache = (signature, time.monotonic() + (15 if all(
            status == "ok" for status in result.values()) else 3), result)
        return dict(result)


@router.get("/ready")
def ready(request: Request):
    """Deployment readiness: routes, domain configuration and critical DBs must work."""
    checks: dict[str, str] = {}

    memory = memory_readiness()
    checks["memory"] = "ok" if memory.ready else "not_ready"
    checks["connector_plan_signing"] = connector_signing_readiness()

    required_routes = {
        "/api/tasks",
        "/api/projects",
        "/api/bop/versions",
        "/api/v1/plugin-marketplace/registry",
    }
    mounted = set(request.app.openapi().get("paths", {}))
    missing_routes = sorted(required_routes - mounted)
    checks["routes"] = "ok" if not missing_routes else "missing: " + ", ".join(missing_routes)

    checks["domain_db_config"] = domain_db_configuration()
    if checks["domain_db_config"] != "ok":
        return JSONResponse(status_code=503, content={"status": "not_ready", "checks": checks})
    domain_results = domain_db_connectivity()
    from backend.scripts.runtime_preflight import REQUIRED_DB_URLS
    failures = [name for name in REQUIRED_DB_URLS if domain_results.get(name) != "ok"]
    if set(domain_results) != set(REQUIRED_DB_URLS):
        failures.extend(sorted(set(domain_results) - set(REQUIRED_DB_URLS)))
    checks["domain_db_connectivity"] = "ok" if not failures else "failed: " + ", ".join(failures)
    if failures:
        return JSONResponse(status_code=503, content={"status": "not_ready", "checks": checks})

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
