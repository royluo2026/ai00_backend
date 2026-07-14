"""
backend/routers/admin.py
──────────────────────────
系统配置管理 API（仅 super_admin）

system_config 表：热重载 Feishu 凭证、功能开关等。
env 变量是启动默认值；super_admin 通过此 API 写入 PG 后生效，
无需重启（热重载通过清除 lru_cache 实现）。

端点：
  GET  /admin/config         → 获取所有配置条目
  GET  /admin/config/{key}   → 获取单条
  PUT  /admin/config/{key}   → 新建或更新（热重载）
  DELETE /admin/config/{key} → 删除（回退到 env 默认）
  POST /admin/config/reload  → 强制清除 settings 缓存
  POST /admin/server-restart → 重启后端进程（NSSM 服务自动重拉）
"""
import asyncio
import json
import os
import re
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import pymysql
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from backend.db.connection import get_conn
from backend.config import get_settings
from backend.routers.deps import require_role, get_current_user_claims_only

router = APIRouter(prefix="/admin", tags=["admin"])

_SUPER_ONLY = require_role("super_admin")


def _require_super_claims(current_user: dict = Depends(get_current_user_claims_only)):
    user_role = current_user.get("org_role") or current_user.get("system_role", "external")
    if user_role != "super_admin" and current_user.get("system_role") != "super_admin":
        raise HTTPException(status_code=403, detail="权限不足")
    return current_user

# 允许通过 API 写入的 key 白名单（防止任意写入敏感字段）
_WRITABLE_KEYS = {
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
    "FEISHU_REDIRECT_URI",
    "FEATURE_CLOUD_SYNC",
    "FEATURE_AI_ASSIST",
    "FEATURE_COLLAB",
    "MAX_TEAMS",
    "dev.bug_tracker",
    "feature_flags",        # 功能开关配置
}

# 允许超管写入 capabilities/lists 的 note/status 字段（活文档）
_WRITABLE_PATTERNS = [
    re.compile(r'^capabilities\.[a-z_]+\.(note|status)$'),
    re.compile(r'^lists\.[a-z_]+\.(note|status)$'),
]


def _is_writable(key: str) -> bool:
    if key in _WRITABLE_KEYS:
        return True
    return any(p.match(key) for p in _WRITABLE_PATTERNS)


class ConfigBody(BaseModel):
    value: str
    description: Optional[str] = ""


class CloudDbConfigBody(BaseModel):
    host: str
    port: int
    user: str
    password: str = ""
    collab_db: str
    public_db: str


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


def _cloud_db_url_from_payload(body: CloudDbConfigBody) -> str:
    user = quote(body.user, safe='')
    password = quote(body.password, safe='')
    db_name = quote(body.collab_db, safe='')
    return f"mysql://{user}:{password}@{body.host}:{body.port}/{db_name}"


def _cloud_db_config_from_system_json() -> dict:
    raw = _load_system_json()
    return raw.get('cloud_db_config') or raw.get('CLOUD_DB_CONFIG') or {}


@router.get("/cloud-db-config")
def get_cloud_db_config(_=Depends(_require_super_claims)):
    cfg = _cloud_db_config_from_system_json()
    return {
        "success": True,
        "data": {
            "host": cfg.get("host", ""),
            "port": cfg.get("port", 2883),
            "user": cfg.get("user", ""),
            "password_configured": bool(cfg.get("password")),
            "collab_db": cfg.get("collab_db", ""),
            "public_db": cfg.get("public_db", ""),
        },
    }


@router.post("/cloud-db-config")
def save_cloud_db_config(body: CloudDbConfigBody, current_user=Depends(_require_super_claims)):
    print(f"[cloud-db-config] save hit role={current_user.get('org_role')} gid={current_user.get('gid')}", flush=True)
    print(f"[cloud-db-config] save payload host={body.host!r} port={body.port!r} user={body.user!r} collab_db={body.collab_db!r} public_db={body.public_db!r} pwd_len={len(body.password or '')}", flush=True)
    if not body.host.strip() or not body.user.strip() or not body.collab_db.strip():
        raise HTTPException(status_code=400, detail="host、user、collab_db 不能为空")

    raw = _load_system_json()
    existing = raw.get('cloud_db_config') or raw.get('CLOUD_DB_CONFIG') or {}
    password = body.password if body.password.strip() else existing.get('password', '')
    cfg = {
        "host": body.host.strip(),
        "port": int(body.port or 2883),
        "user": body.user.strip(),
        "password": password,
        "collab_db": body.collab_db.strip(),
        "public_db": body.public_db.strip() or body.collab_db.strip(),
        "users_db_url": _cloud_db_url_from_payload(
            CloudDbConfigBody(
                host=body.host.strip(),
                port=int(body.port or 2883),
                user=body.user.strip(),
                password=password,
                collab_db=body.collab_db.strip(),
                public_db=body.public_db.strip() or body.collab_db.strip(),
            )
        ),
    }
    raw['cloud_db_config'] = cfg
    path = _system_json_path()
    print(f"[cloud-db-config] writing file path={path}", flush=True)
    try:
        _save_system_json(raw)
        print(f"[cloud-db-config] write ok keys={list(raw.keys())}", flush=True)
    except Exception as e:
        import traceback
        print(f"[cloud-db-config] write failed: {e}\n{traceback.format_exc()}", flush=True)
        raise
    return {"success": True, "msg": "云端数据库配置已保存"}


@router.post("/cloud-db-config/test")
def test_cloud_db_config(body: CloudDbConfigBody, _=Depends(_require_super_claims)):
    if not body.host.strip() or not body.user.strip() or not body.collab_db.strip():
        raise HTTPException(status_code=400, detail="host、user、collab_db 不能为空")
    try:
        conn = pymysql.connect(
            host=body.host.strip(),
            port=int(body.port or 2883),
            user=body.user.strip(),
            password=body.password,
            database=body.collab_db.strip(),
            charset='utf8mb4',
            connect_timeout=8,
            read_timeout=8,
            write_timeout=8,
            cursorclass=pymysql.cursors.DictCursor,
        )
        with conn.cursor() as cur:
            cur.execute('SELECT 1 AS ok')
            cur.fetchone()
        conn.close()
        return {"success": True, "msg": "MySQL 连接成功"}
    except Exception as e:
        return {"success": False, "msg": str(e)}


# ── 读取 ──────────────────────────────────────────────────────────────────────

@router.get("/config")
def list_config(_=Depends(_SUPER_ONLY)):
    """获取所有 system_config 条目（不含 App Secret 明文）"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT `key`, `value`, description, updated_at FROM workmanship_app_system_config ORDER BY `key`")
            rows = [dict(r) for r in cur.fetchall()]

    # 脱敏：以 SECRET 结尾的 key 只返回是否已配置
    for row in rows:
        if "SECRET" in row["key"].upper():
            row["value"] = "●●●●" if row["value"] else ""
    return {"success": True, "data": rows}


@router.get("/config/{key}")
def get_config(key: str, _=Depends(_SUPER_ONLY)):
    """获取单条配置"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT `key`, `value`, description, updated_at FROM workmanship_app_system_config WHERE `key`=%s", (key,))
            row = cur.fetchone()

    if not row:
        # 回退：尝试从当前 Settings 对象读 env 默认值
        s = get_settings()
        env_val = getattr(s, key.lower(), None)
        return {
            "success":    True,
            "data":       {"key": key, "value": env_val, "source": "env"},
        }

    data = dict(row)
    if "SECRET" in key.upper():
        data["value"] = "●●●●" if data["value"] else ""
    data["source"] = "db"
    return {"success": True, "data": data}


# ── 写入 / 更新 ───────────────────────────────────────────────────────────────

@router.put("/config/{key}")
def set_config(key: str, body: ConfigBody, _=Depends(_SUPER_ONLY)):
    """新建或更新一条配置，并热重载 settings 缓存"""
    if not _is_writable(key):
        raise HTTPException(status_code=400, detail=f"key '{key}' 不在可写白名单中")
    # note/status 字段（活文档）允许空值；其他字段不允许
    if not body.value.strip() and key in _WRITABLE_KEYS:
        raise HTTPException(status_code=400, detail="value 不能为空")
    write_value = body.value if body.value.strip() else ' '

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO workmanship_app_system_config (`key`, `value`, description, updated_at)
                   VALUES (%s, %s, %s, NOW())
                   ON DUPLICATE KEY UPDATE
                     `value`=%s, description=COALESCE(NULLIF(%s,''), description),
                     updated_at=NOW()""",
                (key, write_value, body.description,
                 write_value, body.description),
            )

    # 热重载：清除 lru_cache，下次 get_settings() 重新从 env + DB 读取
    get_settings.cache_clear()
    return {"success": True, "msg": f"配置 {key} 已更新，settings 缓存已清除"}


@router.delete("/config/{key}")
def delete_config(key: str, _=Depends(_SUPER_ONLY)):
    """删除一条配置，恢复为 env 默认值"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT `key` FROM workmanship_app_system_config WHERE `key`=%s", (key,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"配置 {key} 不存在")
            cur.execute("DELETE FROM workmanship_app_system_config WHERE `key`=%s", (key,))

    get_settings.cache_clear()
    return {"success": True, "msg": f"配置 {key} 已删除，已回退到 env 默认值"}


# ── 强制热重载 ────────────────────────────────────────────────────────────────

@router.post("/config/reload")
def force_reload(_=Depends(_SUPER_ONLY)):
    """强制清除 settings 缓存（用于手动刷新 env 变更）"""
    get_settings.cache_clear()
    # 预热：触发一次重新加载
    try:
        get_settings()
        return {"success": True, "msg": "settings 缓存已重载"}
    except Exception as e:
        return {"success": False, "msg": str(e)}


# ── 实时调试日志 ──────────────────────────────────────────────────────────────

@router.get("/debug-logs")
def get_debug_logs(limit: int = 200, _=Depends(_SUPER_ONLY)):
    """
    返回最近 N 条后端日志行（来自内存缓冲区）。
    前端 LogPanel 通过此端点实时查看服务器日志，无需 SSH。
    limit 最大 500，超出时截断为 500。
    """
    from backend.core.log_setup import get_recent_logs
    n = min(max(1, limit), 500)
    return {"success": True, "data": get_recent_logs(n)}


# ── 后端进程重启 ──────────────────────────────────────────────────────────────

@router.post("/server-restart")
async def server_restart(
    background_tasks: BackgroundTasks,
    secret: str = "",
    _: dict = Depends(lambda: None),  # placeholder
):
    """
    重启后端进程。支持两种鉴权方式（满足其一即可）：
      1. Header X-AI00-Token（super_admin JWT）
      2. Query ?secret=<RESTART_SECRET>（env 变量，无需登录）
    进程以 os._exit(0) 退出，NSSM 检测到退出后自动重拉。
    """
    # 方式1：env secret
    env_secret = os.getenv("RESTART_SECRET", "")
    authed = env_secret and secret == env_secret
    # 如果没有匹配 secret，交给 JWT 鉴权（由 Depends 控制）
    if not authed:
        raise HTTPException(status_code=403, detail="需要提供有效的 secret 或 super_admin token")

    async def _do_exit():
        await asyncio.sleep(1)
        os._exit(0)

    background_tasks.add_task(_do_exit)
    return {"success": True, "msg": "后端将在 1 秒后重启，请等待约 5 秒后刷新页面"}


# ── 插件注册表（网页版用，无需 auth）────────────────────────────────────────

@router.get("/plugin-registry")
def get_plugin_registry():
    """返回所有已安装插件的前端注册表（tab 定义 + nav 项），供网页版初始化。"""
    from backend.main import _plugin_loader
    return _plugin_loader.get_web_registry()
async def server_restart_admin(background_tasks: BackgroundTasks, _=Depends(_SUPER_ONLY)):
    """重启后端进程（需 super_admin JWT）。"""
    async def _do_exit():
        await asyncio.sleep(1)
        os._exit(0)

    background_tasks.add_task(_do_exit)
    return {"success": True, "msg": "后端将在 1 秒后重启，请等待约 5 秒后刷新页面"}
