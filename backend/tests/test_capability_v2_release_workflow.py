from __future__ import annotations

from pathlib import Path

import yaml

from backend.capability_v2.domain_manifest import load_domain_manifests


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/capability-v2-release.yml"
DOMAIN_MANIFESTS = ROOT / "backend/capability_v2/official_domains.json"


def test_release_workflow_injects_every_manifest_database_credential():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    manifests = load_domain_manifests(DOMAIN_MANIFESTS)

    for domain in manifests.domains:
        for environment_name in (
            domain.database.runtime_url_env,
            domain.database.ddl_url_env,
        ):
            secret_name = f"CAPABILITY_V2_{environment_name.removeprefix('AI00_')}"
            assert f"{environment_name}: ${{{{ secrets.{secret_name} }}}}" in workflow


def test_release_workflow_builds_current_run_evidence_before_acceptance():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    database_command = (
        "python backend/scripts/verify_domain_database_isolation.py "
        "--provider-evidence \"$env:AI00_ACCEPTANCE_PROVIDER_CRUD_EVIDENCE\" "
        "--output artifacts/database-isolation.json"
    )
    assembly_command = (
        "python backend/scripts/assemble_capability_v2_rc_evidence.py "
        "--runtime-evidence \"$env:AI00_ACCEPTANCE_RUNTIME_EVIDENCE_SOURCE\" "
        "--database-evidence artifacts/database-isolation.json "
        "--output \"$env:AI00_ACCEPTANCE_RC_EVIDENCE\""
    )
    acceptance_command = (
        "python backend/scripts/run_capability_v2_acceptance.py "
        "--mode release-candidate --strict"
    )

    assert "AI00_ACCEPTANCE_RUNTIME_EVIDENCE_SOURCE:" in workflow
    assert "AI00_ACCEPTANCE_PROVIDER_CRUD_EVIDENCE:" in workflow
    assert "AI00_ACCEPTANCE_RC_EVIDENCE: artifacts/capability-v2-rc-evidence.json" in workflow
    assert database_command in workflow
    assert assembly_command in workflow
    assert workflow.index(database_command) < workflow.index(assembly_command)
    assert workflow.index(assembly_command) < workflow.index(acceptance_command)
    assert "artifacts/capability-v2-rc-evidence.json" in workflow
    assert "artifacts/database-isolation.json" in workflow


def test_release_workflow_runs_backend_and_plugin_python_suites():
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["integrated-release-candidate"]["steps"]
    commands = [step.get("run") for step in steps if isinstance(step, dict)]

    assert "python -m pytest backend/tests plugins -q" in commands


def test_release_workflow_runs_release_gates_and_revalidates_rc_report():
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["integrated-release-candidate"]["steps"]
    commands = [step.get("run") for step in steps if isinstance(step, dict)]

    freeze = "python backend/scripts/freeze_official_domains.py --check"
    dependencies = "python backend/scripts/check_domain_dependencies.py"
    boundaries = "python backend/scripts/audit_domain_boundaries.py --json"
    acceptance = (
        "python backend/scripts/run_capability_v2_acceptance.py "
        "--mode release-candidate --strict "
        "--report artifacts/capability-v2-release-candidate.json"
    )
    report_check = (
        "python backend/scripts/check_capability_v2_completion.py "
        "--mode strict --report artifacts/capability-v2-release-candidate.json"
    )

    for command in (freeze, dependencies, boundaries, acceptance, report_check):
        assert command in commands
    assert commands.index(freeze) < commands.index(acceptance)
    assert commands.index(dependencies) < commands.index(acceptance)
    assert commands.index(boundaries) < commands.index(acceptance)
    assert commands.index(acceptance) < commands.index(report_check)
