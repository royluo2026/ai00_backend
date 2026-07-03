"""
backend/routers/auth.py
────────────────────────
飞书 OAuth 登录流程（全部在后端完成，客户端不接触 App Secret）

流程：
  1. GET  /auth/feishu/login-url?state=xxx  → 返回飞书扫码 URL
  2. GET  /auth/feishu/callback?code=&state= → 飞书回调，换 token，签发 JWT
  3. GET  /auth/feishu/poll/{state}          → 客户端轮询，等 JWT 就绪
  4. POST /auth/refresh                      → 刷新 JWT
  5. GET  /auth/me                           → 当前用户信息
"""
import secrets
import threading
import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import HTMLResponse

from backend.services.feishu_service import feishu_service
from backend.services import jwt_service, user_service
from backend.db.connection import get_conn
from backend.routers.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])
_log = logging.getLogger(__name__)


# ── 1. 生成登录 URL ────────────────────────────────────────────────────────────

@router.get("/feishu/login-url")
def get_login_url():
    """
    客户端调用：获取飞书扫码 URL 和 state。
    客户端用 webbrowser.open(url) 打开，然后轮询 /poll/{state}。
    """
    state = secrets.token_urlsafe(24)

    # 写入 auth_pending 表（10分钟有效）
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workmanship_auth_auth_pending (state) VALUES (%s)", (state,)
            )

    url = feishu_service.build_login_url(state)
    return {"login_url": url, "state": state}


# ── 2. 飞书 OAuth 回调 ─────────────────────────────────────────────────────────

@router.get("/feishu/callback")
def feishu_callback(code: str = "", state: str = "", error: str = ""):
    """
    飞书 OAuth 回调（需在飞书开放平台配置此 URL）。
    成功：换 token → 查/建用户 → 签发 JWT → 写入 auth_pending → 返回提示页面。
    失败：写入错误信息 → 返回提示页面。
    """
    if error or not code:
        _write_pending_error(state, error or "no_code")
        return HTMLResponse("<h3>登录失败，请关闭此页面重试</h3>")

    try:
        user_info = feishu_service.exchange_code(code)
        user = user_service.get_or_create(
            open_id=user_info["open_id"],
            name=user_info["name"],
            email=user_info["email"],
            avatar_url=user_info["avatar_url"],
            access_token=user_info.get("access_token", ""),
            refresh_token=user_info.get("refresh_token", ""),
            expires_in=user_info.get("expires_in", 7200),
        )
        # 异步同步部门（不阻塞登录）
        dept_ids = user_info.get("department_ids", [])
        if dept_ids:
            threading.Thread(
                target=_bg_sync_dept,
                args=(user["gid"], dept_ids),
                daemon=True,
            ).start()
        token = jwt_service.sign(
            user_gid=user["gid"],
            system_role=user["system_role"],
            external_subtype=user.get("external_subtype"),
            team_id=user.get("team_id"),
            name=user.get("name", ""),
            email=user.get("email", ""),
            avatar_url=user.get("avatar_url", ""),
        )
        _write_pending_jwt(state, token)
        return HTMLResponse("""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>登录成功</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{
    display:flex;align-items:center;justify-content:center;
    min-height:100vh;
    background:#f5f5f5;
    font-family:system-ui,-apple-system,sans-serif;
  }
  .card{
    text-align:center;
    padding:24px 32px;
  }
  .icon{
    width:40px;height:40px;
    background:#e6f9ee;
    border-radius:50%;
    display:flex;align-items:center;justify-content:center;
    margin:0 auto 14px;
  }
  .icon svg{stroke:#2da55e}
  h2{
    font-size:15px;font-weight:600;
    color:#1a1a1a;
    margin-bottom:6px;
  }
  p{font-size:12px;color:#999}
</style>
</head>
<body>
<div class="card">
  <div class="icon">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  </div>
  <h2>登录成功</h2>
  <p>此页面将自动关闭…</p>
</div>
<script>setTimeout(()=>window.close(),2000)</script>
</body>
</html>""")
    except Exception as e:
        _write_pending_error(state, str(e))
        return HTMLResponse(f"<h3>登录出错：{e}</h3>")


def _write_pending_jwt(state: str, jwt_token: str) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_auth_auth_pending SET jwt=%s WHERE state=%s",
                (jwt_token, state),
            )


def _write_pending_error(state: str, error: str) -> None:
    if not state:
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE workmanship_auth_auth_pending SET error=%s WHERE state=%s",
                (error, state),
            )


# ── 3. 客户端轮询 ──────────────────────────────────────────────────────────────

@router.get("/feishu/poll/{state}")
def poll_login(state: str):
    """
    客户端每 2 秒调用一次，等待飞书回调完成。
    返回：
      {status: "pending"}          → 还没扫码
      {status: "ok", token: "..."}  → 登录成功，JWT 在这
      {status: "error", msg: "..."}  → 登录失败
      {status: "expired"}           → state 已过期
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT jwt, error, expires_at FROM workmanship_auth_auth_pending WHERE state=%s",
                (state,),
            )
            row = cur.fetchone()

    if not row:
        return {"status": "expired"}

    now = datetime.utcnow()
    if row["expires_at"] < now:
        return {"status": "expired"}

    if row["error"]:
        return {"status": "error", "msg": row["error"]}

    if row["jwt"]:
        # 清理已用 pending 记录
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM workmanship_auth_auth_pending WHERE state=%s", (state,))
        return {"status": "ok", "token": row["jwt"]}

    return {"status": "pending"}


# ── 4. 退出登录（JWT 无状态，客户端删除 token 即可）──────────────────────────

@router.post("/logout")
def logout():
    """
    网页版退出登录端点。
    JWT 本身无需服务端失效（客户端删除 localStorage 中的 token 即可），
    此端点仅作 Web polyfill 调用的响应点。
    """
    return {"ok": True}


# ── 5. 刷新 JWT ────────────────────────────────────────────────────────────────

@router.post("/refresh")
def refresh_token(current_user: dict = Depends(get_current_user)):
    """重新签发 JWT（续期）"""
    new_token = jwt_service.sign(
        user_gid=current_user["gid"],
        system_role=current_user["system_role"],
        external_subtype=current_user.get("external_subtype"),
        team_id=current_user.get("team_id"),
    )
    return {"token": new_token}


# ── 5. 当前用户信息 ────────────────────────────────────────────────────────────

@router.get("/me")
def get_me(current_user: dict = Depends(get_current_user)):
    """返回当前登录用户信息（含角色、权限面板列表）"""
    from backend.routers.deps import build_profile
    return build_profile(current_user)


# ── 内部：后台部门同步 ──────────────────────────────────────────────────────────

def _bg_sync_dept(user_gid: str, department_ids: list) -> None:
    """登录后台线程：同步用户部门树，失败静默忽略。"""
    try:
        from backend.services.org_sync_service import sync_user_departments
        sync_user_departments(user_gid, department_ids)
    except Exception:
        _log.warning("_bg_sync_dept: 部门同步失败 user_gid=%s", user_gid, exc_info=True)
