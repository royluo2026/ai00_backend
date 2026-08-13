"""
backend/core/storage.py
───────────────────────
boto3 MinIO（S3-compatible）封装。

配置优先级：
  1. app.system_config WHERE key='minio_config'（超管在设置页面保存）
  2. 环境变量 MINIO_ENDPOINT / MINIO_ACCESS_KEY / MINIO_SECRET_KEY / MINIO_BUCKET
  3. 均未配置 → 所有 upload() 返回 None，调用方回退到本地磁盘

公开 API
────────
  init_storage()                         → 启动时调用一次（幂等）
  upload(data, ext, mime, prefix="")     → str | None  （完整公开 URL 或 None）
  delete(url)                            → None        （最大努力，静默失败）
  update(url, data, mime)                → str | None  （覆盖写，返回原 URL）
  _is_ready()                            → bool
"""
from __future__ import annotations

import io
import hashlib
import json
import logging
import uuid
from datetime import datetime

_log = logging.getLogger(__name__)

# ── 模块级状态（每进程初始化一次）─────────────────────────────────────────────
_s3 = None        # boto3 S3 client
_bucket: str = ""
_public_url: str = ""   # 不含尾斜杠，如 "http://192.168.1.100:9000/ai00"


# ── 公开策略 JSON（匿名只读）──────────────────────────────────────────────────
def _public_policy(bucket: str) -> str:
    return json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"AWS": ["*"]},
            "Action":    ["s3:GetObject"],
            "Resource":  [f"arn:aws:s3:::{bucket}/*"],
        }]
    })


# ── 配置读取（DB 优先，env var 兜底）─────────────────────────────────────────

def _get_minio_config() -> dict:
    """
    返回 {endpoint, access_key, secret_key, bucket, public_url}。
    找不到有效配置则返回 {}。
    """
    # 1. 从 DB（超管在设置页面保存）
    try:
        from backend.db.connection import get_conn
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT `value` FROM workmanship_app_system_config WHERE `key`='minio_config'"
                )
                row = cur.fetchone()
                if row and row["value"]:
                    cfg = (
                        json.loads(row["value"])
                        if isinstance(row["value"], str)
                        else dict(row["value"])
                    )
                    if cfg.get("endpoint") and cfg.get("access_key"):
                        pub = cfg.get("public_url", "").rstrip("/")
                        if not pub:
                            bkt = cfg.get("bucket", "ai00")
                            pub = f"{cfg['endpoint'].rstrip('/')}/{bkt}"
                        return {**cfg, "public_url": pub}
    except Exception:
        pass  # DB 未就绪时静默（启动顺序问题）

    # 2. 环境变量
    try:
        from backend.config import get_settings
        s = get_settings()
        if s.minio_enabled:
            return {
                "endpoint":   s.minio_endpoint,
                "access_key": s.minio_access_key,
                "secret_key": s.minio_secret_key,
                "bucket":     s.minio_bucket,
                "public_url": s.minio_public_url,
            }
    except Exception:
        pass

    return {}


# ── 初始化 ────────────────────────────────────────────────────────────────────

def init_storage() -> None:
    """
    初始化 boto3 S3 客户端，确保 bucket 存在且设为公开只读。
    幂等：可多次调用，重新调用会重置连接（设置页面保存后触发）。
    """
    global _s3, _bucket, _public_url

    cfg = _get_minio_config()
    if not cfg.get("endpoint"):
        _log.info("MinIO 未配置，使用本地磁盘存储")
        _s3 = None
        return

    try:
        import boto3
        from botocore.client import Config as _BotoCfg

        _s3 = boto3.client(
            "s3",
            endpoint_url=cfg["endpoint"],
            aws_access_key_id=cfg["access_key"],
            aws_secret_access_key=cfg["secret_key"],
            config=_BotoCfg(signature_version="s3v4"),
            region_name="us-east-1",   # MinIO 忽略 region，但 boto3 必填
        )
        _bucket     = cfg.get("bucket", "ai00")
        _public_url = cfg["public_url"].rstrip("/")

        # 创建 bucket（若不存在）
        try:
            _s3.head_bucket(Bucket=_bucket)
        except Exception:
            _s3.create_bucket(Bucket=_bucket)
            _log.info("MinIO bucket '%s' 已创建", _bucket)

        # 设置公开只读策略（幂等 PUT）
        _s3.put_bucket_policy(Bucket=_bucket, Policy=_public_policy(_bucket))

        _log.info("✅ MinIO 初始化成功: %s / %s", cfg["endpoint"], _bucket)

    except Exception as e:
        _s3 = None
        _log.warning("⚠️ MinIO 初始化失败（回退本地磁盘）: %s", e)


def _is_ready() -> bool:
    return _s3 is not None


# ── 对象键生成 ─────────────────────────────────────────────────────────────────

def _object_key(ext: str, prefix: str = "") -> str:
    """
    生成唯一对象键。
    格式：[prefix/]{YYYY}/{uuid_hex}{ext}
    示例：2025/a3f9e12d8b...c04.jpg  或  bop_pics/2025/a3f9...c04.jpg
    """
    year = datetime.utcnow().strftime("%Y")
    name = uuid.uuid4().hex + ext
    if prefix:
        return f"{prefix.strip('/')}/{year}/{name}"
    return f"{year}/{name}"


# ── 上传 ──────────────────────────────────────────────────────────────────────

def upload(data: bytes, ext: str, mime: str, prefix: str = "") -> str | None:
    """
    上传字节到对象存储。成功返回完整公开 URL，失败或未配置返回 None（调用方回退本地磁盘）。

    优先级：OIS → MinIO → None（本地磁盘）

    参数
    ────
    data    原始字节
    ext     含点扩展名，如 ".jpg"
    mime    MIME 类型，如 "image/jpeg"
    prefix  可选子目录前缀，如 "bop_pics"
    """
    _log.info("storage upload start prefix=%s ext=%s mime=%s bytes=%s", prefix, ext, mime, len(data))
    # 1. OIS（理想汽车内网对象存储）
    try:
        from backend.core import ois_storage as _ois
        if _ois.is_enabled():
            url = _ois.upload(data, ext, mime, prefix)
            _log.info("storage upload ois result url=%s", url)
            if url:
                return url
    except Exception as _e:
        _log.warning("OIS upload 失败，降级 MinIO: %s", _e)

    # 2. MinIO / S3-compatible
    if not _is_ready():
        return None

    key = _object_key(ext, prefix)
    _log.info("storage upload using minio key=%s public_url=%s", key, _public_url)
    try:
        _s3.put_object(
            Bucket=_bucket,
            Key=key,
            Body=io.BytesIO(data),
            ContentType=mime,
            ContentLength=len(data),
        )
        return f"{_public_url}/{key}"
    except Exception as e:
        _log.error("MinIO upload 失败 (key=%s): %s", key, e)
        return None


# ── 删除 ──────────────────────────────────────────────────────────────────────

def delete(url: str) -> None:
    """
    按完整公开 URL 删除对象。静默处理所有错误（不影响主流程）。
    """
    if not _is_ready() or not url:
        return
    try:
        key = url.split(_public_url, 1)[-1].lstrip("/")
        if key:
            _s3.delete_object(Bucket=_bucket, Key=key)
    except Exception as e:
        _log.warning("MinIO delete 失败 (url=%s): %s", url, e)


# ── 覆盖更新 ──────────────────────────────────────────────────────────────────

def update(url: str, data: bytes, mime: str) -> str | None:
    """
    覆盖 MinIO 中已有对象（key 从存储的 URL 中解析）。
    成功返回相同 URL，失败返回 None。
    """
    if not _is_ready() or not url:
        return None
    try:
        key = url.split(_public_url, 1)[-1].lstrip("/")
        if not key:
            return None
        _s3.put_object(
            Bucket=_bucket,
            Key=key,
            Body=io.BytesIO(data),
            ContentType=mime,
            ContentLength=len(data),
        )
        return url
    except Exception as e:
        _log.error("MinIO update 失败 (url=%s): %s", url, e)
        return None


def _normalized_immutable_key(object_key: str) -> str:
    normalized = str(object_key or "").strip().lstrip("/")
    if not normalized or ".." in normalized.split("/") or "//" in normalized:
        raise ValueError("object_key must be a normalized relative object key")
    return normalized


def put_immutable(object_key: str, data: bytes, media_type: str) -> dict | None:
    """Store bytes under an exact immutable key, preferring OIS then MinIO."""
    normalized = _normalized_immutable_key(object_key)
    if not isinstance(data, bytes):
        raise TypeError("data must be bytes")
    digest = hashlib.sha256(data).hexdigest()
    try:
        from backend.core import ois_storage
        stored = ois_storage.put_immutable(normalized, data, media_type)
        if stored:
            return stored
    except Exception as exc:
        _log.warning("OIS immutable upload failed, falling back to MinIO: %s", exc)

    if not _is_ready():
        init_storage()
    if not _is_ready():
        return None
    try:
        _s3.put_object(
            Bucket=_bucket, Key=normalized, Body=io.BytesIO(data),
            ContentType=media_type, ContentLength=len(data),
        )
        return {
            "object_key": normalized, "sha256": digest,
            "byte_size": len(data), "media_type": media_type,
        }
    except Exception as exc:
        _log.error("MinIO immutable upload failed (key=%s): %s", normalized, exc)
        return None


def get_immutable(object_key: str, expected_sha256: str = "") -> bytes | None:
    """Read exact immutable bytes, preferring OIS then MinIO."""
    normalized = _normalized_immutable_key(object_key)
    try:
        from backend.core import ois_storage
        data = ois_storage.get_immutable(normalized, expected_sha256)
        if data is not None:
            return data
    except Exception as exc:
        _log.warning("OIS immutable read failed, falling back to MinIO: %s", exc)

    if not _is_ready():
        init_storage()
    if not _is_ready():
        return None
    try:
        response = _s3.get_object(Bucket=_bucket, Key=normalized)
        body = response.get("Body")
        data = body.read() if hasattr(body, "read") else body
        if not isinstance(data, bytes):
            raise RuntimeError("MinIO returned no byte payload")
        if expected_sha256 and hashlib.sha256(data).hexdigest() != expected_sha256:
            raise RuntimeError("immutable object digest mismatch")
        return data
    except Exception as exc:
        _log.error("MinIO immutable read failed (key=%s): %s", normalized, exc)
        return None
