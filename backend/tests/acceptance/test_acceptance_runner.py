import json
import hashlib
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from backend.capability_v2.completion import evaluate_completion
from backend.capability_v2.domain_manifest import load_domain_manifests
from backend.scripts import run_capability_v2_acceptance as acceptance_runner
from backend.scripts.run_capability_v2_acceptance import (
    MANDATORY_CASES,
    _domain_manifest_binding,
    _domain_migration_bindings,
    _tracked_worktree_clean,
    acceptance_temp_root,
    contract_test_command,
    _http_json_probe,
    _migration_binding,
    _oceanbase_probe,
    environment_errors,
    evaluate_case_outcomes,
    build_report,
    catalog_integrity_errors,
    completion_blockers,
    load_documents,
    validate_runtime_evidence,
    validate_report_schema,
    validate_manifest,
)


def _runtime_evidence(catalog, manifest, *, commit, run_id="rc-run-42"):
    domain_ids = sorted(
        item.domain_id
        for item in load_domain_manifests(
            Path(__file__).resolve().parents[3] / "backend/capability_v2/official_domains.json"
        ).domains
    )
    return {
        "schema_version": 1,
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "git_commit": commit,
        "catalog_release": catalog["release_id"],
        "catalog_hash": catalog["catalog_hash"],
        "migration": _migration_binding(),
        "domain_manifest": _domain_manifest_binding(),
        "domain_migrations": _domain_migration_bindings(),
        "provider_artifacts": catalog["provider_artifacts"],
        "environment_id": "rc-isolated-42",
        "component_results": {
            "backend_gateway": "passed",
            "plugin": "passed",
            "agent": "passed",
            "mcp": "passed",
            "local_runtime": "passed",
        },
        "probe_provenance": {
            "outcome_sha256": "sha256:" + "e" * 64,
            "components": {
                component: {
                    "endpoint": (
                        "outbound://backend-device-gateway"
                        if component == "local_runtime"
                        else f"https://{component}.example.test"
                    ),
                    "checks": ["current-run"],
                    "duration_ms": 1,
                    "correlation_ids": [f"{component}-request-1"],
                }
                for component in (
                    "backend_gateway", "plugin", "agent", "mcp", "local_runtime"
                )
            },
        },
        "database_isolation": {
            "owner_operations": {
                domain_id: {
                    "provider_crud": "passed",
                    "migration_ledger": "passed",
                    "database_read": "passed",
                    "database_write": "passed",
                    "runtime_ddl": "denied",
                }
                for domain_id in domain_ids
            },
            "cross_domain": [
                {
                    "source_domain": source,
                    "target_domain": target,
                    "read": "denied",
                    "write": "denied",
                }
                for source in domain_ids
                for target in domain_ids
                if source != target
            ],
        },
        "capabilities": {
            key: {case: "passed" for case in cases}
            for key, cases in manifest["capabilities"].items()
        },
    }


def test_release_bindings_cover_manifest_and_every_domain_migration():
    manifest_binding = _domain_manifest_binding()
    migration_bindings = _domain_migration_bindings()

    assert manifest_binding["filename"] == "backend/capability_v2/official_domains.json"
    assert manifest_binding["sha256"].startswith("sha256:")
    assert {
        (row["domain_id"], row["filename"])
        for row in migration_bindings
    } == {
        ("agent", "0001_agent.sql"),
        ("base", "0001_base_platform.sql"),
        ("base", "0002_domain_inbox.sql"),
        ("craft", "0001_pbom.sql"),
        ("digital_model", "0001_digital_model.sql"),
        ("factory", "0001_factory.sql"),
        ("integration", "0001_integration.sql"),
        ("knowledge", "0001_knowledge.sql"),
        ("knowledge", "0002_domain_outbox_delivery.sql"),
        ("knowledge", "0003_display_counters.sql"),
        ("local_runtime", "0001_local_runtime.sql"),
        ("ontology", "0001_ontology.sql"),
        ("project_management", "0001_project_management.sql"),
        ("simulation", "0001_simulation.sql"),
    }
    assert all(row["sha256"].startswith("sha256:") for row in migration_bindings)
    assert all(row["artifact_version"] for row in migration_bindings)


def test_rc_cleanliness_ignores_untracked_files_but_rejects_tracked_changes(
    tmp_path, monkeypatch
):
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    tracked = repository / "tracked.txt"
    tracked.write_text("released\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repository, check=True)
    subprocess.run(
        [
            "git", "-c", "user.name=Acceptance Test",
            "-c", "user.email=acceptance@example.invalid",
            "commit", "-q", "-m", "initial",
        ],
        cwd=repository,
        check=True,
    )
    (repository / "handoff-untracked.md").write_text("preserve\n", encoding="utf-8")
    monkeypatch.setattr(acceptance_runner, "ROOT", repository)

    assert _tracked_worktree_clean() is True

    tracked.write_text("changed\n", encoding="utf-8")
    assert _tracked_worktree_clean() is False


def test_current_manifest_is_release_complete():
    catalog, manifest = load_documents()
    assert validate_manifest(catalog, manifest) == []


def test_acceptance_temp_root_is_repository_local_and_writable(tmp_path):
    temp_root = acceptance_temp_root(tmp_path)

    probe = temp_root / "probe.json"
    probe.write_text("{}", encoding="utf-8")

    assert temp_root.parent == tmp_path
    assert probe.read_text(encoding="utf-8") == "{}"


def test_contract_pytest_uses_run_local_basetemp(tmp_path):
    command = contract_test_command(tmp_path)

    basetemp_index = command.index("--basetemp")
    assert Path(command[basetemp_index + 1]).parent == tmp_path
    assert command[command.index("-p") + 1] == "no:cacheprovider"


def test_one_missing_case_blocks_with_exact_capability_and_case():
    catalog, manifest = load_documents()
    key = next(iter(manifest["capabilities"]))
    missing = next(iter(MANDATORY_CASES))
    manifest["capabilities"][key].pop(missing)

    assert f"{key}: missing mandatory case {missing}" in validate_manifest(catalog, manifest)


def test_release_candidate_never_passes_on_missing_external_environment():
    errors = environment_errors("release-candidate", {}, probe=False)

    assert "missing AI00_ACCEPTANCE_ENVIRONMENT_ID" in errors
    assert "missing AI00_ACCEPTANCE_OCEANBASE_URL" in errors
    assert "missing AI00_ACCEPTANCE_OCEANBASE_SSL_CA" in errors
    assert "missing AI00_ACCEPTANCE_RUN_ID" in errors
    for variable in (
        "AI00_ACCEPTANCE_OIS_HEALTH_URL", "AI00_ACCEPTANCE_JWT_DISCOVERY_URL",
        "AI00_ACCEPTANCE_OAUTH_DISCOVERY_URL",
    ):
        assert f"missing {variable}" in errors
    assert "missing AI00_ACCEPTANCE_LOCAL_RUNTIME_HEALTH_URL" not in errors
    manifests = load_domain_manifests(
        Path(__file__).resolve().parents[3] / "backend/capability_v2/official_domains.json"
    )
    for domain in manifests.domains:
        assert f"missing {domain.database.runtime_url_env}" in errors
        assert f"missing {domain.database.ddl_url_env}" in errors
    assert not any("_RESULT must be passed" in error for error in errors)


def test_generated_report_validates_against_checked_in_schema():
    catalog, manifest = load_documents()
    declared = sum(len(cases) for cases in manifest["capabilities"].values())
    report = build_report("offline", catalog, manifest, [], {
        "exit_code": 0, "summary": "acceptance passed", "command": "pytest acceptance",
        "outcome_counts": {"passed": declared, "failed": 0, "skipped": 0, "missing": 0},
    })

    assert validate_report_schema(report) == []
    assert report["completion"]["complete"] is True
    assert report["completion"]["cross_domain_sql"] == 0
    assert report["domain_manifest"] == _domain_manifest_binding()
    assert report["domain_migrations"] == _domain_migration_bindings()


def test_release_report_uses_bound_runtime_component_results_not_env_constants(
    monkeypatch,
):
    catalog, manifest = load_documents()
    declared = sum(len(cases) for cases in manifest["capabilities"].values())
    monkeypatch.setenv("AI00_ACCEPTANCE_AGENT_RESULT", "passed")
    components = {
        "backend_gateway": "passed",
        "plugin": "passed",
        "agent": "passed",
        "mcp": "passed",
        "local_runtime": "passed",
    }

    report = build_report(
        "release-candidate",
        catalog,
        manifest,
        [],
        {
            "exit_code": 0,
            "summary": "acceptance passed",
            "command": "pytest acceptance",
            "outcome_counts": {
                "passed": declared,
                "failed": 0,
                "skipped": 0,
                "missing": 0,
            },
        },
        runtime_evidence_hash="sha256:" + "a" * 64,
        component_results=components,
    )

    assert report["component_results"] == components


def test_only_release_candidate_is_blocked_by_incomplete_program():
    root = Path(__file__).resolve().parents[3]
    completion = replace(
        evaluate_completion(root, mode="progress"),
        cross_domain_sql=1,
        consumer_bypasses=1,
        failed=("cross_domain_sql:1", "consumer_bypasses:1"),
    )

    assert completion_blockers("offline", completion) == []
    blockers = completion_blockers("release-candidate", completion)
    assert "capability completion: cross_domain_sql:1" in blockers
    assert "capability completion: consumer_bypasses:1" in blockers
    assert not any("missing_domain:" in blocker for blocker in blockers)


def test_skipped_or_missing_mandatory_node_is_release_blocking():
    _catalog, manifest = load_documents()
    nodes = [node for cases in manifest["capabilities"].values() for node in cases.values()]
    outcomes = {node: "passed" for node in nodes}
    outcomes[nodes[0]] = "skipped"
    outcomes.pop(nodes[1])

    counts, blockers = evaluate_case_outcomes(manifest, outcomes)

    assert counts["skipped"] == 1
    assert counts["missing"] == 1
    assert any("was skipped" in blocker for blocker in blockers)
    assert any("was not collected" in blocker for blocker in blockers)


def test_report_id_tampering_is_detected():
    catalog, manifest = load_documents()
    declared = sum(len(cases) for cases in manifest["capabilities"].values())
    report = build_report("offline", catalog, manifest, [], {
        "exit_code": 0, "summary": "acceptance passed", "command": "pytest acceptance",
        "outcome_counts": {"passed": declared, "failed": 0, "skipped": 0, "missing": 0},
    })
    report["catalog_hash"] = "sha256:" + "0" * 64

    assert "report integrity: report_id does not match canonical report content" in validate_report_schema(report)


def test_failed_release_candidate_report_remains_schema_valid_for_diagnostics():
    catalog, manifest = load_documents()
    report = build_report("release-candidate", catalog, manifest, ["environment probe failed"], {
        "exit_code": 1, "summary": "acceptance blocked", "command": "pytest acceptance",
        "outcome_counts": {"passed": 0, "failed": 0, "skipped": 0, "missing": 609},
    })

    assert report["status"] == "failed"
    assert validate_report_schema(report) == []


def test_passed_release_candidate_requires_both_production_sharing_paths():
    catalog, manifest = load_documents()
    declared = sum(len(cases) for cases in manifest["capabilities"].values())
    report = build_report(
        "release-candidate",
        catalog,
        manifest,
        [],
        {
            "exit_code": 0,
            "summary": "acceptance passed",
            "command": "pytest acceptance",
            "outcome_counts": {
                "passed": declared,
                "failed": 0,
                "skipped": 0,
                "missing": 0,
            },
        },
        runtime_evidence_hash="sha256:" + "a" * 64,
    )
    report["status"] = "passed"
    report["working_tree_clean"] = True
    report["component_results"] = {
        "backend_gateway": "passed",
        "plugin": "passed",
        "agent": "passed",
        "mcp": "passed",
        "local_runtime": "passed",
    }
    report["completion"].update(
        {
            "complete": True,
            "plugin_agent_gateway_only": True,
            "independent_domains": 11,
            "cross_domain_sql": 0,
            "internal_imports": 0,
            "consumer_bypasses": 0,
            "sync_production_paths": 0,
            "async_production_paths": 0,
            "failed": [],
        }
    )
    report.pop("report_id")
    canonical = json.dumps(
        report, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    report["report_id"] = "sha256:" + hashlib.sha256(canonical).hexdigest()

    errors = validate_report_schema(report)

    assert any("sync_production_paths" in error for error in errors)
    assert any("async_production_paths" in error for error in errors)


def test_runtime_evidence_is_bound_to_commit_run_catalog_migrations_and_providers(tmp_path, monkeypatch):
    catalog, manifest = load_documents()
    commit = "a" * 40
    monkeypatch.setattr("backend.scripts.run_capability_v2_acceptance._git", lambda *args: commit)
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(_runtime_evidence(catalog, manifest, commit=commit)), encoding="utf-8")
    env = {
        "AI00_ACCEPTANCE_RC_EVIDENCE": str(path),
        "AI00_ACCEPTANCE_ENVIRONMENT_ID": "rc-isolated-42",
        "AI00_ACCEPTANCE_RUN_ID": "rc-run-42",
    }

    errors, evidence_hash = validate_runtime_evidence(catalog, manifest, env)

    assert errors == []
    assert evidence_hash.startswith("sha256:")


def test_runtime_evidence_rejects_stale_or_rebound_document(tmp_path, monkeypatch):
    catalog, manifest = load_documents()
    monkeypatch.setattr("backend.scripts.run_capability_v2_acceptance._git", lambda *args: "b" * 40)
    evidence = _runtime_evidence(catalog, manifest, commit="a" * 40, run_id="old-run")
    evidence["catalog_hash"] = "sha256:" + "0" * 64
    evidence["migration"]["sha256"] = "sha256:" + "0" * 64
    evidence["domain_manifest"]["sha256"] = "sha256:" + "0" * 64
    evidence["domain_migrations"][0]["sha256"] = "sha256:" + "0" * 64
    evidence["provider_artifacts"] = []
    evidence["generated_at"] = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    path = tmp_path / "stale.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors, _ = validate_runtime_evidence(catalog, manifest, {
        "AI00_ACCEPTANCE_RC_EVIDENCE": str(path),
        "AI00_ACCEPTANCE_ENVIRONMENT_ID": "rc-isolated-42",
        "AI00_ACCEPTANCE_RUN_ID": "new-run",
    })

    assert "RC evidence git commit mismatch" in errors
    assert "RC evidence run identity mismatch" in errors
    assert "RC evidence catalog hash mismatch" in errors
    assert "RC evidence migration binding mismatch" in errors
    assert "RC evidence domain manifest binding mismatch" in errors
    assert "RC evidence domain migration bindings mismatch" in errors
    assert "RC evidence provider artifact binding mismatch" in errors
    assert "RC evidence generation time is stale or in the future" in errors


def test_runtime_evidence_requires_exact_database_isolation_matrix(tmp_path, monkeypatch):
    catalog, manifest = load_documents()
    commit = "a" * 40
    monkeypatch.setattr("backend.scripts.run_capability_v2_acceptance._git", lambda *args: commit)
    evidence = _runtime_evidence(catalog, manifest, commit=commit)
    removed = evidence["database_isolation"]["cross_domain"].pop()
    evidence["database_isolation"]["cross_domain"].append(
        evidence["database_isolation"]["cross_domain"][0]
    )
    owner_result = evidence["database_isolation"]["owner_operations"].pop(
        removed["target_domain"]
    )
    evidence["database_isolation"]["owner_operations"]["rogue"] = owner_result
    path = tmp_path / "incomplete-database-matrix.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors, _ = validate_runtime_evidence(catalog, manifest, {
        "AI00_ACCEPTANCE_RC_EVIDENCE": str(path),
        "AI00_ACCEPTANCE_ENVIRONMENT_ID": "rc-isolated-42",
        "AI00_ACCEPTANCE_RUN_ID": "rc-run-42",
    })

    assert "RC evidence database owner operations do not cover exactly eleven domains" in errors
    assert "RC evidence database isolation matrix is incomplete or duplicated" in errors


def test_runtime_evidence_requires_runtime_ddl_denial_for_every_domain(
    tmp_path, monkeypatch
):
    catalog, manifest = load_documents()
    commit = "a" * 40
    monkeypatch.setattr(
        "backend.scripts.run_capability_v2_acceptance._git",
        lambda *args: commit,
    )
    evidence = _runtime_evidence(catalog, manifest, commit=commit)
    evidence["database_isolation"]["owner_operations"]["agent"].pop(
        "runtime_ddl"
    )
    path = tmp_path / "missing-runtime-ddl.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors, _ = validate_runtime_evidence(
        catalog,
        manifest,
        {
            "AI00_ACCEPTANCE_RC_EVIDENCE": str(path),
            "AI00_ACCEPTANCE_ENVIRONMENT_ID": "rc-isolated-42",
            "AI00_ACCEPTANCE_RUN_ID": "rc-run-42",
        },
    )

    assert any("runtime_ddl" in error for error in errors)


def test_runtime_evidence_requires_all_current_component_probe_results(
    tmp_path, monkeypatch
):
    catalog, manifest = load_documents()
    commit = "a" * 40
    monkeypatch.setattr(
        "backend.scripts.run_capability_v2_acceptance._git",
        lambda *args: commit,
    )
    evidence = _runtime_evidence(catalog, manifest, commit=commit)
    evidence.pop("component_results")
    evidence.pop("probe_provenance")
    path = tmp_path / "missing-component-results.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors, _ = validate_runtime_evidence(
        catalog,
        manifest,
        {
            "AI00_ACCEPTANCE_RC_EVIDENCE": str(path),
            "AI00_ACCEPTANCE_ENVIRONMENT_ID": "rc-isolated-42",
            "AI00_ACCEPTANCE_RUN_ID": "rc-run-42",
        },
    )

    assert any("component_results" in error for error in errors)
    assert any("probe_provenance" in error for error in errors)


def test_schema_invalid_runtime_evidence_fails_without_structural_exception(tmp_path):
    catalog, manifest = load_documents()
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps({"capabilities": []}), encoding="utf-8")

    errors, evidence_hash = validate_runtime_evidence(catalog, manifest, {
        "AI00_ACCEPTANCE_RC_EVIDENCE": str(path),
        "AI00_ACCEPTANCE_ENVIRONMENT_ID": "rc-isolated-42",
        "AI00_ACCEPTANCE_RUN_ID": "rc-run-42",
    })

    assert errors
    assert evidence_hash.startswith("sha256:")


def test_schema_valid_but_unparseable_evidence_time_becomes_blocker(tmp_path, monkeypatch):
    catalog, manifest = load_documents()
    commit = "a" * 40
    monkeypatch.setattr("backend.scripts.run_capability_v2_acceptance._git", lambda *args: commit)
    evidence = _runtime_evidence(catalog, manifest, commit=commit)
    evidence["generated_at"] = "2026-08-10t12:00:00z"
    path = tmp_path / "lowercase-time.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors, _ = validate_runtime_evidence(catalog, manifest, {
        "AI00_ACCEPTANCE_RC_EVIDENCE": str(path),
        "AI00_ACCEPTANCE_ENVIRONMENT_ID": "rc-isolated-42",
        "AI00_ACCEPTANCE_RUN_ID": "rc-run-42",
    })

    assert "RC evidence generation time cannot be parsed safely" in errors


def test_catalog_integrity_compares_complete_generated_projection():
    catalog, _manifest = load_documents()
    catalog["capabilities"][0]["authorization_policy"] = "tampered:allow-all"

    assert "developer catalog projection differs from immutable release" in catalog_integrity_errors(catalog)


class _ProbeResponse:
    status = 200

    def __init__(self, url, document):
        self._url = url
        self._document = document

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def geturl(self):
        return self._url

    def read(self, _limit):
        return json.dumps(self._document).encode()


def test_http_probe_rejects_cross_origin_redirect_and_wrong_identity(monkeypatch):
    source = "https://ois.example.test/health"
    monkeypatch.setattr(
        "backend.scripts.run_capability_v2_acceptance.urlopen",
        lambda *_args, **_kwargs: _ProbeResponse("https://attacker.example/health", {}),
    )
    assert _http_json_probe("ois", source, "rc-42", {}) == "ois health probe redirected across origin"

    monkeypatch.setattr(
        "backend.scripts.run_capability_v2_acceptance.urlopen",
        lambda *_args, **_kwargs: _ProbeResponse(source, {"service": "other", "environment_id": "rc-42"}),
    )
    assert _http_json_probe("ois", source, "rc-42", {}) == "ois service identity or environment mismatch"


def test_oceanbase_probe_enforces_tls_and_calls_migration_readiness(tmp_path, monkeypatch):
    ca = tmp_path / "ca.pem"
    ca.write_text("test-ca", encoding="utf-8")
    connection = SimpleNamespace(close=lambda: None)
    connect_calls = []
    fake_pymysql = SimpleNamespace(
        cursors=SimpleNamespace(DictCursor=object()),
        connect=lambda **kwargs: connect_calls.append(kwargs) or connection,
    )
    monkeypatch.setitem(sys.modules, "pymysql", fake_pymysql)
    migration_calls = []
    monkeypatch.setattr(
        "backend.db.migration_readiness.assert_migrations_applied",
        lambda value: migration_calls.append(value),
    )

    error = _oceanbase_probe("mysql://user:pass@db.example.test:2881/ai00", str(ca))

    assert error is None
    assert connect_calls[0]["ssl"] == {"ca": str(ca), "check_hostname": True}
    assert migration_calls == [connection]
