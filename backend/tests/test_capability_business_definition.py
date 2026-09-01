from __future__ import annotations

import pytest

from backend.capability_v2.business_definition import (
    business_definition_hash,
    is_generated_business_effect,
)
from backend.capability_v2.contracts import (
    AutomationLevel,
    CapabilityDescriptorV2,
    ExposurePolicy,
)


@pytest.fixture
def descriptor_factory():
    def factory(**overrides: object) -> CapabilityDescriptorV2:
        values: dict[str, object] = {
            "id": "person.height.write",
            "major_version": 1,
            "owner_domain": "person",
            "title": "Write person height",
            "description": "Record a normalized person height.",
            "use_when": "A caller needs to record a person's height.",
            "do_not_use_when": "A caller needs a different person attribute.",
            "business_effect": "A person's normalized height is available for personnel decisions.",
            "exposure": ExposurePolicy(api=True),
            "automation_level": AutomationLevel.A2,
            "authorization_policy": "person.height.write",
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
            "output_schema": {"type": "object", "properties": {}, "additionalProperties": False},
            "schema_hash": "sha256:" + "a" * 64,
            "provider_ref": "person.provider.height",
            "side_effects": "Stores the normalized height in the person profile.",
        }
        values.update(overrides)
        return CapabilityDescriptorV2(**values)

    return factory


def test_business_invariant_and_no_rule_reason_are_exclusive(descriptor_factory):
    with pytest.raises(ValueError, match="business_rule_declaration_conflict"):
        descriptor_factory(
            business_invariants=(
                {
                    "rule_id": "person.height.range",
                    "version": 1,
                    "statement": "Height is 0.3m to 2.5m",
                    "applies_when": "height changes",
                    "enforcement_ref": "person.provider:validate_height",
                    "error_code": "invalid_person_height",
                    "test_refs": ("tests/test_height.py::test_range",),
                },
            ),
            no_business_invariant_reason="No rules",
        )


def test_semantic_hash_ignores_description_formatting(descriptor_factory):
    left = descriptor_factory(description="First description")
    right = descriptor_factory(description="Second description")

    assert business_definition_hash(left) == business_definition_hash(right)


def test_generated_business_effect_detection_rejects_catalog_templates():
    description = "Store a normalized height measurement."

    assert is_generated_business_effect(description, description)
    assert is_generated_business_effect(f"Business outcome: {description}", description)
    assert is_generated_business_effect("Execute the governed person.height.write outcome.", description)
    assert not is_generated_business_effect(
        "Personnel planning can use one normalized, traceable height measurement.", description
    )
