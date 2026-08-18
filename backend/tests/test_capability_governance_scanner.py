from __future__ import annotations

import json
import importlib
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

from backend.capability_governance_test.config import GovernanceSettings
from backend.capability_governance_test.graph import ImplementationGraph, node_key
from backend.capability_governance_test.scanner import GovernanceScanner, ScanPolicyError


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


def test_dynamic_table_expression_becomes_unresolved_evidence() -> None:
    """A dynamic SQL/table expression must never manufacture a table edge."""
    document = scan_fixture(FIXTURES / "invalid_provider")

    assert any(node.node_type == "unresolved_binding" for node in document.nodes)
    assert not any(node.node_type == "database_table" for node in document.nodes)
    assert not any(binding.binding_type == "implemented_by" for binding in document.bindings)
    assert any(node.source_symbol == "provider_not_resolved" for node in document.nodes)


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
