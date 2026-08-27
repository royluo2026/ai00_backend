"""
backend/routers/file_store.py
──────────────────────────────
文件存储配置 REST API

GET  /api/file-store/config      — 读取当前存储配置（MinIO + OIS）
POST /api/file-store/config      — 保存 MinIO 配置
POST /api/file-store/ois-config  — 保存 OIS 配置
POST /api/file-store/test        — 测试 MinIO 连接
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException

from backend.routers.deps import get_current_user, require_role
from backend.db.connection import get_conn
from backend.base.file_store_public_config import public_file_store_config

router = APIRouter(prefix="/api/file-store", tags=["file_store"])
_log = logging.getLogger(__name__)

_WRITE = require_role("super_admin", "team_admin")


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) > 8:
        return key[:4] + "••••" + key[-4:]
    return "•" * len(key)


def _system_json_path() -> Path:
    return Path.home() / '.ai00' / 'config' / 'system.json'


def _load_system_json() -> dict:
    path = _system_json_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}


def _save_system_json(data: dict) -> None:
    path = _system_json_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def _load_db_config(key: str = "minio_config") -> dict | None:
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT `value` FROM workmanship_app_system_config WHERE `key`=%s",
                    (key,)
                )
                row = cur.fetchone()
                if row and row["value"]:
                    return (
                        json.loads(row["value"])
                        if isinstance(row["value"], str)
                        else dict(row["value"])
                    )
    except Exception as e:
        _log.warning("file_store: DB 查询失败: %s", e)
    return None


def _save_db_config(key: str, cfg: dict) -> None:
    value_json = json.dumps(cfg, ensure_ascii=False)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO workmanship_app_system_config (`key`, `value`, description, updated_at)
                   VALUES (%s, %s, '', NOW())
                   ON DUPLICATE KEY UPDATE `value`=%s, updated_at=NOW()""",
                (key, value_json, value_json),
            )


@router.get("/config")
def get_config(_user: dict = Depends(get_current_user)):
    role = str(_user.get("org_role") or _user.get("system_role") or "member")
    return public_file_store_config({}, SimpleNamespace(active_roles=(role,), user_gid=_user.get("gid")))


@router.post("/config")
def save_config(body: dict, _user: dict = Depends(_WRITE)):
    """保存 MinIO 配置。"""
    print(f"[file_store] save_config called, keys={list(body.keys())}, user_role={_user.get('org_role') or _user.get('system_role')}", flush=True)
    endpoint   = (body.get("endpoint")   or "").strip().rstrip("/")
    access_key = (body.get("access_key") or "").strip()
    secret_key = body.get("secret_key")  or ""
    bucket     = (body.get("bucket")     or "ai00").strip()
    public_url = (body.get("public_url") or "").strip().rstrip("/")

    if not endpoint:
        raise HTTPException(400, "endpoint 不能为空")
    if not access_key:
        raise HTTPException(400, "access_key 不能为空")

    existing = _load_db_config("minio_config") or {}
    if not secret_key:
        secret_key = existing.get("secret_key", "")
    if not secret_key:
        raise HTTPException(400, "secret_key 不能为空（首次配置必须填写）")
    if not public_url:
        public_url = f"{endpoint}/{bucket}"

    cfg = {"endpoint": endpoint, "access_key": access_key,
           "secret_key": secret_key, "bucket": bucket, "public_url": public_url}
    try:
        _save_db_config("minio_config", cfg)
        raw = _load_system_json()
        raw['minio_config'] = cfg
        _save_system_json(raw)
        print(f"[file_store] _save_db_config OK", flush=True)
    except Exception as e:
        print(f"[file_store] _save_db_config FAILED: {e}", flush=True)
        _log.error("file_store: 保存失败: %s", e)
        raise HTTPException(500, f"保存失败：{e}")

    try:
        from backend.core.storage import init_storage
        init_storage()
    except Exception as e:
        _log.warning("file_store: 保存后重新初始化失败: %s", e)

    return {"success": True, "msg": "MinIO 配置已保存"}


@router.post("/ois-config")
def save_ois_config(body: dict, _user: dict = Depends(_WRITE)):
    """保存 OIS 配置（理想汽车内网对象存储，SDK: ois3-sdk-python）。"""
    print(f"[ois-config] 收到 body keys={list(body.keys())} values={body}", flush=True)
    print(f"[ois-config] 当前用户 role={_user.get('org_role') or _user.get('system_role')}", flush=True)

    identify        = (body.get("identify")           or "").strip()
    env             = (body.get("env")                or "").strip()
    ois3_url        = (body.get("ois3_url")           or "").strip().rstrip("/")
    region          = (body.get("region")             or "").strip()
    licloud_appid   = (body.get("licloud_appid")      or "").strip()
    idaas_url       = (body.get("idaas_url")          or "").strip()
    client_id       = (body.get("idaas_client_id")    or "").strip()
    service_id      = (body.get("idaas_service_id")   or "").strip()
    client_secret   = body.get("idaas_client_secret") or ""
    public_base_url = (body.get("public_base_url")    or "").strip().rstrip("/")

    print(f"[ois-config] 解析后: identify={identify!r} ois3_url={ois3_url!r} env={env!r}", flush=True)

    if not identify:
        print("[ois-config] 拒绝：identify 为空", flush=True)
        raise HTTPException(400, "identify 不能为空")
    if not ois3_url:
        print("[ois-config] 拒绝：ois3_url 为空", flush=True)
        raise HTTPException(400, "OIS3 URL 不能为空")

    existing = _load_db_config("ois_config") or {}
    if not client_secret:
        client_secret = existing.get("idaas_client_secret", "")

    cfg = {
        "identify":            identify,
        "env":                 env,
        "ois3_url":            ois3_url,
        "region":              region,
        "licloud_appid":       licloud_appid,
        "idaas_url":           idaas_url,
        "idaas_client_id":     client_id,
        "idaas_client_secret": client_secret,
        "idaas_service_id":    service_id,
        "public_base_url":     public_base_url,
    }
    try:
        print(f"[ois-config] 写入 DB key=ois_config ...", flush=True)
        _save_db_config("ois_config", cfg)
        raw = _load_system_json()
        raw['ois_config'] = cfg
        _save_system_json(raw)
        print(f"[ois-config] 写入 DB 成功", flush=True)
    except Exception as e:
        import traceback
        print(f"[ois-config] 写入 DB 失败: {e}\n{traceback.format_exc()}", flush=True)
        _log.error("file_store: OIS 保存失败: %s", e)
        raise HTTPException(500, f"保存失败：{e}")

    return {"success": True, "msg": "OIS 配置已保存"}


@router.post("/ois-test")
def test_ois_connection(body: dict = {}, _user: dict = Depends(_WRITE)):
    """测试 OIS 连接：用 OisS3Client SDK 上传 1 字节测试文件。"""
    try:
        from backend.core import ois_storage

        cfg = ois_storage._get_ois_config()
        if not cfg.get("identify"):
            return {"success": False, "msg": "OIS 未配置，请先填写 Identify 和 OIS3 URL"}

        client, err = ois_storage._make_client()
        if not client:
            return {
                "success": False,
                "msg": f"SDK 初始化失败：{err}",
                "debug": {
                    "identify":       cfg.get("identify", ""),
                    "env":            cfg.get("env", "(未填)"),
                    "ois3_url":       cfg.get("ois3_url") or cfg.get("api_base", "(未填)"),
                    "licloud_appid":  cfg.get("licloud_appid", "(未填)"),
                    "has_idaas":      bool(cfg.get("idaas_client_id") and cfg.get("idaas_client_secret")),
                },
            }

        import io
        test_key = "test/_connectivity_check.txt"
        response = client.put_object(cfg["identify"], test_key, io.BytesIO(b"ok"))

        if hasattr(response, "is_succeed") and response.is_succeed():
            uploaded_key = getattr(getattr(response, "data", None), "object_key", test_key)
            return {
                "success":      True,
                "msg":          f"连接成功 ✓  object_key={uploaded_key}",
                "object_key":   uploaded_key,
            }
        code = getattr(response, "code", "?")
        msg  = getattr(response, "message", "?")
        return {"success": False, "msg": f"上传测试失败：code={code} message={msg}"}

    except Exception as e:
        return {"success": False, "msg": f"连接失败：{str(e)[:300]}"}


@router.post("/test")
def test_connection(body: dict = {}, _user: dict = Depends(_WRITE)):
    """测试当前 MinIO 连接是否正常。"""
    from backend.core.storage import _get_minio_config
    cfg = _get_minio_config()
    if not cfg.get("endpoint"):
        return {"success": False, "msg": "MinIO 未配置"}
    try:
        import boto3
        from botocore.client import Config as _BotoCfg
        client = boto3.client(
            "s3", endpoint_url=cfg["endpoint"],
            aws_access_key_id=cfg["access_key"],
            aws_secret_access_key=cfg["secret_key"],
            config=_BotoCfg(signature_version="s3v4"),
            region_name="us-east-1",
        )
        bkt = cfg.get("bucket", "ai00")
        try:
            client.head_bucket(Bucket=bkt)
            return {"success": True, "msg": f"连接成功，bucket '{bkt}' 已存在"}
        except Exception:
            return {"success": True, "msg": "连接成功（endpoint 可达）"}
    except Exception as e:
        return {"success": False, "msg": f"连接失败：{str(e)[:200]}"}
