from __future__ import annotations

from pathlib import Path

from backend.base import provider as base_provider
from backend.capability_v2.bootstrap import build_capability_registry
from backend.capability_governance_test.contracts import ALL_IDS, provider_artifact
from backend.capability_v2.provider_loader import hash_domain_artifact
from backend.scripts.build_capability_governance_catalog import current_release


ROOT = Path(__file__).resolve().parents[2]


def test_product_registry_is_unchanged_without_test_extension():
    """The official catalog must not load test-governance registrations by default."""
    product = build_capability_registry(ROOT)
    test = build_capability_registry(ROOT, include_test_governance=True)
    assert ("base.capability_registry.search", 1) not in product.keys()
    assert ("base.capability_registry.search", 1) in test.keys()


def test_test_governance_extension_has_exact_base_owned_contracts():
    registry = build_capability_registry(ROOT, include_test_governance=True)
    registrations = {key: registry.get(*key) for key in registry.keys() if key[0] in ALL_IDS}

    assert set(registrations) == {(capability_id, 1) for capability_id in ALL_IDS}
    assert len(registrations) == 14
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


def test_test_governance_registration_restores_base_schema_maps():
    inputs_before = dict(base_provider.INPUT_SCHEMAS)
    outputs_before = dict(base_provider.OUTPUT_SCHEMAS)

    build_capability_registry(ROOT, include_test_governance=True)

    assert dict(base_provider.INPUT_SCHEMAS) == inputs_before
    assert dict(base_provider.OUTPUT_SCHEMAS) == outputs_before
