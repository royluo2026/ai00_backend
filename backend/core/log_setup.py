"""
backend/core/log_setup.py
──────────────────────────
集中式日志配置。

功能：
  - 根 logger 统一设置 level / 格式 / handler
  - StreamHandler → stdout（nssm 生产环境捕获到文件）
  - InMemoryHandler → 内存环形缓冲区（最近 500 条），
    供 GET /admin/debug-logs 端点实时返回给前端 LogPanel
  - 日志级别通过环境变量 LOG_LEVEL 控制（默认 INFO）

用法：
  # 在 backend/main.py 最顶层（FastAPI app 创建前）调用一次
  from backend.core.log_setup import setup_logging
  setup_logging()
"""
import logging
import sys
from collections import deque

_FMT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


class _InMemoryHandler(logging.Handler):
    """将日志行写入内存环形缓冲区，供 REST 端点读取。"""

    def __init__(self, capacity: int = 500) -> None:
        super().__init__()
        self._buf: deque[str] = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._buf.append(self.format(record))
        except Exception:
            self.handleError(record)

    def get_lines(self, n: int = 200) -> list[str]:
        lines = list(self._buf)
        return lines[-n:] if n < len(lines) else lines


_mem_handler = _InMemoryHandler(capacity=500)
_configured = False


def setup_logging(level_str: str = "INFO") -> None:
    """配置根 logger。多次调用安全（幂等）。"""
    global _configured
    if _configured:
        return
    _configured = True

    level = getattr(logging, level_str.upper(), logging.INFO)
    formatter = logging.Formatter(_FMT, datefmt=_DATE_FMT)

    # stdout handler（nssm 在生产中自动捕获到 backend.log）
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(formatter)

    # 内存 handler（供 /admin/debug-logs 端点）
    _mem_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    # 避免重复添加 StreamHandler（如 uvicorn --reload 多次 import）
    if not any(
        isinstance(h, logging.StreamHandler)
        and not isinstance(h, logging.FileHandler)
        for h in root.handlers
    ):
        root.addHandler(sh)
    root.addHandler(_mem_handler)

    # uvicorn 自带 access log 已被我们的 middleware 替代，关闭其传播避免重复
    logging.getLogger("uvicorn.access").propagate = False


def get_recent_logs(n: int = 200) -> list[str]:
    """返回最近 n 条日志行（供 /admin/debug-logs 端点调用）。"""
    return _mem_handler.get_lines(n)
