"""Capability-backed Skill HTTP adapter.

The legacy ``skills.py`` module remains only as a migration reference; this
router is the registered transport surface and contains no database access.
"""
from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, HTTPException

from backend.platform_sdk.auth import get_current_user
from ..api.compatibility import invoke_agent_capability

router = APIRouter(prefix="/api/skills", tags=["skills"])
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,49}$")


def _owner(user: dict) -> None:
    if not str(user.get("gid") or ""):
        raise HTTPException(401, "用户身份缺失")


def _json_value(value, fallback):
    if value is None:
        return fallback
    try:
        return json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        return fallback


@router.get("")
async def list_skills(scope_filter: str = "all", user=Depends(get_current_user)):
    return await invoke_agent_capability(
        "agent.skill.read", {"operation": "list", "scope_filter": scope_filter}, user
    )


@router.post("")
async def create_skill(body: dict, user=Depends(get_current_user)):
    _owner(user)
    name = str(body.get("name") or "").strip()
    title = str(body.get("title") or "").strip()
    if not name or not title:
        raise HTTPException(400, "name 和 title 不能为空")
    if not _NAME_RE.match(name):
        raise HTTPException(400, "name 格式错误：小写字母/数字/下划线，2-50位，字母开头")
    if body.get("skill_type", "prompt") not in {"prompt", "tool", "flow"}:
        raise HTTPException(400, "skill_type 必须是 prompt / tool / flow")
    payload = {
        "operation": "create", "name": name, "title": title,
        "description": body.get("description", ""),
        "skill_type": body.get("skill_type", "prompt"),
        "scope": body.get("scope", "private"),
        "content": _json_value(body.get("content"), {}),
        "icon": body.get("icon", ""), "tags": _json_value(body.get("tags"), []),
        "sort_order": body.get("sort_order", 0),
    }
    return await invoke_agent_capability("agent.skill.change.apply", payload, user)


@router.put("/{gid}")
async def update_skill(gid: str, body: dict, user=Depends(get_current_user)):
    _owner(user)
    payload = {"operation": "update", "skill_gid": gid}
    for field in ("title", "description", "scope", "status", "icon", "sort_order", "is_pinned"):
        if field in body:
            payload[field] = body[field]
    if "content" in body:
        payload["content"] = _json_value(body["content"], {})
    if "tags" in body:
        payload["tags"] = _json_value(body["tags"], [])
    return await invoke_agent_capability("agent.skill.change.apply", payload, user)


@router.delete("/{gid}")
async def delete_skill(gid: str, user=Depends(get_current_user)):
    _owner(user)
    return await invoke_agent_capability(
        "agent.skill.change.apply", {"operation": "delete", "skill_gid": gid}, user
    )
