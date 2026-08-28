"""Compatibility REST adapter for the Base saved-view aggregate service."""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from backend.base.saved_views import SavedViewError, SavedViewService
from backend.routers.deps import require_role


router = APIRouter(prefix="/api/views", tags=["views"])
_READ = require_role("super_admin", "team_admin", "project_admin", "rule_admin", "knowledge_admin", "member")


class _ClosedBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateViewBody(_ClosedBody):
    name: str
    module: str = ""
    list_gid: str | None = None
    config: dict
    share_scope: Literal["private", "team", "shared"]
    idempotency_key: str


class UpdateViewBody(_ClosedBody):
    expected_revision: int
    name: str
    module: str | None = None
    list_gid: str | None = None
    config: dict
    share_scope: Literal["private", "team", "shared"] | None = None
    idempotency_key: str


class CopyViewBody(_ClosedBody):
    name: str
    idempotency_key: str


def _service_error(exc: SavedViewError) -> HTTPException:
    status = {"invalid_input": 422, "resource_not_found": 404, "permission_denied": 403, "revision_conflict": 409}.get(exc.code, 400)
    return HTTPException(status, {"code": exc.code, "message": str(exc)})


def _body(body: BaseModel) -> dict:
    return body.model_dump(exclude_none=True)


@router.get("")
def list_views(module: str = "", list_gid: str | None = None,
               limit: Annotated[int, Query(ge=1, le=200)] = 200, user=Depends(_READ)):
    try:
        return {"success": True, "data": SavedViewService().search(actor=user, query={"module": module, "list_gid": list_gid, "limit": limit})["views"]}
    except SavedViewError as exc:
        raise _service_error(exc) from exc


@router.post("")
def create_view(body: CreateViewBody, user=Depends(_READ)):
    try:
        return {"success": True, "data": SavedViewService().create(actor=user, command=_body(body))["view"]}
    except SavedViewError as exc:
        raise _service_error(exc) from exc


@router.patch("/{gid}")
def update_view(gid: str, body: UpdateViewBody, user=Depends(_READ)):
    try:
        return {"success": True, "data": SavedViewService().update(actor=user, view_gid=gid, command=_body(body))["view"]}
    except SavedViewError as exc:
        raise _service_error(exc) from exc


@router.delete("/{gid}")
def delete_view(gid: str, expected_revision: int, idempotency_key: str, user=Depends(_READ)):
    try:
        return {"success": True, "data": SavedViewService().delete(actor=user, view_gid=gid, command={"expected_revision": expected_revision, "idempotency_key": idempotency_key})["view"]}
    except SavedViewError as exc:
        raise _service_error(exc) from exc


@router.post("/{gid}/copy")
def copy_view(gid: str, body: CopyViewBody, user=Depends(_READ)):
    try:
        return {"success": True, "data": SavedViewService().copy(actor=user, view_gid=gid, command=_body(body))["view"]}
    except SavedViewError as exc:
        raise _service_error(exc) from exc
