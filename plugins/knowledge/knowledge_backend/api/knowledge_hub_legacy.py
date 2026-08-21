"""Gateway adapters for the historical Knowledge Hub HTTP surface."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from backend.capability_v2.gateway import get_default_gateway
from backend.platform_sdk.auth import get_authenticated_principal, get_current_user
from backend.platform_sdk.factory import build_web_compatibility_envelope, invoke_compatibility
from backend.platform_sdk.ids import next_gid

router = APIRouter(prefix="/api/knowledge_hub", tags=["knowledge_hub"])


async def _invoke(request, current_user, principal, gateway, capability_id, operation, arguments=None, *, write=False):
    capability_id = f"{capability_id}.atomic.{operation.replace('.', '_')}"
    atomic_payload = arguments or {}
    request_id = request.headers.get("X-Request-ID") or f"knowledge_hub_legacy_{next_gid()}"
    result = await invoke_compatibility(gateway, build_web_compatibility_envelope(
        gateway, capability_id=capability_id, payload=atomic_payload,
        current_user=current_user, principal=principal, request_id=request_id,
        trace_id=request.headers.get("X-Trace-ID") or request_id,
        idempotency_key=(request.headers.get("X-Idempotency-Key") or request_id) if write else None,
        approval_reference=request.headers.get("X-Capability-Approval") if write else None,
    ))
    if not result.ok:
        code = result.error.code if result.error else "provider_error"
        raise HTTPException(status_code={"resource_not_found": 404, "permission_denied": 403, "invalid_input": 400}.get(code, 422), detail=result.error.model_dump(mode="json") if result.error else None)
    return result.data["data"]


class FolderCreate(BaseModel):
    parent_gid: Optional[str] = None
    scope_type: str = "personal"
    team_gid: Optional[str] = None
    name: str = "新建文件夹"
    sort_order: int = 0


class FolderPatch(BaseModel):
    name: Optional[str] = None
    sort_order: Optional[int] = None
    parent_gid: Optional[str] = None


class ItemCreate(BaseModel):
    folder_gid: Optional[str] = None
    scope_type: str = "personal"
    team_gid: Optional[str] = None
    item_type: str = "richtext"
    title: str = "未命名文档"
    status: str = "draft"
    content_body: Optional[Any] = None
    content_md: str = ""
    file_path: str = ""
    url: str = ""
    site_ref: Optional[Any] = None
    tags: list = []


class ItemPatch(BaseModel):
    folder_gid: Optional[str] = None
    title: Optional[str] = None
    status: Optional[str] = None
    scope_type: Optional[str] = None
    team_gid: Optional[str] = None
    content_body: Optional[Any] = None
    content_md: Optional[str] = None
    file_path: Optional[str] = None
    url: Optional[str] = None
    site_ref: Optional[Any] = None
    tags: Optional[list] = None
    is_pinned: Optional[bool] = None
    is_hidden: Optional[bool] = None


@router.get("/folders")
async def list_folders(request: Request, scope_type: Optional[str] = Query(None), team_gid: Optional[str] = Query(None), current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    data = await _invoke(request, current_user, principal, gateway, "knowledge.hub.read", "folders.list", {"scope_type": scope_type, "team_gid": team_gid})
    return data.get("items", [])


@router.post("/folders")
async def create_folder(body: FolderCreate, request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke(request, current_user, principal, gateway, "knowledge.hub.change.apply", "folders.create", body.model_dump(), write=True)


@router.patch("/folders/{gid}")
async def patch_folder(gid: str, body: FolderPatch, request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    data = await _invoke(request, current_user, principal, gateway, "knowledge.hub.change.apply", "folders.update", {"gid": gid, "updates": body.model_dump(exclude_unset=True)}, write=True)
    return {"success": bool(data.get("changed", True))}


@router.delete("/folders/{gid}")
async def delete_folder(gid: str, request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    data = await _invoke(request, current_user, principal, gateway, "knowledge.hub.change.apply", "folders.delete", {"gid": gid}, write=True)
    return {"success": True, **data}


@router.get("/items")
async def list_items(request: Request, folder_gid: Optional[str] = Query(None), scope_type: Optional[str] = Query(None), team_gid: Optional[str] = Query(None), show_hidden: Optional[bool] = Query(False), q: Optional[str] = Query(None), current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    data = await _invoke(request, current_user, principal, gateway, "knowledge.hub.read", "items.list", {"folder_gid": folder_gid, "scope_type": scope_type, "team_gid": team_gid, "show_hidden": show_hidden, "q": q})
    return data.get("items", [])


@router.get("/items/{gid}")
async def get_item(gid: str, request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke(request, current_user, principal, gateway, "knowledge.hub.read", "items.get", {"gid": gid})


@router.post("/items")
async def create_item(body: ItemCreate, request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    return await _invoke(request, current_user, principal, gateway, "knowledge.hub.change.apply", "items.create", body.model_dump(), write=True)


@router.patch("/items/{gid}")
async def patch_item(gid: str, body: ItemPatch, request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    data = await _invoke(request, current_user, principal, gateway, "knowledge.hub.change.apply", "items.update", {"gid": gid, "updates": body.model_dump(exclude_unset=True)}, write=True)
    return {"success": bool(data.get("changed", True))}


@router.get("/items/{gid}/history")
async def get_item_history(gid: str, request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    rows = await _invoke(request, current_user, principal, gateway, "knowledge.hub.read", "items.history.get", {"gid": gid})
    return {"success": True, "data": [{"gid": row["gid"], "id": row["id"], "author_name": row["author_name"], "content": row["content"], "created_at": str(row["created_at"])} for row in rows.get("items", [])]}


@router.delete("/items/{gid}")
async def delete_item(gid: str, request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    data = await _invoke(request, current_user, principal, gateway, "knowledge.hub.change.apply", "items.delete", {"gid": gid}, write=True)
    return {"success": True, **data}


@router.post("/items/{gid}/favorite")
async def toggle_favorite(gid: str, request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    data = await _invoke(request, current_user, principal, gateway, "knowledge.personalization.change.apply", "favorites.toggle", {"gid": gid}, write=True)
    return {"is_favorite": bool(data.get("favorite"))}


@router.get("/favorites")
async def list_favorites(request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    data = await _invoke(request, current_user, principal, gateway, "knowledge.personalization.read", "favorites.list")
    return data.get("items", [])


@router.post("/items/{gid}/recent")
async def record_recent(gid: str, request: Request, current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    await _invoke(request, current_user, principal, gateway, "knowledge.personalization.change.apply", "recent.record", {"gid": gid}, write=True)
    return {"success": True}


@router.get("/recent")
async def list_recent(request: Request, limit: int = Query(20, le=100), current_user=Depends(get_current_user), principal=Depends(get_authenticated_principal), gateway=Depends(get_default_gateway)):
    data = await _invoke(request, current_user, principal, gateway, "knowledge.personalization.read", "recent.list", {"limit": limit})
    return data.get("items", [])
