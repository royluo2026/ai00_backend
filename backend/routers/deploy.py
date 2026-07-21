"""
backend/routers/deploy.py
部署版本管理 API
"""
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from backend.config import get_settings

router = APIRouter(tags=["deploy"], prefix="/api/deploy")

_HISTORY_FILE = Path(__file__).parent.parent.parent / ".deploy-history.json"
_BACKEND_REPO = Path("E:/Projects/ai00/workmanship-backend")
_FRONTEND_REPO = Path("E:/Projects/ai00/workmanship-web")

UTC8 = timezone(__import__('datetime').timedelta(hours=8))


@router.get("", include_in_schema=False)
def deploy_redirect():
    return RedirectResponse("/static/deploy/dashboard.html")


def _load_history() -> dict:
    if not _HISTORY_FILE.exists():
        return {"current": None, "history": []}
    return json.loads(_HISTORY_FILE.read_text(encoding="utf-8"))


def _save_history(data: dict) -> None:
    _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    _HISTORY_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _git(cwd: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(cwd)] + list(args), capture_output=True, text=True,
                       creationflags=subprocess.CREATE_NO_WINDOW if __import__('sys').platform == 'win32' else 0)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return r.stdout.strip()


def _gitea_api(path: str) -> dict:
    import urllib.request
    token = get_settings().gitea_token or ""
    req = urllib.request.Request(
        f"http://pc-pc2l7vve:3003/api/v1{path}",
        headers={"Authorization": f"token {token}"} if token else {}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


@router.get("/current")
def get_current():
    """当前部署版本信息"""
    h = _load_history()
    current = h.get("current")
    if not current:
        return {"current": None, "latest_commit": None}

    try:
        latest = _git(_BACKEND_REPO, "rev-parse", "--short", "HEAD")
    except Exception:
        latest = None

    return {
        "current": current,
        "latest_commit": latest,
        "needs_update": latest != current.get("backend_commit"),
    }


@router.get("/history")
def get_history():
    """部署历史"""
    h = _load_history()
    return {"history": h.get("history", [])[-20:]}


@router.get("/pipeline")
def get_pipeline_status():
    """最新 pipeline 运行状态"""
    try:
        runs = _gitea_api("/repos/devteam/workmanship-backend/actions/runs?limit=5")
        result = []
        for run in (runs or []):
            result.append({
                "id": run.get("id"),
                "status": run.get("status"),
                "conclusion": run.get("conclusion"),
                "head_sha": (run.get("head_sha") or "")[:7],
                "head_branch": run.get("head_branch"),
                "created_at": run.get("created_at"),
            })
        return {"runs": result}
    except Exception as e:
        return {"runs": [], "error": str(e)}


class RollbackBody(BaseModel):
    commit: str


@router.post("/rollback")
def rollback(body: RollbackBody):
    """回滚到指定 commit（force push 到 test 分支触发重部署）"""
    commit = body.commit.strip()
    if not commit:
        raise HTTPException(400, "commit 不能为空")

    history = _load_history()
    target = None
    for entry in history.get("history", []):
        if entry["backend_commit"].startswith(commit):
            target = entry
            break

    if not target:
        raise HTTPException(404, f"未找到 commit {commit} 的部署记录")

    try:
        _git(_BACKEND_REPO, "checkout", "deploy")
        _git(_BACKEND_REPO, "reset", "--hard", target["backend_commit"])
        _git(_BACKEND_REPO, "push", "devteam", "deploy:test", "--force")
    except RuntimeError as e:
        raise HTTPException(500, f"回滚失败: {str(e)[:200]}")

    return {
        "success": True,
        "message": f"已回滚到 {target['backend_commit']}，pipeline 正在部署...",
        "commit": target["backend_commit"],
        "deployed_at": target.get("deployed_at"),
    }
