"""
backend/gunicorn.conf.py
────────────────────────
gunicorn 生产配置（uvicorn worker 模式）

用法：
  gunicorn backend.main:app -c backend/gunicorn.conf.py
"""
import multiprocessing
import os

from dotenv import load_dotenv

env_file = os.getenv("ENV_FILE", "").strip()
if env_file:
    load_dotenv(env_file, override=False)

host = os.getenv("HOST", "0.0.0.0")
port = int(os.getenv("PORT", "8080") or "8080")

bind             = f"{host}:{port}"
workers          = multiprocessing.cpu_count() * 2 + 1
worker_class     = "uvicorn.workers.UvicornWorker"
timeout          = 120
graceful_timeout = 10
keepalive        = 5
accesslog        = "logs/access.log"
errorlog         = "logs/error.log"
loglevel         = "info"
preload_app      = True
max_requests     = 1000
max_requests_jitter = 100


def post_fork(server, worker):
    """每个 worker fork 后重建连接池，防止父进程连接被多 worker 共享导致腐败。"""
    from backend.db.connection import reset_pool
    reset_pool()
