"""
backend/core/ois_storage.py  (v2 — OisS3Client SDK)
─────────────────────────────────────────────────────
安装 SDK：
  pip install ois3-sdk-python \
    --index-url https://artifactory.ep.chehejia.com/artifactory/api/pypi/licloud-pypi/simple

必填配置字段：
  identify       — 应用标识（OIS bucket 名）
  env            — 环境，如 ontest / prod
  ois3_url       — OIS 服务地址（原 api_base）
  region         — 区域，如 cnhb01
  licloud_appid  — 应用 ID（对应 SDK app_id）
  idaas_url      — IdaaS 认证地址
  idaas_client_id / idaas_client_secret / idaas_service_id

可选：
  public_base_url — 文件 CDN 访问地址；未填则用 ois3_url 拼接
"""
from __future__ import annotations

import logging
import uuid
from urllib.parse import quote

_log = logging.getLogger(__name__)


def _get_ois_config() -> dict:
    """读取 OIS 配置：DB 优先，env var 兜底。"""
    try:
        from backend.db.connection import get_conn
        import json as _j
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT `value` FROM workmanship_app_system_config WHERE `key`='ois_config'"
                )
                row = cur.fetchone()
                if row and row["value"]:
                    cfg = _j.loads(row["value"]) if isinstance(row["value"], str) else dict(row["value"])
                    if cfg.get("identify"):
                        return cfg
    except Exception:
        pass
    try:
        from backend.config import get_settings
        s = get_settings()
        if getattr(s, "ois_identify", ""):
            return {
                "identify":            s.ois_identify,
                "env":                 getattr(s, "ois_env", ""),
                "ois3_url":            getattr(s, "ois_ois3_url", ""),
                "region":              getattr(s, "ois_region", ""),
                "licloud_appid":       getattr(s, "ois_licloud_appid", ""),
                "idaas_url":           getattr(s, "ois_idaas_url", ""),
                "idaas_client_id":     getattr(s, "ois_idaas_client_id", ""),
                "idaas_client_secret": getattr(s, "ois_idaas_client_secret", ""),
                "idaas_service_id":    getattr(s, "ois_idaas_service_id", ""),
                "public_base_url":     getattr(s, "ois_public_base_url", ""),
            }
    except Exception:
        pass
    return {}


def is_enabled() -> bool:
    cfg = _get_ois_config()
    required = (
        "identify", "env", "region", "licloud_appid", "idaas_url",
        "idaas_client_id", "idaas_client_secret", "idaas_service_id",
    )
    return bool(
        all(str(cfg.get(name, "")).strip() for name in required)
        and str(cfg.get("ois3_url") or cfg.get("api_base", "")).strip()
    )


def _make_client():
    """创建 OisS3Client 实例，返回 (client, error_msg)。"""
    try:
        from client.ois_s3_client import OisS3Client, ClientOptions
    except ImportError:
        return None, (
            "ois3-sdk-python 未安装，请执行: pip install ois3-sdk-python "
            "--index-url https://artifactory.ep.chehejia.com/artifactory/api/pypi/licloud-pypi/simple"
        )
    cfg = _get_ois_config()
    if not cfg.get("identify"):
        return None, "OIS 未配置"
    try:
        # ClientOptions 字段名见 ois_client.py _build_client_options mapping
        options = ClientOptions(
            env=cfg.get("env", ""),
            region=cfg.get("region", ""),
            app_id=cfg.get("licloud_appid", ""),
            ois_service_url=cfg.get("ois3_url") or cfg.get("api_base", ""),
            idaas_url=cfg.get("idaas_url", ""),
            idaas_client_id=cfg.get("idaas_client_id", ""),
            idaas_client_secret=cfg.get("idaas_client_secret", ""),
            idaas_service_id=cfg.get("idaas_service_id", ""),
        )
        _log.info("OIS SDK init: env=%s ois_service_url=%s identify=%s",
                  options.env, options.ois_service_url, cfg.get("identify"))
        client = OisS3Client(options)
        return client, None
    except Exception as e:
        return None, str(e)


def generate_access_url(object_key: str, expire_in_seconds: int = 1800) -> str | None:
    if not is_enabled() or not object_key:
        return None

    cfg = _get_ois_config()
    identify = cfg.get("identify", "")
    if not identify:
        return None

    client, err = _make_client()
    if not client:
        _log.error("OIS 客户端初始化失败: %s", err)
        return None

    try:
        public_base = cfg.get("public_base_url", "").rstrip("/")
        if public_base:
            return f"{public_base}/{object_key.lstrip('/')}"
        response = client.generate_pre_signed_url(identify, object_key, expire_in_seconds)
        if not (hasattr(response, "is_succeed") and response.is_succeed()):
            code = getattr(response, "code", "?")
            msg = getattr(response, "message", "?")
            _log.error("OIS 生成签名 URL 失败: code=%s message=%s", code, msg)
            return None
        return getattr(response, "data", None)
    except Exception as e:
        _log.error("OIS 生成签名 URL 失败: %s", e)
        return None



def upload(data: bytes, ext: str, mime: str, prefix: str = "uploads") -> str | None:
    """上传文件到 OIS，成功返回访问 URL，失败或未配置返回 None。"""
    if not is_enabled():
        return None

    cfg = _get_ois_config()
    identify = cfg.get("identify", "")
    file_key = f"{prefix}/{uuid.uuid4().hex}{ext}"
    _log.info("ois upload start identify=%s file_key=%s mime=%s bytes=%s", identify, file_key, mime, len(data))

    client, err = _make_client()
    if not client:
        _log.error("OIS 客户端初始化失败: %s", err)
        return None

    try:
        import io
        response = client.put_object(identify, file_key, io.BytesIO(data))

        if not (hasattr(response, "is_succeed") and response.is_succeed()):
            code = getattr(response, "code", "?")
            msg  = getattr(response, "message", "?")
            _log.error("OIS 上传失败: code=%s message=%s file_key=%s", code, msg, file_key)
            return None

        uploaded_key = getattr(getattr(response, "data", None), "object_key", file_key)
        _log.info("ois upload success requested_key=%s uploaded_key=%s", file_key, uploaded_key)
        access_url = generate_access_url(uploaded_key)
        _log.info("ois upload access url uploaded_key=%s url=%s", uploaded_key, access_url)
        if access_url:
            return access_url
        _log.warning("OIS 上传成功但无法生成访问 URL")
        return None

    except Exception as e:
        _log.error("OIS 上传失败: %s | file_key=%s", e, file_key)
        return None


def put_immutable(object_key: str, data: bytes, mime: str) -> dict | None:
    """Write a caller-generated immutable object key and return its stable metadata.

    The key must be content-addressed or revision-addressed by the caller. This
    function never generates a replacement key and never treats a temporary URL
    as the durable reference.
    """
    import hashlib
    import io

    normalized = str(object_key or "").strip().lstrip("/")
    if not normalized or ".." in normalized.split("/") or "//" in normalized:
        raise ValueError("object_key must be a normalized relative OIS key")
    if not isinstance(data, bytes):
        raise TypeError("data must be bytes")
    if not is_enabled():
        return None
    cfg = _get_ois_config()
    identify = cfg.get("identify", "")
    client, err = _make_client()
    if not client:
        _log.error("OIS 客户端初始化失败: %s", err)
        return None
    try:
        response = client.put_object(identify, normalized, io.BytesIO(data))
        if not (hasattr(response, "is_succeed") and response.is_succeed()):
            _log.error(
                "OIS immutable upload failed: code=%s message=%s object_key=%s",
                getattr(response, "code", "?"),
                getattr(response, "message", "?"),
                normalized,
            )
            return None
        uploaded_key = getattr(getattr(response, "data", None), "object_key", normalized)
        if uploaded_key != normalized:
            raise RuntimeError(
                f"OIS changed immutable object key: expected {normalized!r}, got {uploaded_key!r}"
            )
        return {
            "object_key": normalized,
            "sha256": hashlib.sha256(data).hexdigest(),
            "byte_size": len(data),
            "media_type": mime,
            "access_url": generate_access_url(normalized),
        }
    except Exception as exc:
        _log.error("OIS immutable upload failed: %s | object_key=%s", exc, normalized)
        return None


def put_immutable_stream(object_key: str, stream) -> str | None:
    """Upload a host-verified stream under an exact immutable object key."""
    normalized = str(object_key or "").strip().lstrip("/")
    if not normalized or ".." in normalized.split("/") or "//" in normalized:
        raise ValueError("object_key must be a normalized relative OIS key")
    if not hasattr(stream, "read") or not hasattr(stream, "seek"):
        raise TypeError("stream must be a seekable binary stream")
    if not is_enabled():
        return None
    cfg = _get_ois_config()
    client, err = _make_client()
    if not client:
        _log.error("OIS client unavailable: %s", err)
        return None
    try:
        stream.seek(0)
        response = client.put_object(cfg.get("identify", ""), normalized, stream)
        if not (hasattr(response, "is_succeed") and response.is_succeed()):
            _log.error(
                "OIS immutable stream upload failed: code=%s key=%s",
                getattr(response, "code", "?"), normalized,
            )
            return None
        uploaded_key = getattr(getattr(response, "data", None), "object_key", normalized)
        if uploaded_key != normalized:
            raise RuntimeError(
                f"OIS changed immutable object key: expected {normalized!r}, got {uploaded_key!r}"
            )
        return normalized
    except Exception as exc:
        _log.error("OIS immutable stream upload failed: %s | object_key=%s", exc, normalized)
        return None

def get_immutable(object_key: str, expected_sha256: str = "") -> bytes | None:
    """Read an immutable OIS object and optionally verify its SHA-256 digest."""
    import hashlib

    normalized = str(object_key or "").strip().lstrip("/")
    if not normalized or ".." in normalized.split("/") or "//" in normalized:
        raise ValueError("object_key must be a normalized relative OIS key")
    if not is_enabled():
        return None
    cfg = _get_ois_config()
    client, err = _make_client()
    if not client:
        _log.error("OIS client unavailable: %s", err)
        return None
    try:
        response = client.get_object(cfg.get("identify", ""), normalized)
        if not (hasattr(response, "is_succeed") and response.is_succeed()):
            _log.error("OIS immutable read failed: code=%s key=%s", getattr(response, "code", "?"), normalized)
            return None
        value = getattr(response, "data", None)
        if isinstance(value, bytes):
            data = value
        elif hasattr(value, "read"):
            data = value.read()
        else:
            body = getattr(value, "body", None) or getattr(value, "content", None)
            data = body.read() if hasattr(body, "read") else body
        if not isinstance(data, bytes):
            raise RuntimeError("OIS get_object returned no byte payload")
        if expected_sha256 and hashlib.sha256(data).hexdigest() != expected_sha256:
            raise RuntimeError("OIS immutable object digest mismatch")
        return data
    except Exception as exc:
        _log.error("OIS immutable read failed: %s | object_key=%s", exc, normalized)
        return None
