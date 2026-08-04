"""Craft-owned project collaboration sessions."""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..data.connection import get_conn
from backend.platform_sdk.auth import require_role
from backend.platform_sdk.ids import next_gid

router = APIRouter(prefix="/api/collab", tags=["collab"])

_MEMBER = require_role(
    "super_admin", "team_admin", "project_admin",
    "rule_admin", "knowledge_admin", "member",
)


class CreateSessionBody(BaseModel):
    section_gid: str


def _serialize(row: dict, *, include_meta: bool = False) -> dict:
    result = {
        "gid": row["gid"],
        "section_gid": row["section_gid"],
        "owner_gid": row["owner_gid"],
        "status": row["status"],
        "participants": row["participants"],
        "created_at": str(row["created_at"]),
        "ended_at": str(row["ended_at"]) if row.get("ended_at") else None,
    }
    if include_meta:
        result["meta"] = row.get("meta")
    return result


@router.get("/sessions")
def list_sessions(
    section_gid: Optional[str] = Query(None),
    current_user: dict = Depends(_MEMBER),
):
    with get_conn() as conn:
        with conn.cursor() as cur:
            if section_gid:
                cur.execute(
                    "SELECT gid,section_gid,owner_gid,status,participants,created_at,ended_at "
                    "FROM workmanship_proj_collab_sessions WHERE section_gid=%s "
                    "ORDER BY created_at DESC",
                    (section_gid,),
                )
            else:
                cur.execute(
                    "SELECT gid,section_gid,owner_gid,status,participants,created_at,ended_at "
                    "FROM workmanship_proj_collab_sessions WHERE status='active' "
                    "ORDER BY created_at DESC"
                )
            rows = [dict(row) for row in cur.fetchall()]
    return {"success": True, "data": [_serialize(row) for row in rows]}


@router.post("/sessions", status_code=201)
def create_session(body: CreateSessionBody, current_user: dict = Depends(_MEMBER)):
    gid = str(next_gid())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_proj_collab_sessions "
                "(gid,section_gid,owner_gid,participants) VALUES (%s,%s,%s,%s)",
                (gid, body.section_gid, current_user["gid"], json.dumps([current_user["gid"]])),
            )
        conn.commit()
    return {"success": True, "data": {"gid": gid}}


@router.get("/sessions/{gid}")
def get_session(gid: str, current_user: dict = Depends(_MEMBER)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gid,section_gid,owner_gid,status,participants,meta,created_at,ended_at "
                "FROM workmanship_proj_collab_sessions WHERE gid=%s",
                (gid,),
            )
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="协同会话不存在")
    return {"success": True, "data": _serialize(dict(row), include_meta=True)}


@router.post("/sessions/{gid}/join")
def join_session(gid: str, current_user: dict = Depends(_MEMBER)):
    participant = json.dumps([current_user["gid"]])
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_proj_collab_sessions "
                "SET participants=JSON_MERGE_PATCH(participants,%s) "
                "WHERE gid=%s AND status='active' AND NOT JSON_CONTAINS(participants,%s)",
                (participant, gid, participant),
            )
        conn.commit()
    return {"success": True}


@router.post("/sessions/{gid}/end")
def end_session(gid: str, current_user: dict = Depends(_MEMBER)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_proj_collab_sessions SET status='ended',ended_at=NOW() "
                "WHERE gid=%s AND owner_gid=%s",
                (gid, current_user["gid"]),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=403, detail="无权结束此会话或会话不存在")
        conn.commit()
    return {"success": True}
