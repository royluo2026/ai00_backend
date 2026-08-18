from __future__ import annotations

import json
from pathlib import Path

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
        registry_snapshot=(),
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
