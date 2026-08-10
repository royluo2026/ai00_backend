from __future__ import annotations

import pytest

from backend.capabilities.models_next import CapabilitySpec
from backend.capabilities.registry_next import CapabilityRegistry
from backend.capability_v2.v1_adapter import adapt_v1_spec


def _spec() -> CapabilitySpec:
    return CapabilitySpec(
        id="knowledge.test.write",
        owner="knowledge",
        risk="write",
        confirmation="user",
        input_schema={"type": "object", "properties": {}},
        output_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
    )


def test_registration_can_publish_an_explicit_native_v2_descriptor():
    spec = _spec()
    descriptor = adapt_v1_spec(spec).model_copy(update={"lifecycle_status": "stable"})
    registry = CapabilityRegistry()

    registry.register(spec, lambda *_: {"ok": True}, descriptor=descriptor)

    assert registry.get(spec.id).descriptor is descriptor


@pytest.mark.parametrize("field,value", [
    ("id", "knowledge.other.write"),
    ("major_version", 2),
    ("owner_domain", "craft"),
])
def test_native_descriptor_identity_must_match_provider_registration(field: str, value):
    spec = _spec()
    descriptor = adapt_v1_spec(spec).model_copy(update={field: value})
    registry = CapabilityRegistry()

    with pytest.raises(ValueError, match="native_descriptor_identity_mismatch"):
        registry.register(spec, lambda *_: {"ok": True}, descriptor=descriptor)
