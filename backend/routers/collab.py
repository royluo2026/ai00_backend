"""
backend/routers/collab.py
──────────────────────────
多人协同 API（collab_sessions）

端点：
  GET  /api/collab/sessions               → 会话列表（按工段过滤）
  POST /api/collab/sessions               → 创建/加入会话
  GET  /api/collab/sessions/{gid}         → 会话详情
  POST /api/collab/sessions/{gid}/join    → 加入会话
  POST /api/collab/sessions/{gid}/end     → 结束会话
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.db.connection import get_conn
from backend.routers.deps import get_current_user, require_role
from backend.utils.gid import next_gid

router = APIRouter(prefix="/api/collab", tags=["collab"])

_MEMBER = require_role("super_admin", "team_admin", "project_admin",
                       "rule_admin", "knowledge_admin", "member")


class CreateSessionBody(BaseModel):
    section_gid: str


@router.get("/sessions")
def list_sessions(
    section_gid: Optional[str] = Query(None),
    current_user: dict = Depends(_MEMBER)
):
    with get_conn() as conn:
        with conn.cursor() as cur:
            if section_gid:
                cur.execute(
                    "SELECT gid, section_gid, owner_gid, status, participants, created_at, ended_at "
                    "FROM workmanship_proj_collab_sessions WHERE section_gid = %s ORDER BY created_at DESC",
                    (section_gid,)
                )
            else:
                cur.execute(
                    "SELECT gid, section_gid, owner_gid, status, participants, created_at, ended_at "
                    "FROM workmanship_proj_collab_sessions WHERE status = 'active' ORDER BY created_at DESC"
                )
            rows = cur.fetchall()
    return {"success": True, "data": [
        {
            "gid": r[0], "section_gid": r[1], "owner_gid": r[2],
            "status": r[3], "participants": r[4],
            "created_at": str(r[5]), "ended_at": str(r[6]) if r[6] else None
        }
        for r in rows
    ]}


@router.post("/sessions", status_code=201)
def create_session(body: CreateSessionBody, current_user: dict = Depends(_MEMBER)):
    gid = str(next_gid())
    import json
    participants = json.dumps([current_user["gid"]])
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_proj_collab_sessions (gid, section_gid, owner_gid, participants) "
                "VALUES (%s, %s, %s, %s)",
                (gid, body.section_gid, current_user["gid"], participants)
            )
        conn.commit()
    return {"success": True, "data": {"gid": gid}}


@router.get("/sessions/{gid}")
def get_session(gid: str, current_user: dict = Depends(_MEMBER)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid, section_gid, owner_gid, status, participants, meta, created_at, ended_at "
                "FROM workmanship_proj_collab_sessions WHERE gid = %s",
                (gid,)
            )
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="协同会话不存在")
    return {"success": True, "data": {
        "gid": row[0], "section_gid": row[1], "owner_gid": row[2],
        "status": row[3], "participants": row[4], "meta": row[5],
        "created_at": str(row[6]), "ended_at": str(row[7]) if row[7] else None
    }}


@router.post("/sessions/{gid}/join")
def join_session(gid: str, current_user: dict = Depends(_MEMBER)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_proj_collab_sessions SET participants = JSON_MERGE_PATCH(participants, %s) "
                "WHERE gid = %s AND status = 'active' "
                "AND NOT JSON_CONTAINS(participants, %s)",
                (f'["{current_user["gid"]}"]', gid, f'["{current_user["gid"]}"]')
            )
        conn.commit()
    return {"success": True}


@router.post("/sessions/{gid}/end")
def end_session(gid: str, current_user: dict = Depends(_MEMBER)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_proj_collab_sessions SET status = 'ended', ended_at = NOW() "
                "WHERE gid = %s AND owner_gid = %s",
                (gid, current_user["gid"])
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=403, detail="无权结束此会话或会话不存在")
        conn.commit()
    return {"success": True}
