from __future__ import annotations

import json
import importlib
import shutil
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

from backend.capability_governance_test.config import GovernanceSettings
from backend.capability_governance_test.graph import ImplementationGraph, node_key
from backend.capability_governance_test.scanner import GovernanceScanner, ScanPolicyError
from backend.scripts.run_capability_governance_scan import run_offline_scan


FIXTURES = Path(__file__).parent / "fixtures" / "capability_governance_scan"


@pytest.fixture
def valid_fixture() -> Path:
    return FIXTURES / "valid"


@pytest.fixture
def settings(valid_fixture: Path) -> GovernanceSettings:
    return GovernanceSettings(
        deployment_profile="test-governance",
        repository_root=valid_fixture,
        allowlisted_relative_roots=("plugins",),
    )


def _fixture_registry() -> tuple[SimpleNamespace, ...]:
    handler = SimpleNamespace(__module__="plugins.craft.craft_backend.provider")
    spec = SimpleNamespace(id="craft.bop.factory.create", version=1)
    return (SimpleNamespace(spec=spec, handler=handler),)


def scan_fixture(root: Path):
    settings = GovernanceSettings(
        deployment_profile="test-governance",
        repository_root=root,
        allowlisted_relative_roots=("plugins",),
    )
    return GovernanceScanner(
        settings,
        product_catalog=json.loads((root / "product_catalog.json").read_text(encoding="utf-8")),
        extension_catalog=json.loads((root / "extension_catalog.json").read_text(encoding="utf-8")),
        domain_manifests=json.loads((root / "official_domains.json").read_text(encoding="utf-8")),
        registry_snapshot=_fixture_registry(),
    ).scan(code_revision="fixture-revision")


def test_scanner_rejects_caller_supplied_absolute_path(settings: GovernanceSettings) -> None:
    """A caller must never steer a scan into its home directory."""
    with pytest.raises(ScanPolicyError, match="scan_path_not_allowlisted"):
        GovernanceScanner(settings).scan_path(Path("C:/Users"))


def test_node_keys_are_posix_and_stable() -> None:
    """Cross-platform source paths describe one immutable graph identity."""
    assert node_key("provider", "craft", "plugins/craft/craft_backend/provider.py", "FactoryProvider") == (
        "provider:craft:plugins/craft/craft_backend/provider.py:FactoryProvider"
    )


def test_graph_links_write_from_gateway_to_table(valid_fixture: Path) -> None:
    """Removing a link in the gateway/provider/port/repository chain breaks this test."""
    document = scan_fixture(valid_fixture)
    result = ImplementationGraph(document.nodes, document.relations, document.bindings)

    assert result.has_path(
        "craft.bop.factory.create@1",
        ["gateway", "provider", "domain_port", "repository", "database_table"],
    )


def test_scan_does_not_execute_scanned_modules_and_preserves_catalog_separation(
    valid_fixture: Path,
) -> None:
    """The fixture has an import-time exception, so AST parsing is the only safe outcome."""
    document = scan_fixture(valid_fixture)

    assert [(item.capability_id, item.major_version) for item in document.capabilities] == [
        ("craft.bop.factory.create", 1),
    ]
    assert document.product_release_id == "product-fixture"
    assert document.extension_release_id == "extension-fixture"


def test_scanner_can_bind_registry_snapshot_after_construction(valid_fixture: Path) -> None:
    """A long-lived service can attach the authoritative registry before scanning."""
    settings = GovernanceSettings(
        deployment_profile="test-governance",
        repository_root=valid_fixture,
        allowlisted_relative_roots=("plugins",),
    )
    scanner = GovernanceScanner(
        settings,
        product_catalog=json.loads((valid_fixture / "product_catalog.json").read_text(encoding="utf-8")),
        extension_catalog=json.loads((valid_fixture / "extension_catalog.json").read_text(encoding="utf-8")),
        domain_manifests=json.loads((valid_fixture / "official_domains.json").read_text(encoding="utf-8")),
    )

    scanner.bind_registry_snapshot(_fixture_registry())
    document = scanner.scan(code_revision="bound-after-construction")

    assert any(binding.binding_type == "implemented_by" for binding in document.bindings)


def test_scanner_matches_registry_package_module_to_provider_source() -> None:
    """Registry handlers may expose a package module while source lives in provider.py."""
    assert GovernanceScanner.registry_module_matches_source(
        "craft_backend.capabilities",
        "plugins/craft/craft_backend/capabilities/provider.py",
    )
    assert GovernanceScanner.registry_module_matches_source(
        "craft_backend.capabilities.rule_descriptors",
        "plugins/craft/craft_backend/capabilities/provider.py",
    )
    assert GovernanceScanner.registry_module_matches_source(
        "knowledge_backend.capabilities.knowledge_next",
        "plugins/knowledge/knowledge_backend/provider.py",
    )
    assert GovernanceScanner.registry_module_matches_source(
        "backend.base.approval",
        "backend/base/provider.py",
    )
    assert GovernanceScanner.registry_module_matches_source(
        "backend.capabilities.system_shared_next",
        "backend/base/provider.py",
    )
    assert GovernanceScanner.registry_module_matches_source(
        "backend.plugin_platform.storage",
        "backend/base/provider.py",
    )
    assert not GovernanceScanner.registry_module_matches_source(
        "craft_backend.capabilities",
        "plugins/craft/craft_backend/application/outcomes.py",
    )


def test_dynamic_table_expression_becomes_unresolved_evidence() -> None:
    """A dynamic SQL/table expression must never manufacture a table edge."""
    document = scan_fixture(FIXTURES / "invalid_provider")

    assert any(node.node_type == "unresolved_binding" for node in document.nodes)
    assert not any(node.node_type == "database_table" for node in document.nodes)
    assert not any(binding.binding_type == "implemented_by" for binding in document.bindings)
    assert any(node.source_symbol == "provider_not_resolved" for node in document.nodes)


def test_retired_promotion_placeholders_are_not_public_exposure_findings() -> None:
    report = run_offline_scan(Path(".runtime/promotion-retirement-scan.json"))
    nodes = {item["canonical_key"]: item for item in report["snapshot"]["nodes"]}

    assert not any(
        node["source_symbol"] in {"get_promote_placeholder", "get_issue_promote_placeholder"}
        for node in nodes.values()
        if node["node_type"] in {"rest_route", "legacy_api"}
    )


def test_partial_static_table_expression_is_unresolved() -> None:
    """A literal fragment concatenated with a runtime value is not a table declaration."""
    document = scan_fixture(FIXTURES / "invalid_provider")

    assert not any(node.source_symbol == "workmanship_craft_bop_factories" for node in document.nodes)
    assert any(node.metadata.get("reason", "").startswith("dynamic_table") for node in document.nodes)


def test_scanner_emits_declared_exposure_runtime_and_migration_categories(valid_fixture: Path) -> None:
    """Removing a supported category or cross-file table relation breaks graph coverage."""
    document = scan_fixture(valid_fixture)
    node_types = {node.node_type for node in document.nodes}

    assert {
        "migration", "rest_route", "legacy_api", "mount_binding", "agent_tool", "mcp_tool",
        "worker", "local_runtime", "test_case",
    } <= node_types
    assert any(relation.relation_type == "migrates_table" for relation in document.relations)
    assert any(relation.relation_type == "persists_to" for relation in document.relations)
    assert any(
        any(path.endswith("0002_factory_schema.sql") for path in node.metadata.get("declared_by", ()))
        for node in document.nodes if node.node_type == "database_table"
    )


def test_scanner_binds_explicit_capability_route_and_excludes_route_models(valid_fixture: Path) -> None:
    """Only decorated handlers expose capabilities; route models remain ordinary AST nodes."""
    document = scan_fixture(valid_fixture)

    assert any(
        binding.binding_type == "exposed_by"
        and binding.capability_id == "craft.bop.factory.create"
        and binding.node_canonical_key.endswith("routes.py:create_factory")
        for binding in document.bindings
    )
    assert any(
        binding.binding_type == "exposed_by"
        and binding.capability_id == "craft.bop.factory.create"
        and binding.node_canonical_key.endswith("routes.py:create_factory_via_helper")
        for binding in document.bindings
    )
    assert not any(
        node.node_type == "rest_route" and node.canonical_key.endswith(":routes.py:CreateFactoryBody")
        for node in document.nodes
    )
    assert not any(
        node.node_type == "rest_route" and node.source_symbol == "retired_factory_route"
        for node in document.nodes
    )


def test_scanner_binds_explicit_capability_legacy_api(tmp_path: Path, valid_fixture: Path) -> None:
    root = tmp_path / "legacy-binding"
    shutil.copytree(valid_fixture, root)
    legacy = root / "plugins/craft/craft_backend/legacy_api.py"
    legacy.write_text(
        "from fastapi import APIRouter\nrouter = APIRouter()\n@router.get('/legacy')\n"
        "def legacy_factory_route():\n    return {'capability': 'craft.bop.factory.create'}\n",
        encoding="utf-8",
    )
    document = scan_fixture(root)
    assert any(
        binding.binding_type == "exposed_by"
        and binding.capability_id == "craft.bop.factory.create"
        and binding.node_canonical_key.endswith("legacy_api.py:legacy_factory_route")
        for binding in document.bindings
    )


def test_scanner_binds_explicit_acceptance_manifest_cases(tmp_path: Path, valid_fixture: Path) -> None:
    """Only executable manifest node ids create tested_by evidence."""
    root = tmp_path / "acceptance-manifest"
    shutil.copytree(valid_fixture, root)
    manifest = {
        "schema_version": 1,
        "catalog_release": "product-fixture",
        "mandatory_cases": ["success"],
        "capabilities": {
            "craft.bop.factory.create@1": {
                "success": (
                    "plugins/craft/craft_backend/tests/test_factory.py::"
                    "test_success_case[craft.bop.factory.create@1]"
                ),
            },
        },
    }
    manifest_path = root / "acceptance.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    document = GovernanceScanner(
        GovernanceSettings(
            deployment_profile="test-governance",
            repository_root=root,
            allowlisted_relative_roots=("plugins",),
        ),
        product_catalog=json.loads((root / "product_catalog.json").read_text(encoding="utf-8")),
        extension_catalog=json.loads((root / "extension_catalog.json").read_text(encoding="utf-8")),
        domain_manifests=json.loads((root / "official_domains.json").read_text(encoding="utf-8")),
        registry_snapshot=_fixture_registry(),
        acceptance_manifest=manifest,
        acceptance_manifest_path="acceptance.json",
    ).scan(code_revision="fixture-acceptance")

    test_nodes = [node for node in document.nodes if node.node_type == "test_case"]
    assert any("test_factory.py" in node.source_path for node in test_nodes)
    assert any(
        binding.binding_type == "tested_by"
        and binding.capability_id == "craft.bop.factory.create"
        and binding.node_canonical_key in {node.canonical_key for node in test_nodes}
        for binding in document.bindings
    )


def test_schema_path_sql_is_not_promoted_to_a_migration(valid_fixture: Path) -> None:
    """Only the manifest migration_path may create migration evidence."""
    document = scan_fixture(valid_fixture)

    assert not any(
        node.node_type == "migration" and node.source_path.endswith("0002_factory_schema.sql")
        for node in document.nodes
    )
    assert not any(
        relation.relation_type == "migrates_table"
        and "0002_factory_schema.sql" in relation.from_canonical_key
        for relation in document.relations
    )


def test_imported_literal_table_constant_does_not_create_dynamic_evidence(valid_fixture: Path) -> None:
    """A unique imported literal table constant is resolvable static evidence."""
    document = scan_fixture(valid_fixture)

    assert not any(
        node.node_type == "unresolved_binding"
        and node.source_path.endswith("factory_repository.py")
        and node.metadata.get("reason", "").startswith("dynamic_table")
        for node in document.nodes
    )


def test_offline_runner_does_not_require_provider_bootstrap(monkeypatch: pytest.MonkeyPatch) -> None:
    """The offline scanner must load without an import-capable provider bootstrap."""
    blocked_bootstrap = ModuleType("backend.capability_v2.bootstrap")
    monkeypatch.setitem(sys.modules, "backend.capability_v2.bootstrap", blocked_bootstrap)
    sys.modules.pop("backend.scripts.run_capability_governance_scan", None)

    runner = importlib.import_module("backend.scripts.run_capability_governance_scan")

    assert callable(runner.run_offline_scan)


def test_offline_runner_attaches_authoritative_registry_bindings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Offline snapshots must include implementation bindings from the official registry."""
    runner = importlib.import_module("backend.scripts.run_capability_governance_scan")
    output = runner.REPOSITORY_ROOT / ".runtime" / "pytest-offline-scan-bindings.json"
    try:
        report = runner.run_offline_scan(output)
        binding_types = {binding["binding_type"] for binding in report["snapshot"]["bindings"]}
        assert "implemented_by" in binding_types
    finally:
        output.unlink(missing_ok=True)


def test_snapshot_hash_is_repeatable_and_does_not_include_generated_identity(
    valid_fixture: Path,
) -> None:
    """Changing scan order or generated persistence IDs must not perturb a snapshot."""
    first = scan_fixture(valid_fixture)
    second = scan_fixture(valid_fixture)

    assert first.snapshot_hash == second.snapshot_hash
    assert first.snapshot_hash.startswith("sha256:")
    assert [node.canonical_key for node in first.nodes] == sorted(
        node.canonical_key for node in first.nodes
    )


def test_offline_cli_emits_blocked_report_and_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    runner = importlib.import_module("backend.scripts.run_capability_governance_scan")
    output = tmp_path / "blocked-scan.json"

    def blocked_scan(destination: Path) -> dict[str, object]:
        report = {
            "status": "blocked", "official_domain_count": 0,
            "product_descriptor_count": 0, "stable_product_descriptor_count": 0,
            "extension_descriptor_count": 0,
            "snapshot": {"snapshot_hash": "sha256:blocked", "scan_status": "blocked"},
        }
        destination.write_text(json.dumps(report), encoding="utf-8")
        return report

    monkeypatch.setattr(runner, "run_offline_scan", blocked_scan)

    result = runner.main(["--offline", "--output", str(output)])

    assert result == 1
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "blocked"
    assert json.loads(capsys.readouterr().out)["scan_status"] == "blocked"


def test_offline_cli_persists_real_catalog_validation_failure_before_exit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    runner = importlib.import_module("backend.scripts.run_capability_governance_scan")
    invalid_catalog = tmp_path / "invalid-catalog.json"
    invalid_catalog.write_text('{"schema_version":"invalid"}', encoding="utf-8")
    output = tmp_path / "blocked-preflight.json"
    monkeypatch.setattr(runner, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(runner, "PRODUCT_CATALOG", invalid_catalog)

    result = runner.main(["--offline", "--output", str(output)])

    report = json.loads(output.read_text(encoding="utf-8"))
    finding = report["snapshot"]["scan_findings"][0]
    assert result == 1
    assert report["status"] == "blocked"
    assert report["snapshot"]["scan_status"] == "blocked"
    assert finding == {
        "category": "configuration",
        "code": "scan_configuration_error",
        "message": "product_catalog_validation_error",
        "severity": "blocking",
        "source_path": "product_catalog",
    }
    assert json.loads(capsys.readouterr().out)["scan_status"] == "blocked"
