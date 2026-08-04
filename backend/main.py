"""
backend/main.py
────────────────
AI00 云端后端服务入口

部署：
  # 开发
  uvicorn backend.main:app --reload --port 8080

  # 生产（建议用 gunicorn + uvicorn worker）
  gunicorn backend.main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8080

  # Docker
  docker build -t ai00-backend . && docker run -p 8080:8080 --env-file .env ai00-backend
"""
import asyncio
import importlib
import logging
import os
import pkgutil
import sys
import time
from pathlib import Path as _Path

# 确保 packages/ 目录在 Python 路径中（供 packages.craft_plugin 等模块 import）
_PACKAGES_DIR = str(_Path(__file__).parent.parent / "packages")
if _PACKAGES_DIR not in sys.path:
    sys.path.insert(0, _PACKAGES_DIR)
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.core.log_setup import setup_logging
from backend.config import get_settings
from backend.db.connection import init_pool

# ── 日志初始化（必须在所有模块 import 之前完成）─────────────────────────────────
setup_logging(os.getenv("LOG_LEVEL", "INFO"))

_log = logging.getLogger(__name__)


_CRITICAL_ROUTE_SPECS: list[tuple[str, str]] = [
    ("GET", "/health"),
    ("GET", "/auth/me"),
    ("GET", "/api/lists"),
    ("GET", "/api/notifications/unread_count"),
    ("GET", "/api/workbench/home"),
    ("GET", "/feishu/calendar/today"),
    ("GET", "/api/tasks"),
    ("GET", "/api/projects"),
    ("GET", "/api/bop/versions"),
]


def _run_route_self_check(app: FastAPI) -> None:
    """启动自检：检查关键路由是否已注册，缺失时在启动日志高亮告警。"""
    # 可通过 ROUTE_SELF_CHECK=0 显式关闭。
    if os.getenv("ROUTE_SELF_CHECK", "1").strip().lower() in ("0", "false", "off", "no"):
        _log.info("⏭️  路由自检已关闭（ROUTE_SELF_CHECK）")
        return

    route_set: set[tuple[str, str]] = set()
    # 使用 app.router.routes 更稳定；不同 FastAPI/Starlette 版本下 route 类型可能不同。
    for _r in getattr(app.router, "routes", []):
        _methods = getattr(_r, "methods", None)
        _path = getattr(_r, "path", None)
        if not _methods or not _path:
            continue
        for _m in _methods:
            route_set.add((str(_m).upper(), str(_path)))

    missing: list[tuple[str, str]] = []
    for _spec in _CRITICAL_ROUTE_SPECS:
        if _spec in route_set:
            _log.info("✅ 路由自检通过: %s %s", _spec[0], _spec[1])
        else:
            missing.append(_spec)

    _log.info(
        "🧭 路由自检摘要: registered=%d critical=%d missing=%d",
        len(route_set),
        len(_CRITICAL_ROUTE_SPECS),
        len(missing),
    )
    if not route_set:
        _log.warning("路由自检未采集到任何可匹配路由，请检查框架版本或自检实现")
        # 无法可靠采集时不输出“关键路由缺失”错误，避免误报噪音。
        return
    if missing:
        for _m, _p in missing:
            _log.error("❌ 关键路由缺失: %s %s", _m, _p)
        _log.error("可能原因：模块导入异常被跳过、插件路由加载失败或运行镜像版本不一致")



@asynccontextmanager
async def lifespan(app: FastAPI):
    init_pool()
    # MinIO 对象存储初始化（未配置则静默跳过，回退本地磁盘）
    from backend.core.storage import init_storage
    init_storage()
    # Application startup is read-only with respect to database schema.
    # Production enables the check; deployment runs migrations with the DDL credential first.
    if os.getenv("AI00_REQUIRE_MIGRATIONS", "0") == "1":
        from backend.db.connection import get_conn
        from backend.db.migration_readiness import assert_migrations_applied
        with get_conn() as conn:
            assert_migrations_applied(conn)
    # 确保附件目录存在
    Path(__file__).parent.joinpath("static", "uploads").mkdir(parents=True, exist_ok=True)
    # System Skill seeds are deployment data migrations, never application-startup writes.
    _run_route_self_check(app)
    yield


app = FastAPI(
    title="AI00 Cloud Backend",
    version="1.0.0",  # ⚠️ 发版时需与 package.json 的 version 字段手动保持同步
    description="AI00 厂商云端服务 — 持有飞书凭证，代理 OAuth 和 API 调用",
    docs_url="/docs",
    lifespan=lifespan,
)


# ── 全局未捕获异常处理 ────────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    _log.error(
        "未捕获异常 %s %s → %s\n%s",
        request.method,
        request.url.path,
        exc,
        traceback.format_exc(),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": f"服务器内部错误: {type(exc).__name__}"},
    )


# ── HTML 文件 no-cache middleware（防止浏览器缓存旧版本）────────────────────
@app.middleware("http")
async def html_no_cache_middleware(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.endswith('.html') or path.endswith('/') or path.endswith('.js') or path.endswith('.css'):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response


# ── 请求访问日志 middleware ───────────────────────────────────────────────────
@app.middleware("http")
async def access_log_middleware(request: Request, call_next):
    import sys as _sys
    _sys.stdout.write(f"[MW] {request.method} {request.url.path}\n")
    _sys.stdout.flush()
    start = time.time()
    req_id = (request.headers.get("x-request-id", "") or "")[:16] or "-"
    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = int((time.time() - start) * 1000)
        _log.error("❌ [%s] %s %s → 500 %dms | %s", req_id, request.method, request.url.path, duration_ms, exc)
        raise
    duration_ms = int((time.time() - start) * 1000)
    level = logging.WARNING if response.status_code >= 400 else logging.DEBUG
    _log.log(level, "[%s] %s %s → %d %dms", req_id, request.method, request.url.path, response.status_code, duration_ms)
    if duration_ms > _SLOW_MS:
        _log.warning("SLOW [%s] %s %s -> %d %dms", req_id, request.method, request.url.path, response.status_code, duration_ms)
    response.headers["X-Request-ID"] = req_id
    return response


# 允许客户端跨域（桌面客户端通过本地 HTTP 调用）
def _resolve_cors_allow_origins() -> list[str]:
    raw = os.getenv("CORS_ALLOW_ORIGINS", "").strip()
    if raw:
        values = [item.strip() for item in raw.split(",") if item.strip()]
        if values:
            return values
    return [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "app://root",
        "null",
    ]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_resolve_cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-New-Token"],
)

# ── 自动注册 Router ───────────────────────────────────────────────────────────
# Phase 5：先用 PluginLoader 加载插件路由，再 auto-scan 核心路由（跳过插件已接管的模块）

from backend.plugin_loader import PluginLoader as _PluginLoader

_plugin_loader = _PluginLoader()
_plugin_loader.discover()

# 收集所有插件声明的 OWNED_MODULES（这些模块由插件管理，不走 auto-scan）
_plugin_owned: set[str] = set()
for _plugin in _plugin_loader._plugins:
    _plugin_id = _plugin.get("plugin_id", "")
    _mod_path = _plugin.get("backend", {}).get("routers_module")
    if not _mod_path:
        continue

    _pkg_dir = _plugin_loader._plugin_backend_dirs.get(_plugin_id) or _plugin_loader._plugin_dirs.get(_plugin_id)
    _pkg_dir_str = str(_pkg_dir) if _pkg_dir else ""
    _injected = False
    if _pkg_dir_str and _pkg_dir_str not in sys.path:
        sys.path.insert(0, _pkg_dir_str)
        _injected = True

    try:
        _mod = importlib.import_module(_mod_path)
        if hasattr(_mod, "OWNED_MODULES"):
            _plugin_owned.update(_mod.OWNED_MODULES)
    except ModuleNotFoundError as _e:
        # 非致命：get_routers() 会再次尝试加载并给出完整错误。
        _log.debug(f"Plugin module 预加载跳过 [{_mod_path}]: {_e}")
    except Exception as _e:
        _log.warning(f"Plugin module 预加载失败 [{_mod_path}]: {_e}")
    finally:
        if _injected and _pkg_dir_str in sys.path:
            sys.path.remove(_pkg_dir_str)

# 加载插件路由
_plugin_routers = _plugin_loader.get_routers()
for _router in _plugin_routers:
    app.include_router(_router)

# auto-scan backend/routers/*.py（跳过插件已接管的模块）
_routers_dir = Path(__file__).parent / "routers"
for _finder, _mod_name, _is_pkg in pkgutil.iter_modules([str(_routers_dir)]):
    if _is_pkg or _mod_name in _plugin_owned:
        continue
    try:
        _mod = importlib.import_module(f"backend.routers.{_mod_name}")
        if hasattr(_mod, "router"):
            app.include_router(_mod.router)
    except Exception as _e:
        _log.warning(f"Router 加载跳过 [backend.routers.{_mod_name}]: {_e}")
_log.info(f"✅ Router 自动注册完成（插件路由: {len(_plugin_routers)} 个，跳过模块: {_plugin_owned}）")

# 静态文件：附件上传目录
_STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR), check_dir=False), name="static")

_start_time = time.time()
_SLOW_MS = 2000  # 慢请求阈值（毫秒）

# ── 网页版：服务 Vite 构建产物 dist/ ──────────────────────────────────────────
_DIST_DIR = Path(__file__).parent.parent / "dist"
if _DIST_DIR.exists():
    # assets/ 子目录（JS/CSS bundle，带内容哈希，可长期缓存）
    _assets_dir = _DIST_DIR / "assets"
    if _assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="dist_assets")

    # web/ 子目录（原始路径结构，页面内相对路径引用）
    _web_dist_dir = _DIST_DIR / "web"
    if _web_dist_dir.exists():
        app.mount("/web", StaticFiles(directory=str(_web_dist_dir), html=True), name="dist_web")

    # packages/ 子目录（插件页面）
    _pkg_dist_dir = _DIST_DIR / "packages"
    if _pkg_dist_dir.exists():
        app.mount("/packages", StaticFiles(directory=str(_pkg_dist_dir)), name="dist_packages")

    # SPA catch-all：把所有非 API 路径都指向主页 HTML
    _SPA_INDEX = _DIST_DIR / "web" / "index.html"

    @app.get("/config", tags=["system"], include_in_schema=False)
    def get_frontend_config():
        """前端获取自身配置（后端 URL、版本号等）。"""
        from backend.config import get_settings as _gs
        s = _gs()
        return {"backendUrl": getattr(s, "public_url", "") or ""}

    @app.get("/{path:path}", include_in_schema=False)
    async def spa_fallback(path: str):
        # 已有路由优先，这里只处理未匹配的路径
        _skip = ("api/", "auth/", "static/", "assets/", "feishu/", "share/",
                 "bop/", "config", "health", "docs", "redoc", "openapi.json")
        if any(path.startswith(s) for s in _skip):
            raise HTTPException(status_code=404, detail="Not found")
        if _SPA_INDEX.exists():
            return FileResponse(str(_SPA_INDEX))
        raise HTTPException(status_code=404, detail="Frontend not built. Run: npm run build:web")


# ── 角色同步中间件 ─────────────────────────────────────────────────────────────
# 每次已认证请求完成后，比较 JWT 内的 system_role 与 DB 中的值。
# 若不一致（超管刚改了该用户角色），则重新签发 JWT 并附在 X-New-Token 响应头。
# Electron 主进程拦截此头并自动更新客户端 token，实现近实时权限刷新。

@app.middleware("http")
async def role_sync_middleware(request: Request, call_next):
    response = await call_next(request)

    token = request.headers.get("x-ai00-token") or request.headers.get("X-AI00-Token")
    if not token:
        return response

    try:
        from backend.services import jwt_service, user_service
        payload  = jwt_service.decode_unverified(token)
        jwt_role = payload.get("system_role")
        user_gid = payload.get("sub")
        if not user_gid or not jwt_role:
            return response

        user = await asyncio.get_event_loop().run_in_executor(
            None, user_service.get_by_gid, user_gid
        )
        if user and user["is_active"] and user["system_role"] != jwt_role:
            new_token = jwt_service.sign(
                user_gid=user["gid"],
                system_role=user["system_role"],
                org_role=user.get("org_role"),
                external_subtype=user.get("external_subtype"),
                team_id=user.get("team_id"),
                name=user.get("name", ""),
                email=user.get("email", ""),
                avatar_url=user.get("avatar_url", ""),
            )
            response.headers["X-New-Token"] = new_token
    except Exception:
        pass  # 不因刷新失败而影响正常响应

    return response
