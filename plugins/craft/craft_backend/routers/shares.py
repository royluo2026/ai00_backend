"""Temporary Gateway adapters for direct Project shares."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from backend.capability_v2.gateway import get_default_gateway
from backend.platform_sdk.auth import get_authenticated_principal, get_current_user
from backend.platform_sdk.identity import get_user_summaries
from plugins.project_management.project_management_backend.api.compatibility import build_web_compatibility_envelope, invoke_compatibility
from uuid import uuid4
router=APIRouter(tags=["shares"])
class ListShareBody(BaseModel): shared_to:str; permission:str="read"
class ItemShareBody(BaseModel): item_type:str; item_gid:str; shared_to:str; permission:str="read"
async def _call(request,user,principal,gateway,operation,args):
    write=operation!="shares.list.list"; rid=request.headers.get("X-Request-ID") or f"project_{uuid4().hex}"
    result=await invoke_compatibility(gateway,build_web_compatibility_envelope(gateway,capability_id="project.sharing.change.apply" if write else "project.sharing.read",payload={"operation":operation,"arguments":args},current_user=user,principal=principal,request_id=rid,trace_id=request.headers.get("X-Trace-ID") or rid,idempotency_key=request.headers.get("X-Idempotency-Key") if write else None,approval_reference=request.headers.get("X-Capability-Approval") if write else None))
    if not result.ok:
        code=result.error.code if result.error else "provider_failed"; raise HTTPException(404 if code=="not_found" else 403 if code=="forbidden" else 422,result.error.model_dump(mode="json") if result.error else None)
    return result.data["data"]
@router.get("/api/shares/lists/{list_gid}")
async def get_list_shares(list_gid:str,request:Request,user=Depends(get_current_user),principal=Depends(get_authenticated_principal),gateway=Depends(get_default_gateway)):
    data=await _call(request,user,principal,gateway,"shares.list.list",{"list_gid":list_gid}); summaries=get_user_summaries(row.get("shared_to") for row in data["shares"])
    for row in data["shares"]:
        summary=summaries.get(str(row.get("shared_to")),{}); row["shared_to_name"],row["shared_to_avatar"]=summary.get("name"),summary.get("avatar_url")
    return data
@router.post("/api/shares/lists/{list_gid}",status_code=status.HTTP_201_CREATED)
async def create_list_share(list_gid:str,body:ListShareBody,request:Request,user=Depends(get_current_user),principal=Depends(get_authenticated_principal),gateway=Depends(get_default_gateway)): return await _call(request,user,principal,gateway,"shares.list.create",{"list_gid":list_gid,**body.model_dump()})
@router.delete("/api/shares/lists/{list_gid}/{gid}")
async def delete_list_share(list_gid:str,gid:str,request:Request,user=Depends(get_current_user),principal=Depends(get_authenticated_principal),gateway=Depends(get_default_gateway)): return await _call(request,user,principal,gateway,"shares.list.delete",{"list_gid":list_gid,"gid":gid})
@router.post("/api/shares/items",status_code=status.HTTP_201_CREATED)
async def create_item_share(body:ItemShareBody,request:Request,user=Depends(get_current_user),principal=Depends(get_authenticated_principal),gateway=Depends(get_default_gateway)): return await _call(request,user,principal,gateway,"shares.item.create",body.model_dump())
@router.delete("/api/shares/items/{gid}")
async def delete_item_share(gid:str,request:Request,user=Depends(get_current_user),principal=Depends(get_authenticated_principal),gateway=Depends(get_default_gateway)): return await _call(request,user,principal,gateway,"shares.item.delete",{"gid":gid})
