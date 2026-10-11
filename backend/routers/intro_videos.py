"""Presentation case videos: public playback, server-authenticated admin upload."""
from __future__ import annotations

import json
import tempfile
import re
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool
from backend.core import ois_storage

from backend.db.connection import get_conn
from backend.routers.deps import require_role

router = APIRouter(prefix="/api/intro-videos", tags=["intro-videos"])
_ADMIN = require_role("super_admin")
_CASES = {"craft", "simulation"}
MAX_BYTES = 512 * 1024 * 1024


def _case(case_id: str) -> None:
    if case_id not in _CASES:
        raise HTTPException(404, "案例不存在")


def _metadata(case_id: str) -> dict | None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT `value` FROM workmanship_app_system_config WHERE `key`=%s", (f"platform_intro_video_{case_id}",))
        row = cur.fetchone()
        return json.loads(row["value"]) if row else None


def _save(case_id: str, value: dict) -> None:
    encoded = json.dumps(value, ensure_ascii=False)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO workmanship_app_system_config (`key`,`value`,description,updated_at) VALUES (%s,%s,'系统介绍案例视频',NOW()) ON DUPLICATE KEY UPDATE `value`=%s,updated_at=NOW()", (f"platform_intro_video_{case_id}", encoded, encoded))


def _public(case_id: str, value: dict) -> dict:
    return {"case_id": case_id, "mime": value["mime"], "size": value["size"], "revision": value["revision"], "url": f"/api/intro-videos/{case_id}/content?v={value['revision']}"}


@router.get("")
def list_videos():
    return {"videos": [_public(case_id, value) for case_id in sorted(_CASES) if (value := _metadata(case_id))]}


@router.put("/{case_id}")
async def upload_video(case_id: str, request: Request, user: dict = Depends(_ADMIN)):
    _case(case_id)
    mime = request.headers.get("content-type", "").split(";", 1)[0].lower()
    ext = {"video/mp4": ".mp4", "video/webm": ".webm"}.get(mime)
    if not ext:
        raise HTTPException(415, "请上传 MP4 或 WebM 视频")
    if not ois_storage.is_enabled():
        raise HTTPException(503, "后端 OIS 尚未配置，视频未保存")
    revision = uuid4().hex
    object_key = f"platform-intro/videos/{case_id}/{revision}{ext}"
    size, signature = 0, b""
    # A temporary spool bounds memory use; the durable video exists only in OIS.
    with tempfile.TemporaryFile() as stream:
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_BYTES:
                raise HTTPException(413, "视频不能超过 512 MB")
            if len(signature) < 16:
                signature = (signature + chunk)[:16]
            stream.write(chunk)
        valid = signature[4:8] == b"ftyp" if mime == "video/mp4" else signature[:4] == b"\x1aE\xdf\xa3"
        if not size or not valid:
            raise HTTPException(415, "视频内容与格式不匹配")
        uploaded_key = await run_in_threadpool(ois_storage.put_immutable_stream, object_key, stream)
    if uploaded_key != object_key:
        raise HTTPException(502, "OIS 上传失败，未替换当前案例视频")
    value = {"storage":"ois", "object_key":object_key, "mime":mime, "size":size, "revision":revision, "uploaded_by":str(user["gid"])}
    # Preserve the previous binding unless both cloud upload and DB write succeed.
    await run_in_threadpool(_save, case_id, value)
    return _public(case_id, value)


@router.get("/{case_id}/content")
def video_content(case_id: str, request: Request):
    _case(case_id)
    value = _metadata(case_id)
    if not value or value.get("storage") != "ois" or not re.fullmatch(r"platform-intro/videos/" + case_id + r"/[a-f0-9]{32}\.(mp4|webm)", value.get("object_key", "")):
        raise HTTPException(404, "案例云端视频尚未上传")
    url = ois_storage.generate_access_url(value["object_key"], expire_in_seconds=3600)
    if not url or not url.startswith("https://"):
        raise HTTPException(502, "无法获取 OIS 播放地址，请检查后端存储配置")
    # OIS handles byte ranges and seeking. The stable DB reference is the key,
    # never the expiring playback URL.
    return RedirectResponse(url, status_code=307, headers={"Cache-Control":"no-store"})
