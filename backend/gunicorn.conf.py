"""
backend/gunicorn.conf.py
────────────────────────
gunicorn 生产配置（uvicorn worker 模式）

用法：
  gunicorn backend.main:app -c backend/gunicorn.conf.py
"""
import os

from dotenv import load_dotenv

env_file = os.getenv("ENV_FILE", "").strip()
if env_file:
    load_dotenv(env_file, override=True)


def _positive_env(name: str, *, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value

host = os.getenv("HOST", "0.0.0.0")
port = int(os.getenv("PORT", "8080") or "8080")

bind             = f"{host}:{port}"
workers          = _positive_env("AI00_WEB_WORKERS", default=1)
worker_class     = "uvicorn.workers.UvicornWorker"
timeout          = 120
graceful_timeout = 10
keepalive        = 5
accesslog        = "logs/access.log"
errorlog         = "logs/error.log"
loglevel         = "info"
preload_app      = True
max_requests     = _positive_env("AI00_MAX_REQUESTS", default=1000)
max_requests_jitter = _positive_env("AI00_MAX_REQUESTS_JITTER", default=100)


def post_fork(server, worker):
    """每个 worker fork 后重建连接池，防止父进程连接被多 worker 共享导致腐败。"""
    from backend.db.connection import reset_pool
    reset_pool()
