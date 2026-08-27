"""Legacy workbench-home HTTP adapter backed only by Capability Gateway."""
from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.capability_v2.gateway import get_default_gateway
from backend.platform_sdk.access import build_access_scope
from backend.platform_sdk.auth import get_authenticated_principal, get_current_user
from backend.platform_sdk.project_management import (
    build_web_compatibility_envelope,
    invoke_compatibility,
)


router = APIRouter(prefix="/api/workbench", tags=["workbench"])


def _items(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    values = data.get("data")
    return [dict(item) for item in values] if isinstance(values, list) else []


def _gids(value: str | None) -> tuple[str | None, ...]:
    values = tuple(dict.fromkeys(part.strip() for part in (value or "").split(",") if part.strip()))
    return values or (None,)


async def _invoke(
    request: Request,
    user: dict[str, Any],
    principal: Any,
    gateway: Any,
    capability_id: str,
    arguments: dict[str, Any],
) -> Any:
    base_request_id = request.headers.get("X-Request-ID") or f"workbench_{uuid4().hex}"
    request_id = f"{base_request_id}_{capability_id.replace('.', '_')}"
    result = await invoke_compatibility(
        gateway,
        build_web_compatibility_envelope(
            gateway,
            capability_id=capability_id,
            payload={"arguments": arguments},
            current_user=user,
            principal=principal,
            request_id=request_id,
            trace_id=request.headers.get("X-Trace-ID") or base_request_id,
        ),
    )
    if not result.ok:
        code = result.error.code if result.error else ""
        status = {"not_found": 404, "forbidden": 403, "invalid_input": 400}.get(code, 422)
        detail = result.error.model_dump(mode="json") if result.error else None
        raise HTTPException(status, detail)
    return result.data["data"]


async def execute_constituents(
    request: Request,
    user: dict[str, Any],
    principal: Any,
    gateway: Any,
    calls: tuple[tuple[str, dict[str, Any]], ...],
) -> tuple[Any | None, ...]:
    """Execute reviewed BFF constituents in order and omit only failed values."""
    values: list[Any | None] = []
    for capability_id, arguments in calls:
        try:
            values.append(await _invoke(request, user, principal, gateway, capability_id, arguments))
        except Exception:
            values.append(None)
    return tuple(values)


@router.get("/home", deprecated=True)
async def get_workbench_home(
    request: Request,
    current_user=Depends(get_current_user),
    principal=Depends(get_authenticated_principal),
    gateway=Depends(get_default_gateway),
):
    scope = build_access_scope(current_user)
    project_value, follow_value = await execute_constituents(
        request, current_user, principal, gateway,
        (
            ("project.project.read.atomic.projects_search", {
                "include_deleted": False, "include_archived": False, "scope": scope,
            }),
            ("project.follow.read.atomic.follows_list", {"item_type": None}),
        ),
    )
    projects = _items(project_value)
    follows = _items(follow_value)
    role = str(current_user.get("org_role") or current_user.get("system_role") or "member")
    return {
        "today_items": [],
        "my_contexts": [
            {
                "project_gid": str(project.get("gid") or ""),
                "project_name": str(project.get("name") or ""),
                "role": role,
                "section_gid": None,
            }
            for project in projects
            if project.get("gid")
        ],
        "alerts": [],
        "recent_follows": follows,
    }


@router.get("/panel1", deprecated=True)
async def get_workbench_panel1(
    request: Request,
    sources: str = Query("task,issue"),
    task_lists: str | None = Query(None),
    issue_lists: str | None = Query(None),
    current_user=Depends(get_current_user),
    principal=Depends(get_authenticated_principal),
    gateway=Depends(get_default_gateway),
):
    requested = tuple(dict.fromkeys(part.strip() for part in sources.split(",") if part.strip()))
    scope = build_access_scope(current_user)
    items: list[dict[str, Any]] = []
    for source in requested:
        if source not in {"task", "issue"}:
            continue
        capability_id = f"project.{source}.read.atomic.{source}s_search"
        for list_gid in _gids(task_lists if source == "task" else issue_lists):
            arguments = {
                "project_gid": None,
                "status": None,
                "list_gid": list_gid,
                "q": None,
                "page_size": 200,
                "scope": scope,
            }
            if source == "task":
                arguments["scheduled_date_from"] = None
            value, = await execute_constituents(
                request, current_user, principal, gateway, ((capability_id, arguments),),
            )
            items.extend(_items(value))
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for item in items:
        key = (str(item.get("item_type") or ""), str(item.get("gid") or ""))
        unique[key] = item
    result = list(unique.values())
    return {"items": result, "total": len(result)}


__all__ = ["execute_constituents", "router"]
