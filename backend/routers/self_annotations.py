"""Compatibility adapters for the Base-owned self-annotation service."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, StrictInt, StrictStr

from backend.base.self_annotations import SelfAnnotationError, SelfAnnotationService
from backend.routers.deps import get_current_user


router = APIRouter(prefix="/api/self_ann", tags=["self_annotations"])


class SelfAnnotationAttachmentBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    attachment_gid: StrictStr
    media_type: StrictStr
    display_name: StrictStr
    size: StrictInt
    checksum: StrictStr


class SelfAnnotationChangeBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_revision: StrictInt
    status: StrictStr
    schedule: StrictStr | None = None
    note: StrictStr = ""
    attachments: list[SelfAnnotationAttachmentBody] = []
    idempotency_key: StrictStr


def _service() -> SelfAnnotationService:
    return SelfAnnotationService()


def _http(exc: SelfAnnotationError) -> HTTPException:
    status = 409 if exc.code == "revision_conflict" else 403 if exc.code == "attachment_not_visible" else 422
    return HTTPException(status_code=status, detail={"code": exc.code, "message": str(exc)})


@router.get("/batch")
def get_batch(gids: str = Query(""), user: dict = Depends(get_current_user)):
    values = [value.strip() for value in gids.split(",") if value.strip()][:200]
    records = [_service().get(actor=user, item_gid=value)["annotation"] for value in values]
    return {item["item_gid"]: {"status": item["status"], "schedule": item["schedule"] or "", "has_note": bool(item["note"]), "attach_count": len(item["attachments"])} for item in records if not item["deleted"]}


@router.get("/list")
def get_list(limit: int = Query(200, ge=1, le=200), status: str | None = Query(None), module: str | None = Query(None, max_length=128), user: dict = Depends(get_current_user)):
    try:
        return _service().search(actor=user, query={"limit": limit, "status": status, "module": module})
    except SelfAnnotationError as exc:
        raise _http(exc) from exc


@router.get("/{item_gid}")
def get_annotation(item_gid: str, user: dict = Depends(get_current_user)):
    try:
        return _service().get(actor=user, item_gid=item_gid)
    except SelfAnnotationError as exc:
        raise _http(exc) from exc


@router.put("/{item_gid}")
def upsert_annotation(item_gid: str, body: SelfAnnotationChangeBody, user: dict = Depends(get_current_user)):
    try:
        return _service().apply_change(actor=user, command={"item_gid": item_gid, **body.model_dump()})
    except SelfAnnotationError as exc:
        raise _http(exc) from exc


@router.delete("/{item_gid}")
def delete_annotation(item_gid: str, expected_revision: int = Query(...), idempotency_key: str = Query(...), user: dict = Depends(get_current_user)):
    try:
        return _service().apply_change(actor=user, command={"item_gid": item_gid, "expected_revision": expected_revision,
            "status": "deleted", "schedule": None, "note": "", "attachments": [], "idempotency_key": idempotency_key})
    except SelfAnnotationError as exc:
        raise _http(exc) from exc
