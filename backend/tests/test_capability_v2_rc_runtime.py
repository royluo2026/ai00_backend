from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.scripts.run_capability_v2_rc_runtime import (
    HttpResult,
    RuntimeEvidenceError,
    RuntimeProbeResult,
    build_runtime_evidence,
    build_provider_evidence,
    collect_mandatory_outcomes,
    load_probe_config,
    run_component_probes,
    run_provider_probes,
)


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "backend/tests/acceptance/fixtures/case-manifest.json"


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _outcomes() -> dict[str, str]:
    return {
        node: "passed"
        for cases in _manifest()["capabilities"].values()
        for node in cases.values()
    }


def _probes() -> tuple[RuntimeProbeResult, ...]:
    return (
        RuntimeProbeResult(
            component="backend_gateway",
            status="passed",
            endpoint="https://backend.rc.test:8443/health?token=hidden",
            checks=("health", "catalog", "invoke", "audit"),
            duration_ms=10,
            correlation_ids=("backend-1",),
        ),
        RuntimeProbeResult(
            component="plugin",
            status="passed",
            endpoint="https://backend.rc.test/api/v1/plugins",
            checks=("discover", "permitted", "denied", "approval"),
            duration_ms=11,
            correlation_ids=("plugin-1",),
        ),
        RuntimeProbeResult(
            component="agent",
            status="passed",
            endpoint="https://agent.rc.test/health",
            checks=("health", "tools", "permitted", "denied", "approval"),
            duration_ms=12,
            correlation_ids=("agent-1",),
        ),
        RuntimeProbeResult(
            component="mcp",
            status="passed",
            endpoint="https://mcp.rc.test/mcp",
            checks=("initialize", "tools", "permitted", "denied"),
            duration_ms=13,
            correlation_ids=("mcp-1",),
        ),
        RuntimeProbeResult(
            component="local_runtime",
            status="passed",
            endpoint="outbound://backend-device-gateway",
            checks=("dotnet-tests", "lease", "heartbeat"),
            duration_ms=14,
            correlation_ids=("local-1",),
        ),
    )


def test_build_runtime_evidence_maps_exact_1869_current_run_outcomes():
    manifest = _manifest()
    evidence = build_runtime_evidence(
        root=ROOT,
        environment_id="capability-v2-test-42",
        run_id="gitea:42:1",
        git_commit="a" * 40,
        outcomes=_outcomes(),
        probes=_probes(),
        outcome_sha256="sha256:" + "b" * 64,
    )

    assert sum(len(cases) for cases in evidence["capabilities"].values()) == 1869
    assert set(evidence["capabilities"]) == set(manifest["capabilities"])
    assert all(
        result == "passed"
        for cases in evidence["capabilities"].values()
        for result in cases.values()
    )
    assert evidence["environment_id"] == "capability-v2-test-42"
    assert evidence["run_id"] == "gitea:42:1"
    assert evidence["git_commit"] == "a" * 40
    assert evidence["component_results"] == {
        "backend_gateway": "passed",
        "plugin": "passed",
        "agent": "passed",
        "mcp": "passed",
        "local_runtime": "passed",
    }
    assert evidence["probe_provenance"]["outcome_sha256"] == "sha256:" + "b" * 64
    assert (
        evidence["probe_provenance"]["components"]["backend_gateway"]["endpoint"]
        == "https://backend.rc.test:8443"
    )


@pytest.mark.parametrize("outcome", ["failed", "skipped", "xfailed", "xpassed"])
def test_build_runtime_evidence_rejects_any_non_passed_mandatory_node(outcome):
    outcomes = _outcomes()
    node = next(iter(outcomes))
    outcomes[node] = outcome

    with pytest.raises(RuntimeEvidenceError, match="mandatory_outcomes_not_passed"):
        build_runtime_evidence(
            root=ROOT,
            environment_id="capability-v2-test-42",
            run_id="gitea:42:1",
            git_commit="a" * 40,
            outcomes=outcomes,
            probes=_probes(),
            outcome_sha256="sha256:" + "b" * 64,
        )


@pytest.mark.parametrize("change", ["missing", "extra"])
def test_build_runtime_evidence_rejects_inexact_node_set(change):
    outcomes = _outcomes()
    if change == "missing":
        outcomes.pop(next(iter(outcomes)))
    else:
        outcomes["backend/tests/acceptance/test_fake.py::test_extra"] = "passed"

    with pytest.raises(RuntimeEvidenceError, match="mandatory_outcome_set_mismatch"):
        build_runtime_evidence(
            root=ROOT,
            environment_id="capability-v2-test-42",
            run_id="gitea:42:1",
            git_commit="a" * 40,
            outcomes=outcomes,
            probes=_probes(),
            outcome_sha256="sha256:" + "b" * 64,
        )


def test_build_runtime_evidence_rejects_missing_or_failed_component_probe():
    missing = _probes()[:-1]
    with pytest.raises(RuntimeEvidenceError, match="component_probe_set_mismatch"):
        build_runtime_evidence(
            root=ROOT,
            environment_id="capability-v2-test-42",
            run_id="gitea:42:1",
            git_commit="a" * 40,
            outcomes=_outcomes(),
            probes=missing,
            outcome_sha256="sha256:" + "b" * 64,
        )

    failed = tuple(
        probe
        if probe.component != "agent"
        else RuntimeProbeResult(
            component="agent",
            status="failed",
            endpoint=probe.endpoint,
            checks=probe.checks,
            duration_ms=probe.duration_ms,
            correlation_ids=probe.correlation_ids,
        )
        for probe in _probes()
    )
    with pytest.raises(RuntimeEvidenceError, match="component_probe_failed:agent"):
        build_runtime_evidence(
            root=ROOT,
            environment_id="capability-v2-test-42",
            run_id="gitea:42:1",
            git_commit="a" * 40,
            outcomes=_outcomes(),
            probes=failed,
            outcome_sha256="sha256:" + "b" * 64,
        )


@pytest.mark.parametrize(
    ("environment_id", "run_id", "git_commit", "message"),
    [
        ("production", "gitea:42:1", "a" * 40, "environment_not_test_or_rc"),
        ("capability-v2-test-42", "", "a" * 40, "run_id_invalid"),
        ("capability-v2-test-42", "gitea:42:1", "short", "git_commit_invalid"),
    ],
)
def test_build_runtime_evidence_rejects_invalid_run_bindings(
    environment_id, run_id, git_commit, message
):
    with pytest.raises(RuntimeEvidenceError, match=message):
        build_runtime_evidence(
            root=ROOT,
            environment_id=environment_id,
            run_id=run_id,
            git_commit=git_commit,
            outcomes=_outcomes(),
            probes=_probes(),
            outcome_sha256="sha256:" + "b" * 64,
        )


def test_collect_mandatory_outcomes_runs_acceptance_once_and_hashes_raw_result(
    tmp_path
):
    calls = []
    outcomes = _outcomes()

    def run(command, **kwargs):
        calls.append((command, kwargs))
        result_path = Path(kwargs["env"]["AI00_ACCEPTANCE_RESULT_PATH"])
        result_path.write_text(
            json.dumps({"exit_status": 0, "outcomes": outcomes}, sort_keys=True),
            encoding="utf-8",
        )
        return SimpleNamespace(
            returncode=0,
            stdout="1848 passed in 1.00s",
            stderr="",
        )

    collected = collect_mandatory_outcomes(
        root=ROOT,
        temp_root=tmp_path,
        run=run,
    )

    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command[:3] == [str(Path(__import__("sys").executable)), "-m", "pytest"]
    assert "backend/tests/acceptance" in command
    assert "backend.tests.acceptance.outcome_plugin" in command
    assert kwargs["cwd"] == ROOT
    assert kwargs["check"] is False
    assert collected.outcomes == outcomes
    assert collected.outcome_sha256.startswith("sha256:")
    assert collected.summary == "1848 passed in 1.00s"


@pytest.mark.parametrize(
    ("returncode", "write_result", "message"),
    [
        (1, True, "acceptance_pytest_failed"),
        (0, False, "acceptance_outcome_missing"),
    ],
)
def test_collect_mandatory_outcomes_fails_closed(
    tmp_path, returncode, write_result, message
):
    def run(_command, **kwargs):
        if write_result:
            Path(kwargs["env"]["AI00_ACCEPTANCE_RESULT_PATH"]).write_text(
                json.dumps({"exit_status": returncode, "outcomes": _outcomes()}),
                encoding="utf-8",
            )
        return SimpleNamespace(returncode=returncode, stdout="", stderr="secret")

    with pytest.raises(RuntimeEvidenceError, match=message):
        collect_mandatory_outcomes(root=ROOT, temp_root=tmp_path, run=run)


def test_collect_mandatory_outcomes_rejects_duplicate_json_keys(tmp_path):
    def run(_command, **kwargs):
        Path(kwargs["env"]["AI00_ACCEPTANCE_RESULT_PATH"]).write_text(
            '{"exit_status":0,"outcomes":{"same":"passed","same":"passed"}}',
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stdout="passed", stderr="")

    with pytest.raises(RuntimeEvidenceError, match="acceptance_outcome_duplicate"):
        collect_mandatory_outcomes(root=ROOT, temp_root=tmp_path, run=run)


REQUIRED_CHECKS = {
    "backend_gateway": ["health", "catalog", "unauthenticated_denial", "permitted_invoke", "audit"],
    "plugin": ["catalog", "permitted", "denied", "approval"],
    "agent": ["health", "tools", "permitted", "denied", "approval"],
    "mcp": ["initialize", "tools", "permitted", "denied"],
    "local_runtime": ["heartbeat", "lease"],
}


def _probe_config() -> dict:
    components = {}
    for component, names in REQUIRED_CHECKS.items():
        target = "backend" if component in {"backend_gateway", "plugin", "local_runtime"} else component
        prefix = (
            "/api/v1/plugin-marketplace/probe"
            if component == "plugin"
            else "/api/v1/device-runtime/probe"
            if component == "local_runtime"
            else f"/probe/{component}"
        )
        components[component] = [
            {
                "name": name,
                "target": target,
                "method": "GET" if name in {"health", "catalog", "tools"} else "POST",
                "path": f"{prefix}/{name}",
                "headers_env": {} if name == "unauthenticated_denial" else {"Authorization": "AI00_RC_USER_TOKEN"},
                "body": {},
                "expect": (
                    "denied" if name in {"unauthenticated_denial", "denied"}
                    else "approval" if name == "approval"
                    else "catalog" if name in {"catalog", "tools"}
                    else "health" if name == "health"
                    else "success"
                ),
            }
            for name in names
        ]
    domains = json.loads(
        (ROOT / "backend/capability_v2/official_domains.json").read_text(encoding="utf-8")
    )["domains"]
    catalog = json.loads(
        (ROOT / "docs/capabilities/catalog.v2.json").read_text(encoding="utf-8")
    )["capabilities"]
    providers = {}
    for domain in domains:
        descriptor = next(item for item in catalog if item["owner_domain"] in domain["allowed_owners"])
        providers[domain["domain_id"]] = {
            "capability_id": descriptor["id"],
            "major_version": descriptor["major_version"],
            "payload": descriptor["minimal_input_example"],
        }
    return {
        "schema_version": 1,
        "gateway_headers_env": {"Authorization": "AI00_RC_USER_TOKEN"},
        "components": components,
        "providers": providers,
    }


def test_load_probe_config_requires_exact_components_and_manifest_owned_provider(tmp_path):
    path = tmp_path / "probe.json"
    path.write_text(json.dumps(_probe_config()), encoding="utf-8")
    loaded = load_probe_config(ROOT, path)
    assert set(loaded["components"]) == set(REQUIRED_CHECKS)
    assert len(loaded["providers"]) == 11

    document = _probe_config()
    document["providers"].pop(next(iter(document["providers"])))
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(RuntimeEvidenceError, match="provider_probe_set_mismatch"):
        load_probe_config(ROOT, path)


def test_component_probes_execute_real_http_steps_and_dotnet_solution():
    calls = []

    def request(method, url, headers, body, timeout):
        calls.append((method, url, headers, body, timeout))
        name = url.rsplit("/", 1)[-1]
        if name in {"unauthenticated_denial", "denied"}:
            return HttpResult(403, {"detail": {"code": "denied"}}, {})
        if name == "approval":
            return HttpResult(200, {"approval_reference": "opaque", "request_id": "approval-1"}, {})
        if name in {"catalog", "tools"}:
            return HttpResult(200, {"data": [{"id": "one"}], "request_id": f"{name}-1"}, {})
        if name == "health":
            return HttpResult(200, {"ok": True}, {})
        return HttpResult(200, {"success": True, "request_id": f"{name}-1"}, {})

    commands = []

    def run(command, **kwargs):
        commands.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="passed", stderr="")

    probes = run_component_probes(
        root=ROOT,
        backend_url="https://backend.rc.test",
        agent_url="https://agent.rc.test",
        mcp_url="https://mcp.rc.test",
        config=_probe_config(),
        environ={"AI00_RC_USER_TOKEN": "secret-token"},
        request=request,
        run=run,
    )

    assert {probe.component for probe in probes} == set(REQUIRED_CHECKS)
    assert all(probe.status == "passed" for probe in probes)
    assert commands[0][0][:4] == ["dotnet", "test", str(ROOT / "local-runtime/Ai00.LocalRuntime.sln"), "--configuration"]
    assert not any("secret-token" in probe.endpoint for probe in probes)


def test_provider_probes_use_backend_gateway_once_per_exact_domain():
    calls = []

    def request(method, url, headers, body, timeout):
        calls.append((method, url, headers, body, timeout))
        request_id = headers["X-Request-ID"]
        return HttpResult(200, {"success": True, "data": {"status": "ok", "request_id": request_id}}, {})

    results = run_provider_probes(
        root=ROOT,
        backend_url="https://backend.rc.test",
        config=_probe_config(),
        environ={"AI00_RC_USER_TOKEN": "secret-token"},
        run_id="gitea:42:1",
        request=request,
    )
    evidence = build_provider_evidence(
        environment_id="capability-v2-rc-42",
        run_id="gitea:42:1",
        git_commit="a" * 40,
        backend_url="https://backend.rc.test/private",
        results=results,
    )

    assert len(calls) == 11
    assert all("/api/v1/capabilities/" in call[1] and call[1].endswith(":invoke") for call in calls)
    assert set(evidence["domains"]) == set(_probe_config()["providers"])
    assert set(evidence["domains"].values()) == {"passed"}
    assert evidence["endpoint"] == "https://backend.rc.test"
    assert "secret-token" not in json.dumps(evidence)
