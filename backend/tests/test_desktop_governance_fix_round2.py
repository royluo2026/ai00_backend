"""Actual HTTP and fresh-process regressions for the two round-2 findings."""
import ast
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.tests.test_desktop_app_capability_governance import ROOT, signed_claim, test_jwt_key
from backend.tests.test_desktop_governance_fix_round import USER, assert_desktop
from backend.routers import deps


@pytest.fixture
def agent_client(monkeypatch):
    from plugins.agent.agent_backend.api import compatibility
    from backend.capability_v2.contracts import CapabilityResultV2, CapabilityStatus
    captured = []
    class Gateway:
        catalog_release = "rel_test"
        async def invoke(self, envelope):
            captured.append(envelope)
            return CapabilityResultV2(ok=True, status=CapabilityStatus.COMPLETED,
                capability_id=envelope.capability_id, major_version=1,
                data={"sessions": [], "gid": "audit-1"}, correlation={"request_id": envelope.request_id})
    monkeypatch.setattr(compatibility, "get_default_gateway", Gateway)
    monkeypatch.setattr(deps.user_service, "get_by_gid", lambda _: USER.copy())
    app = FastAPI()
    for module in ("skills_v2", "flows", "ai_chat", "ai_audit"):
        router_module = importlib.import_module(f"plugins.agent.agent_backend.routers.{module}")
        app.include_router(router_module.router)
        if module == "ai_chat":
            monkeypatch.setattr(router_module._pi_proxy, "enabled", lambda: False)
    app.dependency_overrides[deps.get_current_user] = lambda: USER.copy()
    with TestClient(app) as client:
        yield client, captured


@pytest.mark.parametrize("method,route,body", [
    ("GET", "/api/skills", None), ("POST", "/api/skills", {"name": "example", "title": "Example"}),
    ("PUT", "/api/skills/skill-1", {"title": "Changed"}), ("DELETE", "/api/skills/skill-1", None),
    ("GET", "/api/flows", None), ("POST", "/api/flows", {"name": "Example"}),
    ("GET", "/api/flows/capability-manifest", None), ("GET", "/api/flows/runs?flow_gid=flow-1", None),
    ("GET", "/api/flows/runs/run-1", None), ("POST", "/api/flows/runs/run-1/step", {}),
    ("GET", "/api/flows/flow-1", None), ("PUT", "/api/flows/flow-1", {"name": "Changed"}),
    ("DELETE", "/api/flows/flow-1", None), ("POST", "/api/flows/flow-1/run", {"mode": "auto"}),
    ("POST", "/api/flows/gen-script", {"description": "Example"}),
    ("POST", "/api/ai/abort", {"session_gid": "session-1"}), ("GET", "/api/ai/sessions", None),
    ("GET", "/api/ai/sessions/session-1", None), ("DELETE", "/api/ai/sessions/session-1", None),
    ("POST", "/api/ai/sessions/new", {}), ("GET", "/api/ai/tools", None),
    ("GET", "/api/ai/admin-config", None), ("POST", "/api/ai/audit", {"tool_name": "example"}),
    ("GET", "/api/ai/audit-logs", None),
])
def test_interactive_agent_http_keeps_signed_desktop_claim(agent_client, method, route, body):
    client, captured = agent_client
    response = client.request(method, route, json=body, headers={"X-AI00-Token": signed_claim()})
    assert response.status_code == 200, response.text
    assert_desktop(captured[0].identity)


@pytest.mark.parametrize("route,body", [
    ("/api/skills", {"name": "example", "title": "Example"}),
    ("/api/flows", {"name": "Example"}),
    ("/api/ai/sessions/new", {}),
    ("/api/ai/audit", {"tool_name": "example"}),
])
@pytest.mark.parametrize("location", ["body", "payload", "header"])
def test_interactive_agent_rejects_identity_before_payload_normalization(agent_client, route, body, location):
    client, captured = agent_client
    body = dict(body)
    headers = {"X-AI00-Token": signed_claim()}
    if location == "header":
        headers["X-AI00-Consumer-ID"] = "forged"
    elif location == "payload":
        body["payload"] = {"consumer_id": "forged"}
    else:
        body["consumer_id"] = "forged"
    response = client.post(route, json=body, headers=headers)
    assert response.status_code == 400, response.text
    assert response.json()["detail"]["code"] == "consumer_identity_override_forbidden"
    assert captured == []


def test_all_agent_compatibility_callers_supply_authenticated_principal():
    for path in (ROOT / "plugins/agent/agent_backend/routers").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for function in tree.body:
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name) and node.func.id == "invoke_agent_capability"]
            if not calls:
                continue
            assert any(isinstance(node, ast.Name) and node.id == "get_authenticated_principal"
                for node in ast.walk(function.args)), (path.name, function.name)
            assert all(any(k.arg == "principal" for k in call.keywords) for call in calls), (path.name, function.name)


def test_ordinary_generator_cli_refuses_nonisolated_startup():
    output = ROOT / "docs/governance/desktop-app-impact-closure.json"
    original = output.read_bytes()
    result = subprocess.run([sys.executable, "backend/scripts/build_desktop_app_governance.py", "--check"],
        cwd=ROOT, capture_output=True, text=True)
    assert result.returncode != 0, result.stdout
    assert "isolated_bootstrap_required" in result.stderr
    assert output.read_bytes() == original


def test_fresh_ordinary_cli_rejects_mutated_generation_logic(tmp_path):
    script = tmp_path / "backend/scripts/build_desktop_app_governance.py"
    script.parent.mkdir(parents=True)
    source = (ROOT / "backend/scripts/build_desktop_app_governance.py").read_text(encoding="utf-8")
    position = source.rindex('if __name__ == "__main__":')
    source = source[:position] + '\ndef build_impact_closure(*args):\n    return {"human_approved": True}\n\n' + source[position:]
    script.write_text(source, encoding="utf-8")
    output = tmp_path / "docs/governance/desktop-app-impact-closure.json"
    output.parent.mkdir(parents=True)
    output.write_text('{"original": true}', encoding="utf-8")
    result = subprocess.run([sys.executable, str(script), "--write"], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode != 0
    assert "isolated_bootstrap_required" in result.stderr
    assert json.loads(output.read_text(encoding="utf-8")) == {"original": True}


def test_formal_desktop_command_loads_immutable_bootstrap():
    from backend.scripts.desktop_governance_command import isolated_command
    command = isolated_command(sys.executable, "--check")
    assert command[1:4] == ["-I", "-S", "-c"]
    assert "git" in command[4] and "desktop_governance_bootstrap.py" in command[4]


@pytest.fixture
def committed_generator_repo(tmp_path):
    """Commit test implementations in an isolated object view, not this worktree.

    This permits real CLI RED/GREEN before the implementation commit, while
    every runtime input still comes from an actual immutable Git commit.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    def git(*args, data=None):
        return subprocess.check_output(["git", *args], cwd=repo, input=data)
    git("init", "-q")
    common = Path(subprocess.check_output(["git", "rev-parse", "--git-common-dir"], cwd=ROOT, text=True).strip())
    (repo / ".git/objects/info/alternates").write_text((common / "objects").as_posix() + "\n", encoding="utf-8", newline="\n")
    baseline = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    git("read-tree", baseline)
    for name in ("build_desktop_app_governance.py", "desktop_governance_bootstrap.py", "desktop_governance_command.py"):
        relative = f"backend/scripts/{name}"
        blob = git("hash-object", "-w", "--stdin", data=(ROOT / relative).read_bytes().replace(b"\r\n", b"\n")).decode().strip()
        git("update-index", "--add", "--cacheinfo", "100644", blob, relative)
    tree = git("write-tree").decode().strip()
    commit = git("-c", "user.name=Desktop Regression", "-c", "user.email=desktop-test@example.invalid",
        "commit-tree", tree, "-p", baseline, "-m", "Immutable bootstrap regression fixture").decode().strip()
    git("update-ref", "HEAD", commit)
    (repo / "docs/governance").mkdir(parents=True)
    return repo, commit


def test_fresh_supported_cli_ignores_replaced_workspace_code_and_python_startup(committed_generator_repo, tmp_path):
    from backend.scripts.desktop_governance_command import isolated_command
    repo, commit = committed_generator_repo
    output = repo / "docs/governance/desktop-app-impact-closure.json"
    def run(mode, env=None):
        return subprocess.run(isolated_command(sys.executable, mode), cwd=repo,
            capture_output=True, text=True, encoding="utf-8", env=env)
    clean = run("--write")
    assert clean.returncode == 0, clean.stderr
    expected = output.read_bytes()
    assert json.loads(expected)["source_commit"] == commit
    for name in ("build_desktop_app_governance.py", "desktop_governance_bootstrap.py"):
        path = repo / "backend/scripts" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('raise RuntimeError("mutable workspace code executed")\n', encoding="utf-8")
    poison = tmp_path / "poison"
    poison.mkdir()
    marker = tmp_path / "startup-executed"
    (poison / "sitecustomize.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n", encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(poison)}
    written = run("--write", env)
    assert written.returncode == 0, written.stderr
    assert output.read_bytes() == expected
    checked = run("--check", env)
    assert checked.returncode == 0, checked.stderr
    assert not marker.exists(), "untrusted Python startup code ran before isolation"
    document = json.loads(expected)
    document["human_approved"] = True
    output.write_text(json.dumps(document), encoding="utf-8")
    rejected = run("--check", env)
    assert rejected.returncode != 0
    assert "drift" in rejected.stdout.lower()


def test_ordinary_cli_poisoned_startup_is_unsupported_and_never_reports_verified(tmp_path):
    output = ROOT / "docs/governance/desktop-app-impact-closure.json"
    original = output.read_bytes()
    marker = tmp_path / "startup-executed"
    (tmp_path / "sitecustomize.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n", encoding="utf-8")
    result = subprocess.run([sys.executable, "backend/scripts/build_desktop_app_governance.py", "--write"],
        cwd=ROOT, capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(tmp_path)})
    assert marker.exists(), "test must demonstrate startup happens before a normal script can reject it"
    assert result.returncode != 0
    assert "isolated_bootstrap_required" in result.stderr
    assert "verified" not in result.stdout
    assert output.read_bytes() == original


def test_release_gate_requires_controlled_desktop_check_before_success(monkeypatch, tmp_path, capsys):
    from types import SimpleNamespace
    from backend.scripts import check_capability_v2_release_gate as gate
    from backend.scripts.desktop_governance_command import isolated_command
    calls = []
    monkeypatch.setattr(sys, "argv", ["gate", "--root", str(tmp_path), "--web-root", str(tmp_path)])
    monkeypatch.setattr(gate, "evaluate_document", lambda *_: {"passed": True})
    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(gate.subprocess, "run", run)
    assert gate.main() == 1
    assert calls[0][0] == isolated_command(sys.executable, "--check")
    assert calls[0][1]["cwd"] == tmp_path
    assert json.loads(capsys.readouterr().out)["configuration_blockers"][0]["reason_code"] == "desktop_impact_closure_invalid"
