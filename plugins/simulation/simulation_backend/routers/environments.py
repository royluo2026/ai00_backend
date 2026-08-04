from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.platform_sdk.auth import get_current_user
from ..public import create_environment, get_environment, list_environments

router = APIRouter(prefix="/api/simulation/environments", tags=["simulation"])


class CreateEnvironmentBody(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    execution_plan: dict[str, Any]
    execution_plan_snapshot_uri: str = Field(min_length=1, max_length=2048)
    team_gid: str | None = None


@router.post("")
def create(body: CreateEnvironmentBody, user: dict = Depends(get_current_user)):
    try:
        data = create_environment(
            name=body.name,
            plan=body.execution_plan,
            snapshot_uri=body.execution_plan_snapshot_uri,
            creator_gid=user["gid"],
            team_gid=body.team_gid,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"success": True, "data": data}


@router.get("")
def list_all(team_gid: str | None = None, user: dict = Depends(get_current_user)):
    return {"success": True, "data": list_environments(user["gid"], team_gid)}


@router.get("/{environment_gid}")
def get_one(environment_gid: str, team_gid: str | None = None, user: dict = Depends(get_current_user)):
    try:
        data = get_environment(environment_gid, user["gid"], team_gid)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"success": True, "data": data}
