"""
backend/routers/flows.py
──────────────────────────────
流程引擎云端 REST API

GET    /api/flows                   → 列出流程
POST   /api/flows                   → 创建流程
GET    /api/flows/{gid}             → 获取流程详情（含 flowdef）
PUT    /api/flows/{gid}             → 更新流程
DELETE /api/flows/{gid}             → 软删除

POST   /api/flows/{gid}/run         → 执行流程（返回 run_gid）
GET    /api/flows/runs/{run_gid}    → 获取运行状态
POST   /api/flows/runs/{run_gid}/step → step 模式推进一步
GET    /api/flows/runs              → 运行历史（?flow_gid=）

POST   /api/flows/gen-script        → AI 生成脚本
GET    /api/flows/capability-manifest → 系统能力清单
"""
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.db.connection import get_conn
from backend.routers.deps import get_current_user
from backend.utils.gid import next_gid

router = APIRouter(prefix="/api/flows", tags=["flows"])


# ── Pydantic 模型 ─────────────────────────────────────────────────────────────

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
    inputs_schema: dict = {}
    outputs_schema: dict = {}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _flow_row(r: dict) -> dict:
    return {
        'gid':         r['gid'],
        'name':        r['name'],
        'description': r.get('description') or '',
        'status':      r.get('status') or 'draft',
        'last_run_at': str(r['last_run_at']) if r.get('last_run_at') else None,
        'created_at':  str(r.get('created_at')),
        'updated_at':  str(r.get('updated_at')),
    }


def _run_row(r: dict) -> dict:
    return {
        'gid':             r['gid'],
        'flow_gid':        r['flow_gid'],
        'status':          r.get('status') or 'pending',
        'mode':            r.get('mode') or 'auto',
        'current_node_id': r.get('current_node_id'),
        'error_msg':       r.get('error_msg'),
        'started_at':      str(r['started_at']) if r.get('started_at') else None,
        'completed_at':    str(r['completed_at']) if r.get('completed_at') else None,
    }


# ── Flow CRUD ─────────────────────────────────────────────────────────────────

@router.get("")
def list_flows(user=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM app.flows WHERE deleted_at IS NULL ORDER BY updated_at DESC"
            )
            rows = cur.fetchall()
    return {"items": [_flow_row(dict(r)) for r in rows]}


@router.post("")
def create_flow(body: FlowBody, user=Depends(get_current_user)):
    gid = str(next_gid())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO app.flows (gid, name, description, flowdef, status, created_at, updated_at)
                   VALUES (%s,%s,%s,%s,%s,NOW(),NOW())""",
                (gid, body.name, body.description, body.flowdef, body.status),
            )
        conn.commit()
    return {"gid": gid, "name": body.name}


@router.get("/capability-manifest")
def capability_manifest(user=Depends(get_current_user)):
    """返回所有节点的能力清单（AI 可读）"""
    _ONTOLOGY_TOOLS = [
        {
            "name": "get_class_schema",
            "category": "ontology",
            "endpoint": "GET /api/ontology/schema/{node_type}",
            "description": "获取指定 node_type 的本体类定义、属性列表和关联 CEL 规则",
            "params": {"node_type": "BOP 节点类型，如 operation / physical_equipment"},
        },
        {
            "name": "audit_bop_version",
            "category": "ontology",
            "endpoint": "POST /api/rule-engine/audit/bop-version/{version_gid}",
            "description": "批量检验 BOP 版本所有条目是否满足本体规则，返回违反列表",
            "params": {"version_gid": "BOP 版本 gid", "dry_run": "true=只返回，false=同时创建 Issue"},
        },
        {
            "name": "check_rule",
            "category": "ontology",
            "endpoint": "POST /api/rule-engine/check",
            "description": "对单条 CEL 规则执行检验，返回 pass/warn/fail/skip",
            "params": {"rule_gid": "规则 gid", "context": "字段名→值的 JSON dict"},
        },
    ]
    try:
        import app.application.flow_engine.nodes  # noqa: F401 — trigger registration
        from app.application.flow_engine.node_registry import flow_registry
        return {"manifest": flow_registry.get_manifest(), "ontology_tools": _ONTOLOGY_TOOLS}
    except Exception as e:
        return {"manifest": [], "ontology_tools": _ONTOLOGY_TOOLS, "error": str(e)}


@router.get("/runs")
def list_run_history(flow_gid: str, limit: int = 10, user=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT * FROM app.flow_runs WHERE flow_gid=%s
                   ORDER BY started_at DESC LIMIT %s""",
                (flow_gid, limit),
            )
            rows = cur.fetchall()
    return {"items": [_run_row(dict(r)) for r in rows]}


@router.get("/runs/{run_gid}")
def get_run_state(run_gid: str, user=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM app.flow_runs WHERE gid=%s", (run_gid,))
            row = cur.fetchone()
    if not row:
        raise HTTPException(404, "run_gid 不存在")
    return _run_row(dict(row))


@router.post("/runs/{run_gid}/step")
def step_run(run_gid: str, user=Depends(get_current_user)):
    """step 模式推进一步（更新 DB，返回新状态）"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM app.flow_runs WHERE gid=%s", (run_gid,))
            row = cur.fetchone()
        if not row:
            raise HTTPException(404, "run_gid 不存在")
        # 在云端 PG 场景下，执行引擎实际在本地，此 endpoint 仅记录"step 请求"
        # 实际 step 逻辑由本地 bridge 处理，这里只做状态透传
    return {"message": "step request received", "run_gid": run_gid}


@router.get("/{gid}")
def get_flow(gid: str, user=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM app.flows WHERE gid=%s AND deleted_at IS NULL", (gid,))
            row = cur.fetchone()
    if not row:
        raise HTTPException(404, "flow 不存在")
    d = _flow_row(dict(row))
    d['flowdef'] = row['flowdef'] or ''
    return d


@router.put("/{gid}")
def update_flow(gid: str, body: FlowPatch, user=Depends(get_current_user)):
    updates = {k: v for k, v in body.dict().items() if v is not None}
    if not updates:
        return {"success": True}
    set_clause = ", ".join(f"{k}=%s" for k in updates)
    values = list(updates.values()) + [gid]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE app.flows SET {set_clause}, updated_at=NOW() WHERE gid=%s",
                values,
            )
        conn.commit()
    return {"success": True}


@router.delete("/{gid}")
def delete_flow(gid: str, user=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE app.flows SET deleted_at=NOW() WHERE gid=%s", (gid,))
        conn.commit()
    return {"success": True}


@router.post("/{gid}/run")
def run_flow(gid: str, body: RunBody, user=Depends(get_current_user)):
    """在云端记录一次 run，实际执行由本地引擎处理"""
    run_gid = str(next_gid())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO app.flow_runs (gid, flow_gid, status, mode, started_at)
                   VALUES (%s,%s,'running',%s,NOW())""",
                (run_gid, gid, body.mode),
            )
        conn.commit()
    return {"run_gid": run_gid}


# ── AI Script Generation ──────────────────────────────────────────────────────

@router.post("/gen-script")
async def gen_script(body: GenScriptBody, user=Depends(get_current_user)):
    """调用 AI 根据描述生成 Python 脚本"""
    try:
        import anthropic
        from backend.db.connection import get_conn as _gc
        with _gc() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM app.system_config WHERE key='ai.anthropic_api_key'")
                row = cur.fetchone()
                api_key = row["value"] if row else ""

        if not api_key:
            return {"success": False, "error": "Anthropic API key 未配置"}

        client = anthropic.AsyncAnthropic(api_key=api_key)
        system = (
            "你是一个 Python 脚本生成器，专门为汽车工艺系统生成数据处理脚本。"
            "生成的代码只能使用：print, len, range, int, str, float, list, dict, "
            "sorted, enumerate, zip, map, filter, sum, min, max, abs, round, "
            "isinstance, type, bool, repr, set, tuple, any, all, json。"
            "操作全部通过 inputs 字典读取，结果写入 outputs 字典。"
            "禁止 import os, sys, socket, subprocess, shutil, pathlib。"
            "只输出 Python 代码，不要额外解释。"
        )
        import json
        user_msg = (
            f"需求：{body.description}\n"
            f"inputs 格式：{json.dumps(body.inputs_schema, ensure_ascii=False)}\n"
            f"outputs 格式：{json.dumps(body.outputs_schema, ensure_ascii=False)}\n"
            f"请生成对应的 Python 脚本，操作 inputs 和 outputs 字典。"
        )
        resp = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
        code = resp.content[0].text if resp.content else ""
        # 去除 markdown 代码块
        if code.startswith("```"):
            lines = code.splitlines()
            code = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
        return {"success": True, "code": code}
    except Exception as e:
        return {"success": False, "error": str(e)}
