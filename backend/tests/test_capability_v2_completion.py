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
from backend.tests.capability_completion_support import FrozenCoverageReview


DOMAIN_IDS = (
    "agent",
    "base",
    "craft",
    "digital_model",
    "factory",
    "integration",
    "knowledge",
    "local_runtime",
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


def test_current_repository_reports_progress_without_claiming_completion() -> None:
    root = Path(__file__).resolve().parents[2]

    report = evaluate_completion(root, mode="progress")

    assert report.complete is False
    assert report.independent_domains == 10
    assert report.cross_domain_sql == 312
    assert report.internal_imports == 6
    assert "missing_domain:agent" in report.failed
    assert "missing_domain:factory" not in report.failed
    assert "missing_domain:integration" not in report.failed
    assert "domain_not_independent:local_runtime:migration_path" not in report.failed
    assert "missing_domain:project_management" not in report.failed
    assert "domain_not_independent:base:migration_path" not in report.failed


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


def test_completion_cli_reports_progress_and_fails_strict() -> None:
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
    assert json.loads(progress.stdout)["complete"] is False
    assert strict.returncode == 1
    assert json.loads(strict.stdout)["cross_domain_sql"] == 312
