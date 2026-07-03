"""
backend/routers/share_page.py
──────────────────────────────
提供 Web 分享页入口，由 FastAPI 直接 serve HTML 文件。
"""
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(tags=["share"])
_WEB_DIR = Path(__file__).parent.parent.parent / "web"


@router.get("/share/issues")
def share_issues_page():
    return FileResponse(_WEB_DIR / "share" / "issues.html")
