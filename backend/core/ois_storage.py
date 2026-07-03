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
    return bool(cfg.get("identify") and (cfg.get("ois3_url") or cfg.get("api_base")))


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


def upload(data: bytes, ext: str, mime: str, prefix: str = "uploads") -> str | None:
    """上传文件到 OIS，成功返回访问 URL，失败或未配置返回 None。"""
    if not is_enabled():
        return None

    cfg = _get_ois_config()
    identify = cfg.get("identify", "")
    file_key = f"{prefix}/{uuid.uuid4().hex}{ext}"

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
            _log.error("OIS 上传失败: code=%s message=%s", code, msg)
            return None

        uploaded_key = getattr(getattr(response, "data", None), "object_key", file_key)

        public_base = cfg.get("public_base_url", "").rstrip("/")
        if public_base:
            return f"{public_base}/{uploaded_key.lstrip('/')}"
        ois3_url = (cfg.get("ois3_url") or cfg.get("api_base", "")).rstrip("/")
        return f"{ois3_url}/{identify}/{uploaded_key.lstrip('/')}"

    except Exception as e:
        _log.error("OIS 上传失败: %s", e)
        return None
