from __future__ import annotations

from pathlib import Path

from backend.base import provider as base_provider
from backend.capability_v2.bootstrap import (
    build_capability_registry,
    build_test_governance_capability_registry,
    get_capability_registry,
    reset_capability_registry_for_tests,
)
from backend.capability_governance_test.contracts import ALL_IDS, provider_artifact
from backend.capability_v2.provider_loader import hash_domain_artifact
from backend.capability_v2.gateway import configure_default_gateway
from backend.scripts.build_capability_governance_catalog import current_release


ROOT = Path(__file__).resolve().parents[2]


def test_product_registry_is_unchanged_without_test_extension():
    """The official catalog must not load test-governance registrations by default."""
    product = build_capability_registry(ROOT)
    test = build_capability_registry(ROOT, include_test_governance=True)
    assert ("base.capability_registry.search", 1) not in product.keys()
    assert ("base.capability_registry.search", 1) in test.keys()


def test_test_governance_profile_injects_a_functional_service_not_none():
    registry = build_test_governance_capability_registry(ROOT)

    result = registry.get("base.capability_registry.search").handler({"query": "capability"}, object())

    assert result["capability_id"] == "base.capability_registry.search"
    assert result["status"] == "completed"
    assert result["items"] == []
    assert result["total"] == 0
    assert result["product_capability_total"] == 0
    assert result["governance_extension_capability_total"] == 0


def test_test_governance_extension_has_exact_base_owned_contracts():
    registry = build_capability_registry(ROOT, include_test_governance=True)
    registrations = {key: registry.get(*key) for key in registry.keys() if key[0] in ALL_IDS}

    assert set(registrations) == {(capability_id, 1) for capability_id in ALL_IDS}
    assert len(registrations) == len(ALL_IDS)
    assert provider_artifact(ROOT).plugin_id == "test.governance"
    for registration in registrations.values():
        assert registration.spec.owner == "base"
        assert registration.descriptor is not None
        assert registration.descriptor.owner_domain == "base"
        assert registration.descriptor.input_schema["additionalProperties"] is False
        assert registration.descriptor.output_schema["additionalProperties"] is False


def test_governance_write_contracts_require_idempotency_and_confirmation():
    registry = build_capability_registry(ROOT, include_test_governance=True)
    for capability_id in ALL_IDS:
        registration = registry.get(capability_id, 1)
        if registration.spec.risk.value != "read":
            assert registration.spec.idempotent is True
            assert registration.spec.confirmation == "admin"
            assert registration.descriptor.idempotency_policy == "required"
            assert registration.descriptor.confirmation_policy == "admin"


def test_governance_provider_artifact_uses_the_canonical_extension_hash():
    release = current_release()

    assert release.provider_artifacts[0].artifact_hash == hash_domain_artifact(
        ROOT, "backend/capability_governance_test",
    )


def test_governance_catalog_artifact_matches_registered_extension():
    """Every registered governance capability must be resolvable by HTTP."""
    artifact = (ROOT / "docs/governance/test-extension/capability-governance-catalog-release.json").read_text(encoding="utf-8")
    from backend.capability_v2.catalog import CatalogRelease

    checked = CatalogRelease.model_validate_json(artifact)
    expected = current_release()
    assert checked.release_id == expected.release_id
    assert checked.catalog_hash == expected.catalog_hash
    assert {item.id for item in checked.descriptors} == set(ALL_IDS)


def test_test_governance_registration_restores_base_schema_maps():
    inputs_before = dict(base_provider.INPUT_SCHEMAS)
    outputs_before = dict(base_provider.OUTPUT_SCHEMAS)

    build_capability_registry(ROOT, include_test_governance=True)

    assert dict(base_provider.INPUT_SCHEMAS) == inputs_before
    assert dict(base_provider.OUTPUT_SCHEMAS) == outputs_before


def test_http_gateway_overlays_governance_catalog_only_for_explicit_test_profile(monkeypatch):
    monkeypatch.setenv("AI00_GID_MACHINE_ID", "41")
    monkeypatch.setenv("AI00_DEPLOYMENT_PROFILE", "test-governance")
    test_gateway = configure_default_gateway(build_capability_registry(ROOT, include_test_governance=True))

    assert test_gateway.catalog().descriptor("base.capability_registry.search", 1) is not None
    assert test_gateway.catalog().descriptor("craft.bop.version.list", 1) is not None

    monkeypatch.delenv("AI00_DEPLOYMENT_PROFILE")
    product_gateway = configure_default_gateway(build_capability_registry(ROOT))
    assert product_gateway.catalog().descriptor("base.capability_registry.search", 1) is None
    assert product_gateway.catalog().descriptor("craft.bop.version.list", 1) is not None


def test_default_test_governance_bootstrap_wires_scan_and_projection_runtime(monkeypatch):
    """The explicit local profile must expose a usable service, not placeholders."""
    monkeypatch.setenv("AI00_DEPLOYMENT_PROFILE", "test-governance")
    monkeypatch.setenv("AI00_GID_MACHINE_ID", "41")
    monkeypatch.setenv("AI00_PYTEST_OFFLINE", "1")
    reset_capability_registry_for_tests()
    try:
        registry = get_capability_registry()
        scan = registry.get("base.capability_scan.run").handler(
            {"code_revision": "test-bootstrap", "idempotency_key": "bootstrap-scan"}, object()
        )
        assert scan["status"] == "completed"
        search = registry.get("base.capability_registry.search").handler(
            {"query": "base.", "limit": 2}, object()
        )
        assert search["status"] == "completed"
        assert len(search["items"]) == 2
        graph = registry.get("base.capability_graph.get").handler(
            {"target_gid": scan["snapshot_gid"], "max_depth": 2, "max_nodes": 500}, object()
        )
        assert any(item.get("binding_type") == "implemented_by" for item in graph["bindings"])
        assert any(item.get("binding_type") == "tested_by" for item in graph["bindings"])
    finally:
        reset_capability_registry_for_tests()
