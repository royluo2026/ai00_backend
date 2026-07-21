"""
deploy_dashboard_server.py
独立部署面板服务 — 不依赖主服务，重启不影响面板
端口: 8090
"""
import json
import subprocess
import sys
import os
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

HERE = Path(__file__).parent
HISTORY_FILE = Path("E:/projects/ai00-v2/.deploy-history.json")
BACKEND_REPO = Path("E:/Projects/ai00/workmanship-backend")
GITEA_TOKEN = os.getenv("GITEA_TOKEN", "ece8d92157140c498cfb1b869ac16614e07bfd3e")
UTC8 = timezone(timedelta(hours=8))
PORT = int(os.getenv("DASHBOARD_PORT", "8090"))


def _load_history():
    if not HISTORY_FILE.exists():
        return {"current": None, "history": []}
    return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))


def _git(cwd, *args):
    r = subprocess.run(["git", "-C", str(cwd)] + list(args),
                       capture_output=True, text=True,
                       creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                       env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:200])
    return r.stdout.strip()


def _gitea_api(path):
    import urllib.request
    req = urllib.request.Request(
        f"http://pc-pc2l7vve:3003/api/v1{path}",
        headers={"Authorization": f"token {GITEA_TOKEN}"} if GITEA_TOKEN else {}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        print(f"[{datetime.now(UTC8).strftime('%H:%M:%S')}] {args[0]}", flush=True)

    def _json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, content, code=200):
        body = content.encode("utf-8") if isinstance(content, str) else content
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            if self.path in ("/", "/index.html"):
                html_file = HERE / "deploy_dashboard.html"
                self._html(html_file.read_text(encoding="utf-8") if html_file.exists() else "<h1>Not found</h1>")
            elif self.path == "/api/current":
                self._json(self._get_current())
            elif self.path == "/api/history":
                h = _load_history()
                self._json({"history": h.get("history", [])[-20:]})
            elif self.path == "/api/pipeline":
                self._json(self._get_pipeline())
            else:
                self._json({"error": "not found"}, 404)
        except Exception as e:
            self._json({"error": str(e)[:200]}, 500)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            if self.path == "/api/rollback":
                self._json(self._do_rollback(body.get("commit", "")))
            else:
                self._json({"error": "not found"}, 404)
        except Exception as e:
            self._json({"error": str(e)[:200]}, 500)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _get_current(self):
        h = _load_history()
        current = h.get("current")
        latest = None
        try:
            latest = _git(BACKEND_REPO, "rev-parse", "--short", "HEAD")
        except Exception:
            pass
        return {
            "current": current,
            "latest_commit": latest,
            "needs_update": bool(latest and current and latest != current.get("backend_commit")),
        }

    def _get_pipeline(self):
        try:
            runs = _gitea_api("/repos/devteam/workmanship-backend/actions/runs?limit=5")
            return {"runs": [{
                "id": r.get("id"),
                "status": r.get("status"),
                "conclusion": r.get("conclusion"),
                "head_sha": (r.get("head_sha") or "")[:7],
                "head_branch": r.get("head_branch"),
                "created_at": r.get("created_at"),
            } for r in (runs or [])]}
        except Exception as e:
            return {"runs": [], "error": str(e)[:200]}

    def _do_rollback(self, commit):
        if not commit.strip():
            return {"success": False, "message": "commit is required"}
        commit = commit.strip()
        h = _load_history()
        target = None
        for entry in h.get("history", []):
            if entry["backend_commit"].startswith(commit):
                target = entry
                break
        if not target:
            return {"success": False, "message": f"commit {commit} not found in history"}
        try:
            _git(BACKEND_REPO, "checkout", "deploy")
            _git(BACKEND_REPO, "reset", "--hard", target["backend_commit"])
            _git(BACKEND_REPO, "push", "devteam", "deploy:test", "--force")
        except RuntimeError as e:
            return {"success": False, "message": str(e)[:200]}
        return {
            "success": True,
            "message": f"Rolled back to {target['backend_commit']}, pipeline deploying...",
            "commit": target["backend_commit"],
        }


def main():
    print(f"Deploy Dashboard starting on port {PORT}...", flush=True)
    srv = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Dashboard: http://pc-pc2l7vve:{PORT}/", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
