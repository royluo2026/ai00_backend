"""Agent-owned Flow HTTP compatibility routes.

The router only validates transport input and delegates stable outcomes to the
Agent Capability Gateway. Persistence lives below the provider boundary.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.platform_sdk.auth import get_current_user
from ..api.compatibility import invoke_agent_capability

router = APIRouter(prefix="/api/flows", tags=["flows"])


class FlowBody(BaseModel):
    name: str
    description: str = ""
    flowdef: str = ""
    status: str = "draft"


class FlowPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    flowdef: str | None = None
    status: str | None = None


class RunBody(BaseModel):
    mode: str = "auto"


class StepBody(BaseModel):
    pass


class GenScriptBody(BaseModel):
    description: str
    inputs_schema: dict = Field(default_factory=dict)
    outputs_schema: dict = Field(default_factory=dict)


def _owner(user: dict) -> None:
    if not str(user.get("gid") or ""):
        raise HTTPException(401, "用户身份缺失")


@router.get("")
async def list_flows(user=Depends(get_current_user)):
    return await invoke_agent_capability("agent.flow.read", {"operation": "list"}, user)


@router.post("")
async def create_flow(body: FlowBody, user=Depends(get_current_user)):
    return await invoke_agent_capability(
        "agent.flow.change.apply", {"operation": "create", **body.model_dump()}, user
    )


@router.get("/capability-manifest")
async def capability_manifest(user=Depends(get_current_user)):
    return await invoke_agent_capability("agent.flow.read", {"operation": "manifest"}, user)


@router.get("/runs")
async def list_run_history(flow_gid: str, limit: int = 10, user=Depends(get_current_user)):
    return await invoke_agent_capability(
        "agent.flow.read", {"operation": "list_runs", "flow_gid": flow_gid, "limit": limit}, user
    )


@router.get("/runs/{run_gid}")
async def get_run_state(run_gid: str, user=Depends(get_current_user)):
    return await invoke_agent_capability(
        "agent.flow.read", {"operation": "get_run", "run_gid": run_gid}, user
    )


@router.post("/runs/{run_gid}/step")
async def step_run(run_gid: str, _body: StepBody = StepBody(), user=Depends(get_current_user)):
    return await get_run_state(run_gid, user)


@router.get("/{gid}")
async def get_flow(gid: str, user=Depends(get_current_user)):
    return await invoke_agent_capability(
        "agent.flow.read", {"operation": "get", "flow_gid": gid}, user
    )


@router.put("/{gid}")
async def update_flow(gid: str, body: FlowPatch, user=Depends(get_current_user)):
    return await invoke_agent_capability(
        "agent.flow.change.apply",
        {"operation": "update", "flow_gid": gid, **body.model_dump(exclude_none=True)},
        user,
    )


@router.delete("/{gid}")
async def delete_flow(gid: str, user=Depends(get_current_user)):
    return await invoke_agent_capability(
        "agent.flow.change.apply", {"operation": "delete", "flow_gid": gid}, user
    )


@router.post("/{gid}/run")
async def run_flow(gid: str, body: RunBody, user=Depends(get_current_user)):
    return await invoke_agent_capability(
        "agent.flow.change.apply", {"operation": "run", "flow_gid": gid, "mode": body.mode}, user
    )


@router.post("/gen-script")
async def gen_script(body: GenScriptBody, user=Depends(get_current_user)):
    _owner(user)
    return await invoke_agent_capability(
        "agent.script.generate",
        body.model_dump(),
        user,
    )
