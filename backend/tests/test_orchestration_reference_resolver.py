from pathlib import Path

import pytest

from plugins.agent.agent_backend.orchestration.reference_resolver import (
    CatalogReferenceResolver,
    ReferenceResolver,
    UntrustedCapabilityReference,
)


def test_catalog_reference_resolver_uses_server_catalog_for_capability_gid():
    from backend.capability_v2.bootstrap import build_capability_registry

    root = Path(__file__).resolve().parents[2]
    registry = build_capability_registry(root)
    descriptor = next(
        item.descriptor for item in registry.snapshot()
        if item.spec.id == "agent.orchestration.panorama.read"
    )
    release = __import__("json").loads(
        (root / "docs/governance/capability-catalog-release.json").read_text(encoding="utf-8")
    )
    artifact = next(item for item in release["provider_artifacts"] if item["plugin_id"] == "official.agent")
    registry.bind_provider_artifact("agent", type("Artifact", (), artifact)())
    resolver = CatalogReferenceResolver(registry)

    resolved = resolver.resolve_capability_binding(descriptor.capability_version_gid, "u1")

    assert resolved["capability_version_gid"] == descriptor.capability_version_gid
    assert resolved["provider_ref"] == "agent.provider"
    assert resolved["catalog_release_gid"] == release["release_id"]


def trusted_capability(**overrides):
    return {
        "capability_version_gid": "cv2_read",
        "capability_id": "craft.bop.read",
        "major_version": 1,
        "lifecycle_status": "stable",
        "provider_ref": "craft.provider",
        "gateway_ref": "agent.gateway.v1",
        "catalog_release_gid": "release-1",
        "artifact_hash": "sha256:abc",
        "catalog_member": True,
        "artifact_match": True,
        "authorized": True,
        **overrides,
    }


def test_reference_resolver_marks_external_authority_and_deep_link():
    resolver = ReferenceResolver(capability_lookup=lambda gid, actor: {"label": "BOP Read", "resolved": True})

    refs = resolver.resolve_many([
        {"ref_type": "capability", "ref_gid": "cv2_read"},
        {"ref_type": "data", "ref_gid": "data-1"},
        {"ref_type": "rule", "ref_gid": "rule-1"},
        {"ref_type": "knowledge", "ref_gid": "knowledge-1"},
        {"ref_type": "ontology", "ref_gid": "ontology-1"},
        {"ref_type": "code", "ref_gid": "provider.py"},
    ], "u1")

    assert refs[0]["edit_authority"] == "capability_governance"
    assert refs[0]["deep_link"].startswith("/web/admin/capabilities.html")
    assert [item["edit_authority"] for item in refs[1:]] == [
        "data", "rule_governance", "knowledge", "ontology", "code",
    ]
    assert all(item["read_only"] for item in refs)


def test_capability_lookup_failure_is_unresolved_not_guessed():
    resolver = ReferenceResolver()

    resolved = resolver.resolve_many([{"ref_type": "capability", "ref_gid": "cv2_unknown"}], "u1")

    assert resolved[0]["resolved"] is False


def test_capability_binding_is_an_exact_trusted_catalog_projection():
    resolver = ReferenceResolver(capability_lookup=lambda _gid, _actor: trusted_capability())

    resolved = resolver.resolve_capability_binding("cv2_read", "u1")

    assert resolved["capability_id"] == "craft.bop.read"
    assert resolved["provider_ref"] == "craft.provider"
    assert "catalog_member" not in resolved


@pytest.mark.parametrize(
    "overrides",
    [
        {"lifecycle_status": "candidate"},
        {"catalog_member": False},
        {"artifact_match": False},
        {"authorized": False},
        {"provider_ref": ""},
        {"capability_version_gid": "cv2_other"},
    ],
)
def test_capability_binding_fails_closed_on_untrusted_catalog_fact(overrides):
    resolver = ReferenceResolver(
        capability_lookup=lambda _gid, _actor: trusted_capability(**overrides)
    )

    with pytest.raises(UntrustedCapabilityReference):
        resolver.resolve_capability_binding("cv2_read", "u1")


def test_resolver_has_no_sql_or_domain_repository_dependency():
    source = (Path(__file__).resolve().parents[2] / "plugins/agent/agent_backend/orchestration/reference_resolver.py").read_text(encoding="utf-8")

    assert "SELECT " not in source.upper()
    assert "workmanship_" not in source
