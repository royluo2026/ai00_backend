"""Administrator-only, payload-free runtime resource diagnostics."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException

from backend.capability_v2.gateway import get_default_gateway
from backend.capability_v2.resource_budget import MemoryPressureSampler
from backend.routers.deps import get_current_user_claims_only


router = APIRouter(prefix="/admin", tags=["admin", "runtime"])


def require_runtime_admin(current_user: dict = Depends(get_current_user_claims_only)) -> dict:
    if current_user.get("system_role") != "super_admin" and current_user.get("org_role") != "super_admin":
        raise HTTPException(status_code=403, detail="权限不足")
    return current_user


@router.get("/runtime-diagnostics")
def runtime_diagnostics(_current_user: dict = Depends(require_runtime_admin)) -> dict:
    snapshot = MemoryPressureSampler().snapshot()
    records = get_default_gateway().recent_metrics()
    return {
        "pid": os.getpid(),
        "worker_count": int(os.getenv("AI00_WEB_WORKERS", "1")),
        "memory": {
            "rss_bytes": snapshot.rss_bytes,
            "cgroup_current_bytes": snapshot.cgroup_current_bytes,
            "cgroup_limit_bytes": snapshot.cgroup_limit_bytes,
            "ratio": snapshot.ratio,
            "level": snapshot.level,
        },
        "capabilities": [
            {
                "capability_id": item.capability_id,
                "major_version": item.major_version,
                "owner_domain": item.owner_domain,
                "consumer_type": item.consumer_type,
                "consumer_key_hash": item.consumer_key_hash,
                "elapsed_ms": item.elapsed_ms,
                "output_bytes": item.output_bytes,
                "rss_before_bytes": item.rss_before_bytes,
                "rss_after_bytes": item.rss_after_bytes,
                "cgroup_ratio": item.cgroup_ratio,
                "in_flight": item.in_flight,
                "cancelled": item.cancelled,
                "error_code": item.error_code,
            }
            for item in records[-50:]
        ],
    }
