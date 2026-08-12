from __future__ import annotations

from pathlib import Path

import yaml

from backend.capability_v2.domain_manifest import load_domain_manifests


ROOT = Path(__file__).resolve().parents[2]
GITHUB_WORKFLOW = ROOT / ".github/workflows/capability-v2-release.yml"
GITEA_WORKFLOW = ROOT / ".gitea/workflows/capability-v2-release.yml"
DOMAIN_MANIFESTS = ROOT / "backend/capability_v2/official_domains.json"
REQUIRED_GATES = (
    "freeze-domains", "catalog-check", "docs-check", "registry-strict",
    "acceptance-manifest-check", "dependency-check", "boundary-audit",
    "python-tests", "agent-tests", "mcp-tests", "local-runtime-tests",
    "database-bootstrap", "domain-migrations", "runtime-evidence",
    "database-isolation", "evidence-assembly", "strict-acceptance",
    "completion-recheck", "artifact-upload",
)


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _job(path: Path) -> dict:
    return _load(path)["jobs"]["integrated-release-candidate"]


def _mandatory_steps(path: Path) -> list[tuple[str, str, str]]:
    selected = []
    for step in _job(path)["steps"]:
        name = str(step.get("name", ""))
        if name in REQUIRED_GATES:
            selected.append((name, str(step.get("run", "")), str(step.get("working-directory", ""))))
    return selected


def test_gitea_workflow_exists_and_uses_only_protected_rc_runner():
    assert GITEA_WORKFLOW.is_file()
    workflow = _load(GITEA_WORKFLOW)
    assert _job(GITEA_WORKFLOW)["runs-on"] == ["self-hosted", "test-server", "capability-v2-rc"]
    assert workflow["permissions"] == {"contents": "read"}
    source = GITEA_WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in source
    assert "environment_id:" in source and "required: true" in source
    assert "pull_request:" not in source and "push:" not in source


def test_both_workflows_have_identical_ordered_mandatory_gates():
    github = _mandatory_steps(GITHUB_WORKFLOW)
    gitea = _mandatory_steps(GITEA_WORKFLOW)
    assert [name for name, _run, _cwd in github] == list(REQUIRED_GATES)
    assert gitea == github


def test_workflows_bootstrap_one_admin_secret_and_import_generated_domain_urls():
    manifests = load_domain_manifests(DOMAIN_MANIFESTS)
    expected_names = {
        name
        for domain in manifests.domains
        for name in (domain.database.runtime_url_env, domain.database.ddl_url_env)
    }
    assert len(expected_names) == 22
    for path in (GITHUB_WORKFLOW, GITEA_WORKFLOW):
        source = path.read_text(encoding="utf-8")
        assert "secrets.CAPABILITY_V2_RC_ADMIN_DB_URL" in source
        assert "--admin-url-env AI00_RC_ADMIN_DB_URL" in source
        assert "--env-file .runtime/capability-v2-rc.env" in source
        assert '--export-job-env "$env:GITHUB_ENV"' in source
        for environment_name in expected_names:
            secret_name = f"CAPABILITY_V2_{environment_name.removeprefix('AI00_')}"
            assert f"secrets.{secret_name}" not in source


def test_runtime_evidence_is_generated_locally_and_constant_results_are_forbidden():
    command = (
        'python backend/scripts/run_capability_v2_rc_runtime.py '
        '--backend-url "$env:AI00_RC_BACKEND_URL" '
        '--agent-url "$env:AI00_RC_AGENT_URL" '
        '--mcp-url "$env:AI00_RC_MCP_URL" '
        '--provider-output artifacts/provider-crud.json '
        '--runtime-output artifacts/runtime-evidence.json'
    )
    for path in (GITHUB_WORKFLOW, GITEA_WORKFLOW):
        source = path.read_text(encoding="utf-8")
        assert command in source
        assert "AI00_ACCEPTANCE_AGENT_RESULT" not in source
        assert "AI00_ACCEPTANCE_MCP_RESULT" not in source
        assert "AI00_ACCEPTANCE_LOCAL_RUNTIME_RESULT" not in source
        assert "AI00_ACCEPTANCE_LOCAL_RUNTIME_HEALTH_URL" not in source


def test_artifact_upload_is_allowlisted_and_preceded_by_secret_schema_scan():
    allowed = {
        "artifacts/provider-crud.json",
        "artifacts/runtime-evidence.json",
        "artifacts/database-isolation.json",
        "artifacts/capability-v2-rc-evidence.json",
        "artifacts/capability-v2-release-candidate.json",
    }
    for path in (GITHUB_WORKFLOW, GITEA_WORKFLOW):
        steps = _job(path)["steps"]
        upload_index = next(i for i, step in enumerate(steps) if step.get("name") == "artifact-upload")
        scan_index = next(i for i, step in enumerate(steps) if step.get("name") == "secret-schema-scan")
        assert scan_index < upload_index
        upload = steps[upload_index]
        assert upload["if"] == "always()"
        assert set(upload["with"]["path"].splitlines()) == allowed
        assert ".runtime" not in upload["with"]["path"]
        for forbidden in (
            "password", "token", "secret", "credential", "database_url", "dsn",
            "authorization", "admin_url", "private_key",
        ):
            assert forbidden in steps[scan_index]["run"]
