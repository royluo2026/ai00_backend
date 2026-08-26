from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from backend.capability_v2.completion import (
    CompletionConfigurationError,
    evaluate_completion,
)
from backend.capability_v2.consumer_routes import scan_web_api_routes
from backend.tests.capability_completion_support import FrozenCoverageReview


DOMAIN_IDS = (
    "agent",
    "base",
    "craft",
    "device",
    "digital_model",
    "factory",
    "integration",
    "knowledge",
    "ontology",
    "project_management",
    "simulation",
)


def _write_json(root: Path, relative: str, document: object) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def _write_text(root: Path, relative: str, text: str = "") -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _commit_frontend(frontend: Path) -> str:
    commands = (
        ("init", "-q"),
        ("config", "user.email", "capability-tests@example.invalid"),
        ("config", "user.name", "Capability Tests"),
        ("add", "."),
        ("commit", "-q", "-m", "test frontend"),
    )
    for arguments in commands:
        subprocess.run(
            ["git", "-C", str(frontend), *arguments],
            check=True,
            capture_output=True,
            text=True,
        )
    return subprocess.run(
        ["git", "-C", str(frontend), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _complete_repository(tmp_path: Path) -> Path:
    _write_json(
        tmp_path,
        "backend/governance/capability_v2_completion.json",
        {
            "schema_version": 1,
            "required_domains": list(DOMAIN_IDS),
            "consumer_adapter_roots": ["backend/consumers", "plugins/agent"],
            "forbidden_consumer_paths": [],
            "forbidden_consumer_import_fragments": [
                ".application.",
                ".infrastructure.repositories.",
            ],
            "forbidden_consumer_call_fragments": ["get_conn("],
            "coverage_invariants": {
                "domains": 11,
                "stable_functions": 752,
                "resolutions.unreviewed": 0,
            },
            "starting_snapshot": {
                "candidate_capabilities": 87,
                "catalog_descriptors": 102,
                "proposed_final_catalog_capabilities": 173,
            },
        },
    )
    _write_json(
        tmp_path,
        "docs/capabilities/catalog.v2.json",
        {
            "capabilities": [
                {
                    "id": f"test.capability_{index}",
                    "major_version": 1,
                    "lifecycle_status": "stable",
                }
                for index in range(173)
            ]
            + [
                {
                    "id": "test.reviewed_candidate",
                    "major_version": 1,
                    "lifecycle_status": "stable",
                }
            ]
        },
    )
    _write_json(
        tmp_path,
        "docs/governance/capability-coverage-review/generated/summary.json",
        {
            "domains": 11,
            "stable_functions": 752,
            "resolutions": {"unreviewed": 0},
            "candidate_capabilities": 87,
            "catalog_descriptors": 102,
            "proposed_final_catalog_capabilities": 173,
        },
    )
    manifests = []
    for domain_id in DOMAIN_IDS:
        artifact_path = f"plugins/{domain_id}/{domain_id}_backend"
        migration_path = f"backend/db/migrations/domains/{domain_id}"
        _write_text(tmp_path, f"{artifact_path}/__init__.py")
        _write_text(tmp_path, f"{migration_path}/0001_initial.sql", "SELECT 1;\n")
        manifests.append(
            {
                "domain_id": domain_id,
                "artifact": {
                    "plugin_id": f"official.{domain_id.replace('_', '-')}",
                    "module": f"{domain_id}_backend.capabilities",
                    "version": "1.0.0",
                    "artifact_hash": "sha256:" + domain_id.encode().hex().ljust(64, "0")[:64],
                },
                "artifact_path": artifact_path,
                "allowed_owners": [domain_id],
                "database": {
                    "database_name": f"ai00_{domain_id}",
                    "runtime_url_env": f"AI00_{domain_id.upper()}_DB_URL",
                    "ddl_url_env": f"AI00_{domain_id.upper()}_DDL_DB_URL",
                    "migration_path": migration_path,
                    "schema_paths": [migration_path],
                },
                "search_export": None,
                "event_subscriptions": [],
            }
        )
    _write_json(
        tmp_path,
        "backend/capability_v2/official_domains.json",
        {"schema_version": 1, "domains": manifests},
    )
    _write_json(
        tmp_path,
        "backend/governance/boundary_baseline.json",
        {"registry_version": 1, "violations": []},
    )
    _write_text(
        tmp_path,
        "backend/consumers/plugin_adapter.py",
        "from backend.capability_v2.gateway import CapabilityGatewayService\n",
    )
    _write_text(
        tmp_path,
        "plugins/agent/agent_backend/catalog_tools.py",
        "from backend.capability_v2.gateway import CapabilityGatewayService\n",
    )
    _write_text(tmp_path, "plugins/craft/craft_backend/infrastructure/domain_clients.py")
    _write_text(tmp_path, "backend/capability_v2/event_transport.py")
    _write_text(tmp_path, "backend/base/inbox.py")
    _write_text(
        tmp_path,
        "plugins/craft/tests/test_bop_domain_sharing.py",
        "def test_bop_binding_uses_gateway(): pass\n",
    )
    _write_text(
        tmp_path,
        "backend/tests/test_production_domain_event_path.py",
        "def test_knowledge_publication_reaches_base_once(): pass\n",
    )
    _write_json(
        tmp_path,
        "backend/governance/capability_v2_production_paths.json",
        {
            "schema_version": 1,
            "sync": [
                {
                    "path_id": "craft-factory-resource-binding",
                    "caller": "craft",
                    "callee": "factory",
                    "contract": "factory.resource.read@1",
                    "source_modules": [
                        "plugins/craft/craft_backend/infrastructure/domain_clients.py"
                    ],
                    "test_node": (
                        "plugins/craft/tests/test_bop_domain_sharing.py"
                        "::test_bop_binding_uses_gateway"
                    ),
                }
            ],
            "async": [
                {
                    "path_id": "knowledge-publication-base-projection",
                    "producer": "knowledge",
                    "consumer": "base",
                    "contract": "knowledge.document.published.v1",
                    "source_modules": [
                        "backend/capability_v2/event_transport.py",
                        "backend/base/inbox.py",
                    ],
                    "test_node": (
                        "backend/tests/test_production_domain_event_path.py"
                        "::test_knowledge_publication_reaches_base_once"
                    ),
                }
            ],
        },
    )
    return tmp_path


def test_complete_repository_satisfies_all_three_goals(tmp_path: Path) -> None:
    root = _complete_repository(tmp_path)

    report = evaluate_completion(root, mode="strict")

    assert report.complete is True
    assert report.domains == DOMAIN_IDS
    assert report.plugin_agent_gateway_only is True
    assert report.independent_domains == 11
    assert report.sync_production_paths == 1
    assert report.async_production_paths == 1
    assert report.cross_domain_sql == 0
    assert report.internal_imports == 0
    assert report.consumer_bypasses == 0
    assert report.catalog_capabilities == 174
    assert report.failed == ()


def test_missing_domain_and_boundary_debt_fail_closed(tmp_path: Path) -> None:
    root = _complete_repository(tmp_path)
    manifests_path = root / "backend/capability_v2/official_domains.json"
    manifests = json.loads(manifests_path.read_text(encoding="utf-8"))
    manifests["domains"] = [
        item for item in manifests["domains"] if item["domain_id"] != "agent"
    ]
    _write_json(root, "backend/capability_v2/official_domains.json", manifests)
    _write_json(
        root,
        "backend/governance/boundary_baseline.json",
        {
            "registry_version": 1,
            "violations": [
                {"category": "cross_domain_sql"},
                {"category": "internal_import"},
            ],
        },
    )

    report = evaluate_completion(root, mode="strict")

    assert report.complete is False
    assert report.independent_domains == 10
    assert report.cross_domain_sql == 1
    assert report.internal_imports == 1
    assert "missing_domain:agent" in report.failed
    assert "cross_domain_sql:1" in report.failed
    assert "internal_imports:1" in report.failed


def test_consumer_business_bypass_is_counted(tmp_path: Path) -> None:
    root = _complete_repository(tmp_path)
    _write_text(
        root,
        "plugins/agent/agent_backend/direct.py",
        "from plugins.craft.craft_backend.application.bop import BopService\n",
    )

    report = evaluate_completion(root, mode="strict")

    assert report.plugin_agent_gateway_only is False
    assert report.consumer_bypasses == 1
    assert "consumer_bypasses:1" in report.failed


def test_legacy_consumer_handler_path_is_counted(tmp_path: Path) -> None:
    root = _complete_repository(tmp_path)
    configuration_path = root / "backend/governance/capability_v2_completion.json"
    configuration = json.loads(configuration_path.read_text(encoding="utf-8"))
    configuration["forbidden_consumer_paths"] = [
        "plugins/agent/agent_backend/tool_handlers"
    ]
    _write_json(
        root,
        "backend/governance/capability_v2_completion.json",
        configuration,
    )
    _write_text(
        root,
        "plugins/agent/agent_backend/tool_handlers/project.py",
        "def run(): return 'legacy'\n",
    )

    report = evaluate_completion(root, mode="strict")

    assert report.consumer_bypasses == 1
    assert report.plugin_agent_gateway_only is False


def test_frozen_coverage_drift_fails_closed(tmp_path: Path) -> None:
    root = _complete_repository(tmp_path)
    summary_path = (
        root
        / "docs/governance/capability-coverage-review/generated/summary.json"
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["stable_functions"] = 751
    _write_json(
        root,
        "docs/governance/capability-coverage-review/generated/summary.json",
        summary,
    )

    report = evaluate_completion(root, mode="strict")

    assert report.complete is False
    assert "coverage_invariant:stable_functions:751!=752" in report.failed


def test_approved_candidate_count_correction_does_not_fail_completion(
    tmp_path: Path,
) -> None:
    root = _complete_repository(tmp_path)
    summary_path = (
        root
        / "docs/governance/capability-coverage-review/generated/summary.json"
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["candidate_capabilities"] = 94
    summary["proposed_final_catalog_capabilities"] = 178
    _write_json(
        root,
        "docs/governance/capability-coverage-review/generated/summary.json",
        summary,
    )

    report = evaluate_completion(root, mode="strict")

    assert report.complete is True


def test_catalog_count_is_evidence_not_a_completion_quota(tmp_path: Path) -> None:
    root = _complete_repository(tmp_path)
    catalog_path = root / "docs/capabilities/catalog.v2.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["capabilities"].pop(0)
    _write_json(root, "docs/capabilities/catalog.v2.json", catalog)

    report = evaluate_completion(root, mode="strict")

    assert report.catalog_capabilities == 173
    assert report.complete is True


def test_production_path_rejects_test_only_source(tmp_path: Path) -> None:
    root = _complete_repository(tmp_path)
    path = root / "backend/governance/capability_v2_production_paths.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["sync"][0]["source_modules"] = [
        "plugins/craft/tests/test_bop_domain_sharing.py"
    ]
    _write_json(root, "backend/governance/capability_v2_production_paths.json", document)

    with pytest.raises(CompletionConfigurationError, match="production source"):
        evaluate_completion(root, mode="strict")


def test_current_repository_reports_three_goal_completion() -> None:
    root = Path(__file__).resolve().parents[2]

    report = evaluate_completion(root, mode="progress")

    assert report.complete is True
    assert report.independent_domains == 11
    assert report.cross_domain_sql == 0
    assert report.internal_imports == 0
    assert report.consumer_bypasses == 0
    assert report.sync_production_paths >= 1
    assert report.async_production_paths >= 1
    assert report.failed == ()
    assert "missing_domain:agent" not in report.failed
    assert "missing_domain:factory" not in report.failed
    assert "missing_domain:integration" not in report.failed
    assert "domain_not_independent:device:migration_path" not in report.failed
    assert "missing_domain:project_management" not in report.failed
    assert "domain_not_independent:base:migration_path" not in report.failed


def test_web_consumer_bypass_is_evaluated_when_web_root_is_supplied(tmp_path: Path) -> None:
    root = _complete_repository(tmp_path)
    web = root / "web"
    web.mkdir()
    (web / "app.js").write_text(
        "fetch('/api/bop/entries', { method: 'POST' });\n", encoding="utf-8"
    )
    _commit_frontend(web)

    report = evaluate_completion(root, mode="strict", web_root=web)

    assert report.web_consumer_bypasses == 1
    assert report.complete is False
    assert "web_consumer_bypasses:1" in report.failed


def test_web_route_inventory_drift_fails_closed(tmp_path: Path) -> None:
    root = _complete_repository(tmp_path)
    web = root / "web"
    web.mkdir()
    (web / "app.js").write_text(
        "fetch('/api/capabilities/project.task.read', { method: 'POST' });\n",
        encoding="utf-8",
    )
    _commit_frontend(web)
    configuration_path = root / "backend/governance/capability_v2_completion.json"
    configuration = json.loads(configuration_path.read_text(encoding="utf-8"))
    configuration["web_route_inventory_artifact"] = "docs/route-inventory.json"
    _write_json(root, "backend/governance/capability_v2_completion.json", configuration)
    _write_json(root, "docs/route-inventory.json", {"counts": {"legacy": 99}})

    report = evaluate_completion(root, mode="strict", web_root=web)

    assert report.complete is False
    assert "web_route_inventory_drift:1" in report.failed


def _configure_complete_web_evidence(
    root: Path, source: str
) -> tuple[Path, Path]:
    web = root / "frontend"
    web.mkdir()
    (web / "app.js").write_text(source, encoding="utf-8")
    configuration_path = root / "backend/governance/capability_v2_completion.json"
    configuration = json.loads(configuration_path.read_text(encoding="utf-8"))
    configuration.update(
        {
            "web_route_inventory_artifact": "docs/web-routes.json",
            "legacy_route_inventory_artifact": "docs/legacy-routes.json",
            "bff_route_inventory_artifact": "docs/bff-routes.json",
            "web_operations_exclusions_artifact": "docs/operations.json",
        }
    )
    _write_json(root, "backend/governance/capability_v2_completion.json", configuration)
    _write_json(root, "docs/legacy-routes.json", {"inventory_kind": "legacy_rest", "entries": []})
    _write_json(root, "docs/bff-routes.json", {"inventory_kind": "bff", "entries": []})
    _write_json(root, "docs/operations.json", {"schema_version": 1, "entries": []})
    revision = _commit_frontend(web)
    report = scan_web_api_routes(
        [web],
        legacy_index=set(),
        bff_index=set(),
        exclusions=(),
        frontend_revision=revision,
    )
    artifact = root / "docs/web-routes.json"
    artifact.write_text(report.json(), encoding="utf-8", newline="\n")
    return web, artifact


def test_completion_distinguishes_missing_stored_web_occurrence(tmp_path: Path) -> None:
    root = _complete_repository(tmp_path)
    web, artifact = _configure_complete_web_evidence(
        root,
        "fetch('/api/v1/capabilities/test.capability_1:invoke', { method: 'POST' });\n",
    )
    document = json.loads(artifact.read_text(encoding="utf-8"))
    document["routes"] = []
    document["counts"]["capability"] = 0
    _write_json(root, "docs/web-routes.json", document)

    report = evaluate_completion(root, mode="strict", web_root=web)

    assert "web_route_inventory_occurrence_drift:1" in report.failed
    assert "web_route_inventory_revision_drift:1" not in report.failed


def test_completion_distinguishes_frontend_revision_drift(tmp_path: Path) -> None:
    root = _complete_repository(tmp_path)
    web, artifact = _configure_complete_web_evidence(
        root,
        "fetch('/api/v1/capabilities/test.capability_1:invoke', { method: 'POST' });\n",
    )
    document = json.loads(artifact.read_text(encoding="utf-8"))
    document["frontend_revision"] = "f" * 40
    _write_json(root, "docs/web-routes.json", document)

    report = evaluate_completion(root, mode="strict", web_root=web)

    assert "web_route_inventory_revision_drift:1" in report.failed
    assert "web_route_inventory_occurrence_drift:1" not in report.failed


def test_completion_blocks_stored_unresolved_web_occurrence(tmp_path: Path) -> None:
    root = _complete_repository(tmp_path)
    web, _artifact = _configure_complete_web_evidence(
        root, "fetch('/api/tasks');\n"
    )

    report = evaluate_completion(root, mode="strict", web_root=web)

    assert "web_route_inventory_unresolved:1" in report.failed


def test_strict_completion_blocks_stored_unresolved_without_frontend_root(
    tmp_path: Path,
) -> None:
    root = _complete_repository(tmp_path)
    _web, _artifact = _configure_complete_web_evidence(
        root, "fetch('/api/tasks');\n"
    )

    report = evaluate_completion(root, mode="strict")

    assert report.web_consumer_bypasses == 1
    assert "web_route_inventory_unresolved:1" in report.failed
    assert "web_consumer_bypasses:1" in report.failed


def test_fresh_web_verification_rejects_missing_frontend_root(tmp_path: Path) -> None:
    root = _complete_repository(tmp_path)

    with pytest.raises(CompletionConfigurationError, match="frontend Git root is missing"):
        evaluate_completion(root, mode="strict", web_root=root / "missing-frontend")


def test_fresh_web_verification_rejects_non_git_frontend_root(tmp_path: Path) -> None:
    root = _complete_repository(tmp_path)
    frontend = root / "frontend"
    frontend.mkdir()
    (frontend / "app.js").write_text("fetch('/api/tasks');\n", encoding="utf-8")

    with pytest.raises(CompletionConfigurationError, match="frontend Git revision"):
        evaluate_completion(root, mode="strict", web_root=frontend)


def test_completion_blocks_unmatched_lexical_api_token(tmp_path: Path) -> None:
    root = _complete_repository(tmp_path)
    web, _artifact = _configure_complete_web_evidence(
        root, "fetch('https://example.test/api/tasks');\n"
    )

    report = evaluate_completion(root, mode="strict", web_root=web)

    assert "web_route_inventory_lexical_unmatched:1" in report.failed


def test_strict_completion_rejects_internally_inconsistent_lexical_audit(
    tmp_path: Path,
) -> None:
    root = _complete_repository(tmp_path)
    _web, artifact = _configure_complete_web_evidence(
        root,
        "fetch('/api/v1/capabilities/test.capability_1:invoke', { method: 'POST' });\n",
    )
    document = json.loads(artifact.read_text(encoding="utf-8"))
    document["lexical_audit"]["token_count"] += 1
    _write_json(root, "docs/web-routes.json", document)

    report = evaluate_completion(root, mode="strict")

    assert "web_route_inventory_lexical_invalid:1" in report.failed


def test_completion_accepts_byte_identical_canonical_web_evidence(tmp_path: Path) -> None:
    root = _complete_repository(tmp_path)
    web, _artifact = _configure_complete_web_evidence(
        root,
        "fetch('/api/v1/capabilities/test.capability_1:invoke', { method: 'POST' });\n",
    )

    report = evaluate_completion(root, mode="strict", web_root=web)

    assert not any(reason.startswith("web_route_inventory_") for reason in report.failed)


def test_completion_checks_optional_legacy_route_inventory_deadlines(tmp_path: Path) -> None:
    root = _complete_repository(tmp_path)
    configuration_path = root / "backend/governance/capability_v2_completion.json"
    configuration = json.loads(configuration_path.read_text(encoding="utf-8"))
    configuration["legacy_route_inventory_artifact"] = "docs/legacy-routes.json"
    _write_json(root, "backend/governance/capability_v2_completion.json", configuration)
    _write_json(root, "docs/legacy-routes.json", {
        "inventory_kind": "legacy_rest",
        "entries": [{
            "route_path": "/api/legacy", "method": "GET", "owner": "craft",
            "migration_target_capability": "craft.legacy.read",
            "migration_deadline": "2020-01-01", "source": "web/app.js",
        }],
    })

    report = evaluate_completion(root, mode="strict")

    assert "legacy_route_inventory_artifact:expired:GET:/api/legacy" in report.failed


def test_frozen_review_exposes_exact_capability_ids() -> None:
    root = Path(__file__).resolve().parents[2]

    review = FrozenCoverageReview(root)

    base_ids = review.capability_ids("base")
    assert "base.annotation.read" in base_ids
    assert "base.annotation.change.apply" in base_ids
    assert "system.worker.outbox.health" not in base_ids
    assert "plugin.upgrade.finish" not in base_ids
    assert len(base_ids) == 36

    integration_ids = review.capability_ids("integration")
    assert "integration.connector.create" in integration_ids
    assert "integration.mapping.preview" in integration_ids
    assert "integration.sync.start" in integration_ids
    assert len(integration_ids) == 13


def test_completion_cli_reports_complete_in_progress_and_strict_modes() -> None:
    root = Path(__file__).resolve().parents[2]
    script = root / "backend/scripts/check_capability_v2_completion.py"

    progress = subprocess.run(
        [sys.executable, str(script), "--mode", "progress"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    strict = subprocess.run(
        [sys.executable, str(script), "--mode", "strict"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )

    assert progress.returncode == 0
    assert json.loads(progress.stdout)["complete"] is True
    assert strict.returncode == 1
    assert json.loads(strict.stdout)["complete"] is False
    assert any(
        reason.startswith("web_route_inventory_unresolved:")
        for reason in json.loads(strict.stdout)["failed"]
    )
    assert json.loads(strict.stdout)["cross_domain_sql"] == 0


def test_completion_cli_static_only_alias_runs_the_strict_static_gate() -> None:
    root = Path(__file__).resolve().parents[2]
    script = root / "backend/scripts/check_capability_v2_completion.py"

    result = subprocess.run(
        [sys.executable, str(script), "--static-only"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1, result.stderr
    assert json.loads(result.stdout)["complete"] is False
    assert any(
        reason.startswith("web_route_inventory_unresolved:")
        for reason in json.loads(result.stdout)["failed"]
    )
