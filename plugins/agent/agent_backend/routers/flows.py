"""Agent-owned flow definitions and runs with strict user ownership."""
from __future__ import annotations

import json
import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.platform_sdk.auth import get_current_user
from ..data.connection import get_agent_conn

router = APIRouter(prefix="/api/flows", tags=["flows"])
FLOWS = "workmanship_app_flows"
RUNS = "workmanship_app_flow_runs"


class FlowBody(BaseModel):
    name: str
    description: str = ""
    flowdef: str = ""
    status: str = "draft"


class FlowPatch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    flowdef: Optional[str] = None
    status: Optional[str] = None


class RunBody(BaseModel):
    mode: str = "auto"


class StepBody(BaseModel):
    pass


class GenScriptBody(BaseModel):
    description: str
    inputs_schema: dict = Field(default_factory=dict)
    outputs_schema: dict = Field(default_factory=dict)


def _owner(user: dict) -> str:
    gid = str(user.get("gid") or "")
    if not gid:
        raise HTTPException(401, "用户身份缺失")
    return gid


def _flow_row(row: dict) -> dict:
    return {
        "gid": row["gid"], "name": row["name"], "description": row.get("description") or "",
        "status": row.get("status") or "draft", "last_run_at": str(row["last_run_at"]) if row.get("last_run_at") else None,
        "created_at": str(row.get("created_at")), "updated_at": str(row.get("updated_at")),
    }


def _run_row(row: dict) -> dict:
    return {
        "gid": row["gid"], "flow_gid": row["flow_gid"], "status": row.get("status") or "pending",
        "mode": row.get("mode") or "auto", "current_node_id": row.get("current_node_id"),
        "error_msg": row.get("error_msg"), "started_at": str(row["started_at"]) if row.get("started_at") else None,
        "completed_at": str(row["completed_at"]) if row.get("completed_at") else None,
    }


@router.get("")
def list_flows(user=Depends(get_current_user)):
    owner = _owner(user)
    with get_agent_conn() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT * FROM {FLOWS} WHERE owner_user_gid=%s AND deleted_at IS NULL ORDER BY updated_at DESC", (owner,))
        rows = cur.fetchall()
    return {"items": [_flow_row(dict(row)) for row in rows]}


@router.post("")
def create_flow(body: FlowBody, user=Depends(get_current_user)):
    owner = _owner(user)
    gid = str(uuid.uuid4())
    with get_agent_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"""INSERT INTO {FLOWS}
                (gid, owner_user_gid, name, description, flowdef, status, created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,NOW(),NOW())""",
            (gid, owner, body.name, body.description, body.flowdef, body.status),
        )
    return {"gid": gid, "name": body.name}


@router.get("/capability-manifest")
def capability_manifest(user=Depends(get_current_user)):
    _owner(user)
    return {
        "manifest": [],
        "message": "Flow 节点必须从 Capability Catalog 选择；旧进程内 node_registry 已停用",
    }


@router.get("/runs")
def list_run_history(flow_gid: str, limit: int = 10, user=Depends(get_current_user)):
    owner = _owner(user)
    with get_agent_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"""SELECT r.* FROM {RUNS} r JOIN {FLOWS} f ON f.gid=r.flow_gid
                WHERE r.flow_gid=%s AND f.owner_user_gid=%s ORDER BY r.started_at DESC LIMIT %s""",
            (flow_gid, owner, min(max(limit, 1), 100)),
        )
        rows = cur.fetchall()
    return {"items": [_run_row(dict(row)) for row in rows]}


@router.get("/runs/{run_gid}")
def get_run_state(run_gid: str, user=Depends(get_current_user)):
    owner = _owner(user)
    with get_agent_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT r.* FROM {RUNS} r JOIN {FLOWS} f ON f.gid=r.flow_gid WHERE r.gid=%s AND f.owner_user_gid=%s",
            (run_gid, owner),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "run_gid 不存在")
    return _run_row(dict(row))


@router.post("/runs/{run_gid}/step")
def step_run(run_gid: str, _body: StepBody = StepBody(), user=Depends(get_current_user)):
    return get_run_state(run_gid, user)


@router.get("/{gid}")
def get_flow(gid: str, user=Depends(get_current_user)):
    owner = _owner(user)
    with get_agent_conn() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT * FROM {FLOWS} WHERE gid=%s AND owner_user_gid=%s AND deleted_at IS NULL", (gid, owner))
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "flow 不存在")
    result = _flow_row(dict(row)); result["flowdef"] = row.get("flowdef") or ""
    return result


@router.put("/{gid}")
def update_flow(gid: str, body: FlowPatch, user=Depends(get_current_user)):
    owner = _owner(user)
    updates = {key: value for key, value in body.dict().items() if value is not None}
    if not updates:
        return {"success": True}
    clause = ", ".join(f"{key}=%s" for key in updates)
    with get_agent_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"UPDATE {FLOWS} SET {clause}, updated_at=NOW() WHERE gid=%s AND owner_user_gid=%s AND deleted_at IS NULL",
            [*updates.values(), gid, owner],
        )
        if cur.rowcount != 1:
            raise HTTPException(404, "flow 不存在")
    return {"success": True}


@router.delete("/{gid}")
def delete_flow(gid: str, user=Depends(get_current_user)):
    owner = _owner(user)
    with get_agent_conn() as conn, conn.cursor() as cur:
        cur.execute(f"UPDATE {FLOWS} SET deleted_at=NOW() WHERE gid=%s AND owner_user_gid=%s AND deleted_at IS NULL", (gid, owner))
        if cur.rowcount != 1:
            raise HTTPException(404, "flow 不存在")
    return {"success": True}


@router.post("/{gid}/run")
def run_flow(gid: str, body: RunBody, user=Depends(get_current_user)):
    owner = _owner(user)
    run_gid = str(uuid.uuid4())
    with get_agent_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"""INSERT INTO {RUNS} (gid, flow_gid, status, mode, started_at)
                SELECT %s, gid, 'running', %s, NOW() FROM {FLOWS}
                WHERE gid=%s AND owner_user_gid=%s AND deleted_at IS NULL""",
            (run_gid, body.mode, gid, owner),
        )
        if cur.rowcount != 1:
            raise HTTPException(404, "flow 不存在")
    return {"run_gid": run_gid}


@router.post("/gen-script")
async def gen_script(body: GenScriptBody, user=Depends(get_current_user)):
    _owner(user)
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {"success": False, "error": "ANTHROPIC_API_KEY 未配置；模型密钥只能来自部署 Secret"}
    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model=os.getenv("AI_SCRIPT_MODEL", "claude-sonnet-4-6"),
            max_tokens=1024,
            system="生成只操作 inputs/outputs 字典的受限 Python 数据处理代码；禁止系统、网络和文件 API。只输出代码。",
            messages=[{"role": "user", "content": f"需求：{body.description}\ninputs：{json.dumps(body.inputs_schema, ensure_ascii=False)}\noutputs：{json.dumps(body.outputs_schema, ensure_ascii=False)}"}],
        )
        code = response.content[0].text if response.content else ""
        if code.startswith("```"):
            lines = code.splitlines(); code = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
        return {"success": True, "code": code}
    except Exception as exc:
        return {"success": False, "error": str(exc)[:300]}
