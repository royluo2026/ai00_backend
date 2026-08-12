"""Legacy Task/Issue HTTP adapter; Project owns behavior and SQL."""
from __future__ import annotations

from typing import Optional
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from backend.capability_v2.gateway import get_default_gateway
from backend.platform_sdk.access import build_access_scope
from backend.platform_sdk.auth import get_authenticated_principal, get_current_user
from backend.platform_sdk.project_management import build_web_compatibility_envelope, invoke_compatibility

router = APIRouter(tags=["promotion"])


class TaskBody(BaseModel):
    title: str
    description: str = ""
    owner_gid: str = ""
    assignee_team_gid: Optional[str] = None
    project_gid: Optional[str] = None
    status: str = "pending"
    priority: str = "normal"
    source_ref: dict = {}
    review_date: Optional[str] = None
    meeting_level: str = "none"
    meeting_doc_link: Optional[str] = None
    progress_logs: list = []
    due_date: Optional[str] = None
    plan_start: Optional[str] = None
    plan_end: Optional[str] = None
    actual_start: Optional[str] = None
    actual_end: Optional[str] = None
    share_scope: str = "project"
    list_gid: Optional[str] = None
    local_gid: Optional[str] = None
    local_created_at: Optional[float] = None
    attachments: list = []
    scheduled_date: Optional[str] = None
    scheduled_start_time: Optional[str] = None
    time_estimate: Optional[int] = None
    is_deleted: bool = False
    parent_task_gid: Optional[str] = None
    canvas_x: Optional[float] = None
    canvas_y: Optional[float] = None
    completion: int = 0
    node_type: str = "normal"
    canvas_icon: str = "star"
    feishu_assignee_open_id: Optional[str] = None
    feishu_assignee_name: Optional[str] = None
    feishu_group_chat_id: Optional[str] = None
    feishu_group_name: Optional[str] = None
    feishu_groups: list = []
    feishu_docs: list = []


class TaskPromoteBody(TaskBody): pass


class IssueBody(BaseModel):
    title: str
    description: str = ""
    severity: str = "low"
    status: str = "open"
    owner_gid: str = ""
    assignee_team_gid: Optional[str] = None
    project_gid: Optional[str] = None
    tracking_refs: list = []
    occurrence_root_cause: Optional[str] = None
    escape_root_cause: Optional[str] = None
    interim_action: Optional[str] = None
    permanent_action: Optional[str] = None
    source_ref: dict = {}
    related_task_gid: Optional[str] = None
    related_knowledge_gid: Optional[str] = None
    approval_order_gid: Optional[str] = None
    bop_entry_gid: Optional[str] = None
    share_scope: str = "project"
    list_gid: Optional[str] = None
    attachments: list = []
    feishu_assignee_open_id: Optional[str] = None
    feishu_assignee_name: Optional[str] = None
    feishu_group_chat_id: Optional[str] = None
    feishu_group_name: Optional[str] = None
    feishu_groups: list = []
    feishu_docs: list = []


class IssuePromoteBody(IssueBody):
    local_gid: Optional[str] = None
    local_created_at: Optional[float] = None


class TaskDepBody(BaseModel):
    source_gid: str
    target_gid: str
    edge_type: str = "prerequisite"
    dep_condition: str = "done"
    dep_group: Optional[str] = None
    label: str = ""


def _task_scope_clauses(current_user: dict, alias: str) -> tuple[str, list[str]]:
    scope = build_access_scope(current_user); clauses = [f"{alias}.owner_user_gid = %s", f"{alias}.share_scope = 'global'"]; params = [scope["user_gid"]]
    if scope["team_member_gids"]:
        placeholders = ",".join(["%s"] * len(scope["team_member_gids"])); clauses.append(f"({alias}.share_scope = 'team' AND {alias}.owner_user_gid IN ({placeholders}))"); params.extend(scope["team_member_gids"])
    if scope["project_gids"]:
        placeholders = ",".join(["%s"] * len(scope["project_gids"])); clauses.append(f"({alias}.share_scope = 'project' AND {alias}.project_gid IN ({placeholders}))"); params.extend(scope["project_gids"])
    return "(" + " OR ".join(clauses) + ")", params


async def _invoke(request, user, principal, gateway, capability_id, operation, arguments, *, write=False):
    request_id = request.headers.get("X-Request-ID") or f"project_{uuid4().hex}"
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(gateway, capability_id=capability_id, payload={"operation": operation, "arguments": arguments}, current_user=user, principal=principal, request_id=request_id, trace_id=request.headers.get("X-Trace-ID") or request_id, idempotency_key=request.headers.get("X-Idempotency-Key") if write else None, approval_reference=request.headers.get("X-Capability-Approval") if write else None))
    if not result.ok:
        code = result.error.code if result.error else ""; raise HTTPException({"not_found": 404, "forbidden": 403, "invalid_input": 400}.get(code, 422), result.error.model_dump(mode="json") if result.error else None)
    return result.data["data"]


async def _task_call(request, user, principal, gateway, operation, args, write=False): return await _invoke(request, user, principal, gateway, "project.task.change.apply" if write else "project.task.read", operation, args, write=write)
async def _issue_call(request, user, principal, gateway, operation, args, write=False): return await _invoke(request, user, principal, gateway, "project.issue.change.apply" if write else "project.issue.read", operation, args, write=write)


@router.get("/api/tasks")
async def list_cloud_tasks(request: Request, project_gid: Optional[str] = Query(None), status: Optional[str] = Query(None), list_gid: Optional[str] = Query(None), scheduled_date_from: Optional[str] = Query(None), q: Optional[str] = Query(None), page_size: Optional[int] = Query(None), current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _task_call(request, current_user, principal, gateway, "tasks.search", {"project_gid": project_gid, "status": status, "list_gid": list_gid, "scheduled_date_from": scheduled_date_from, "q": q, "page_size": page_size, "scope": build_access_scope(current_user)})


@router.post("/api/tasks", status_code=201)
async def create_cloud_task(body: TaskBody, request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)): return await _task_call(request, current_user, principal, gateway, "tasks.create", body.model_dump(), True)


@router.get("/api/tasks/promote")
def get_promote_placeholder(): return {"detail": "POST to this endpoint to promote a local task"}


@router.post("/api/tasks/promote", status_code=201)
async def promote_task(body: TaskPromoteBody, request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)): return await _task_call(request, current_user, principal, gateway, "tasks.promote", body.model_dump(), True)


@router.get("/api/tasks/{gid}")
async def get_cloud_task(gid: str, request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)): return await _task_call(request, current_user, principal, gateway, "tasks.get", {"gid": gid})


@router.put("/api/tasks/{gid}")
@router.patch("/api/tasks/{gid}")
async def update_cloud_task(gid: str, body: dict, request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)): return await _task_call(request, current_user, principal, gateway, "tasks.update", {"gid": gid, "updates": body}, True)


@router.delete("/api/tasks/{gid}")
async def delete_cloud_task(gid: str, request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)): return await _task_call(request, current_user, principal, gateway, "tasks.delete", {"gid": gid}, True)


@router.get("/api/issues")
async def list_cloud_issues(request: Request, project_gid: Optional[str] = Query(None), status: Optional[str] = Query(None), list_gid: Optional[str] = Query(None), q: Optional[str] = Query(None), page_size: Optional[int] = Query(None), current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _issue_call(request, current_user, principal, gateway, "issues.search", {"project_gid": project_gid, "status": status, "list_gid": list_gid, "q": q, "page_size": page_size, "scope": build_access_scope(current_user)})


@router.post("/api/issues", status_code=201)
async def create_cloud_issue(body: IssueBody, request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)): return await _issue_call(request, current_user, principal, gateway, "issues.create", body.model_dump(), True)


@router.get("/api/issues/promote")
def get_issue_promote_placeholder(): return {"detail": "POST to this endpoint to promote a local issue"}


@router.post("/api/issues/promote", status_code=201)
async def promote_issue(body: IssuePromoteBody, request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)): return await _issue_call(request, current_user, principal, gateway, "issues.promote", body.model_dump(), True)


@router.get("/api/issues/{gid}")
async def get_cloud_issue(gid: str, request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)): return await _issue_call(request, current_user, principal, gateway, "issues.get", {"gid": gid})


@router.put("/api/issues/{gid}")
@router.patch("/api/issues/{gid}")
async def update_cloud_issue(gid: str, body: dict, request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)): return await _issue_call(request, current_user, principal, gateway, "issues.update", {"gid": gid, "updates": body}, True)


@router.delete("/api/issues/{gid}")
async def delete_cloud_issue(gid: str, request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)): return await _issue_call(request, current_user, principal, gateway, "issues.delete", {"gid": gid}, True)


@router.get("/api/task-dependencies")
async def list_task_dependencies(request: Request, list_gid: str = Query(...), current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)): return await _task_call(request, current_user, principal, gateway, "task_dependencies.list", {"list_gid": list_gid})


@router.post("/api/task-dependencies")
async def create_task_dependency(body: TaskDepBody, request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)): return await _task_call(request, current_user, principal, gateway, "task_dependencies.create", body.model_dump(), True)


@router.put("/api/task-dependencies/{gid}")
async def update_task_dependency(gid: str, body: dict, request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)): return await _task_call(request, current_user, principal, gateway, "task_dependencies.update", {"gid": gid, "updates": body}, True)


@router.delete("/api/task-dependencies/{gid}")
async def delete_task_dependency(gid: str, request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)): return await _task_call(request, current_user, principal, gateway, "task_dependencies.delete", {"gid": gid}, True)
