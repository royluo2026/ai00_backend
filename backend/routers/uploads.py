"""
backend/routers/uploads.py
──────────────────────────
文件上传端点 — 云端清单附件上传

POST /api/uploads
  body: { filename: str, mime: str, data_b64: str }  # base64 编码文件内容
  validate: mime in 白名单; size ≤ 1MB after decode
  save: backend/static/uploads/{uuid4_hex}{ext}
  return: { url: "/static/uploads/{name}", name, mime }

PUT /api/uploads/{filename}
  body: { content: str }  # 纯文本内容（用于 Markdown 等文本文件在线编辑保存）
  validate: 文件必须已存在; size ≤ 1MB
  return: { url: "/static/uploads/{filename}" }
"""
import base64
import os
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.routers.deps import get_current_user_optional
from backend.core import storage as _storage

router = APIRouter(prefix="/api", tags=["uploads"])

# 允许的 MIME 类型前缀
_ALLOWED_MIME_PREFIXES = ("image/", "text/", "application/pdf", "application/json",
                          "application/vnd.openxmlformats-officedocument.spreadsheetml",
                          "application/vnd.ms-excel")
_MAX_SIZE = 5 * 1024 * 1024  # 5MB

_UPLOADS_DIR = Path(__file__).parent.parent / "static" / "uploads"


class UploadRequest(BaseModel):
    filename: str
    mime: str
    data_b64: str


class UpdateRequest(BaseModel):
    content: str | None = None    # 纯文本内容（csv / md / txt）
    data_b64: str | None = None   # base64 二进制内容（xlsx）
    file_url: str | None = None   # 原始完整 URL（MinIO 文件更新时传入，用于定位对象键）


@router.post("/uploads")
def upload_file(
    req: UploadRequest,
    _user: dict = Depends(get_current_user_optional),
):
    # 验证 MIME 类型
    if not any(req.mime.startswith(p) for p in _ALLOWED_MIME_PREFIXES):
        raise HTTPException(400, f"不支持的文件类型：{req.mime}")

    # 解码 base64（validate=True 确保非法字符不被静默忽略）
    try:
        data = base64.b64decode(req.data_b64, validate=True)
    except Exception:
        raise HTTPException(400, "base64 数据格式无效")

    # 验证大小
    if len(data) > _MAX_SIZE:
        raise HTTPException(400, f"文件大小超过 1MB 限制（{len(data)} 字节）")

    # 确定扩展名
    original_ext = Path(req.filename).suffix.lower()
    if not original_ext:
        # 从 MIME 推断
        _MIME_EXT = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "application/pdf": ".pdf",
            "text/markdown": ".md",
            "text/plain": ".txt",
            "text/csv": ".csv",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
            "application/vnd.ms-excel": ".xls",
        }
        original_ext = _MIME_EXT.get(req.mime, ".bin")

    # ── MinIO 优先 ────────────────────────────────────────────────────────────
    minio_url = _storage.upload(data, original_ext, req.mime)
    if minio_url:
        return {"url": minio_url, "name": req.filename, "mime": req.mime}

    # ── 本地磁盘 fallback ─────────────────────────────────────────────────────
    # 生成唯一文件名
    unique_name = uuid.uuid4().hex + original_ext

    # 写文件
    _UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    dest = _UPLOADS_DIR / unique_name
    dest.write_bytes(data)

    return {
        "url": f"/static/uploads/{unique_name}",
        "name": req.filename,
        "mime": req.mime,
    }


@router.put("/uploads/{filename}")
def update_upload(
    filename: str,
    req: UpdateRequest,
    _user: dict = Depends(get_current_user_optional),
):
    # 防止路径穿越：只允许纯文件名（无目录分隔符）
    if not re.match(r'^[a-zA-Z0-9_\-\.]+$', filename) or '..' in filename:
        raise HTTPException(400, "非法文件名")

    # 只允许更新文本类或表格类文件
    suffix = Path(filename).suffix.lower()
    if suffix not in ('.md', '.markdown', '.txt', '.json', '.csv', '.xlsx', '.xls'):
        raise HTTPException(400, f"不支持编辑此类型文件：{suffix}")

    # ── 先解码内容 ─────────────────────────────────────────────────────────────
    _MIME_MAP = {
        '.md': 'text/markdown', '.markdown': 'text/markdown',
        '.txt': 'text/plain',   '.json': 'application/json',
        '.csv': 'text/csv',
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        '.xls':  'application/vnd.ms-excel',
    }
    mime = _MIME_MAP.get(suffix, 'text/plain')

    if req.data_b64 is not None:
        try:
            file_bytes = base64.b64decode(req.data_b64, validate=True)
        except Exception:
            raise HTTPException(400, "base64 数据格式无效")
        if len(file_bytes) > _MAX_SIZE:
            raise HTTPException(400, "内容超过 1MB 限制")
    elif req.content is not None:
        content_bytes = req.content.encode('utf-8')
        if len(content_bytes) > _MAX_SIZE:
            raise HTTPException(400, "内容超过 1MB 限制")
        file_bytes = content_bytes
    else:
        raise HTTPException(400, "content 或 data_b64 不能同时为空")

    # ── MinIO 路径：file_url 指向 MinIO 对象 ──────────────────────────────────
    dest = _UPLOADS_DIR / filename
    if not dest.exists():
        if req.file_url:
            updated = _storage.update(req.file_url, file_bytes, mime)
            if updated:
                return {"url": updated}
        raise HTTPException(404, "文件不存在")

    # ── 本地磁盘 ───────────────────────────────────────────────────────────────
    dest.write_bytes(file_bytes)
    return {"url": f"/static/uploads/{filename}"}
