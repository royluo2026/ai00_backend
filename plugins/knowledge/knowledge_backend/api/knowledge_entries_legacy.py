"""
Knowledge-owned compatibility routes for historical entry APIs.
─────────────────────────────
知识条目 CRUD API（云端 PG）

端点：
  GET    /api/knowledge_entries          → 列表
  POST   /api/knowledge_entries          → 创建
  GET    /api/knowledge_entries/{gid}    → 获取单条
  PATCH  /api/knowledge_entries/{gid}    → 更新
  DELETE /api/knowledge_entries/{gid}    → 删除
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from backend.platform_sdk.auth import get_current_user
from backend.platform_sdk.ids import next_gid
from backend.capability_v2.gateway import get_default_gateway
from backend.platform_sdk.auth import get_authenticated_principal
from backend.platform_sdk.factory import build_web_compatibility_envelope, invoke_compatibility

router = APIRouter(tags=["knowledge"])


async def _invoke_knowledge(request, current_user, principal, gateway, capability_id, payload, *, write=False):
    operation = payload.get("operation") if isinstance(payload, dict) else None
    if isinstance(operation, str):
        capability_id = f"{capability_id}.atomic.{operation.replace('.', '_')}"
        payload = payload.get("arguments", {}) if isinstance(payload.get("arguments"), dict) else {}
    request_id = request.headers.get("X-Request-ID") or f"knowledge_legacy_{next_gid()}"
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(
        gateway,
        capability_id=capability_id,
        payload=payload,
        current_user=current_user,
        principal=principal,
        request_id=request_id,
        trace_id=request.headers.get("X-Trace-ID") or request_id,
        idempotency_key=(request.headers.get("X-Idempotency-Key") or request_id) if write else None,
        approval_reference=request.headers.get("X-Capability-Approval") if write else None,
    ))
    if not result.ok:
        code = result.error.code if result.error else "provider_error"
        raise HTTPException(status_code={"resource_not_found": 404, "permission_denied": 403, "invalid_input": 400}.get(code, 422), detail=result.error.model_dump(mode="json") if result.error else None)
    return result.data["data"]


class KnowledgeBody(BaseModel):
    title: str
    entry_type: str = "guide"
    status: str = "draft"
    share_scope: str = "team"
    list_gid: Optional[str] = None
    source_gid: Optional[str] = None
    source_label: str = ""
    maintainer_gid: str = ""
    contributors: list = []
    attachments: list = []
    tags: list = []
    content_ref: dict = {}
    related_part_nos: list = []
    related_operation_gids: list = []


@router.get("/api/knowledge_entries")
async def list_knowledge_entries(
    entry_type: Optional[str] = Query(None),
    list_gid: Optional[str] = Query(None),
    context_class_gid: Optional[str] = Query(None),
    limit: int = Query(200, le=500),
    current_user: dict = Depends(get_current_user),
    request: Request = None,
    principal=Depends(get_authenticated_principal),
    gateway=Depends(get_default_gateway),
):
    data = await _invoke_knowledge(
        request,
        current_user,
        principal,
        gateway,
        "knowledge.search",
        {
            "query": "",
            "entry_type": entry_type,
            "list_gid": list_gid,
            "context_class_gid": context_class_gid,
            "include_content": True,
            "limit": limit,
        },
    )
    return {"success": True, "data": data.get("items", [])}


@router.post("/api/knowledge_entries", status_code=201)
async def create_knowledge_entry(
    body: KnowledgeBody,
    request: Request,
    current_user: dict = Depends(get_current_user),
    principal=Depends(get_authenticated_principal),
    gateway=Depends(get_default_gateway),
):
    data = await _invoke_knowledge(
        request,
        current_user,
        principal,
        gateway,
        "knowledge.entry.change.apply",
        {"operation": "entries.create", "arguments": body.model_dump(exclude_none=True)},
        write=True,
    )
    return {"success": True, "data": {"gid": data.get("gid", "")}}


@router.get("/api/knowledge_entries/{gid}")
async def get_knowledge_entry(
    gid: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
    principal=Depends(get_authenticated_principal),
    gateway=Depends(get_default_gateway),
):
    data = await _invoke_knowledge(
        request, current_user, principal, gateway, "knowledge.get", {"gid": gid}
    )
    return {"success": True, "data": data}


@router.patch("/api/knowledge_entries/{gid}")
async def update_knowledge_entry(
    gid: str,
    body: dict,
    request: Request,
    current_user: dict = Depends(get_current_user),
    principal=Depends(get_authenticated_principal),
    gateway=Depends(get_default_gateway),
):
    await _invoke_knowledge(
        request,
        current_user,
        principal,
        gateway,
        "knowledge.entry.change.apply",
        {"operation": "entries.update", "arguments": {"gid": gid, "updates": body}},
        write=True,
    )
    return {"success": True}


@router.delete("/api/knowledge_entries/{gid}")
async def delete_knowledge_entry(
    gid: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
    principal=Depends(get_authenticated_principal),
    gateway=Depends(get_default_gateway),
):
    await _invoke_knowledge(
        request,
        current_user,
        principal,
        gateway,
        "knowledge.entry.change.apply",
        {"operation": "entries.delete", "arguments": {"gid": gid}},
        write=True,
    )
    return {"success": True}

class VectorSearchBody(BaseModel):
    query_vector: list
    top_k: int = 10
    min_similarity: float = 0.0   # cosine distance < (1 - min_similarity)


@router.post("/api/knowledge_entries/vector-search", status_code=410)
def vector_search_knowledge(
    body: VectorSearchBody,
    current_user: dict = Depends(get_current_user),
):
    """Retired until an OceanBase-compatible vector index Capability is available."""
    raise HTTPException(
        status_code=410,
        detail=(
            "遗留向量检索入口已退役；"
            "待 OceanBase-compatible vector Capability 上线后重新开放"
        ),
    )
