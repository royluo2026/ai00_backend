"""Canonical, author-controlled business-definition projections."""
from __future__ import annotations

import hashlib
import json

from .contracts import CapabilityDescriptorV2


def is_generated_business_effect(value: object, description: object) -> bool:
    effect = str(value or "").strip()
    source = str(description or "").strip()
    lowered = effect.lower()
    return (
        not effect
        or effect == source
        or (effect.startswith("Business outcome: ") and effect[len("Business outcome: "):].strip() == source)
        or ("execute the governed" in lowered and "outcome" in lowered)
    )


def business_definition_projection(descriptor: CapabilityDescriptorV2) -> dict[str, object]:
    return {
        "capability_id": descriptor.id,
        "major_version": descriptor.major_version,
        "business_effect": (descriptor.business_effect or "").strip(),
        "business_acceptance_criteria": list(descriptor.business_acceptance_criteria),
        "business_invariants": [item.model_dump(mode="json") for item in descriptor.business_invariants],
        "no_business_invariant_reason": descriptor.no_business_invariant_reason,
        "input_schema": descriptor.input_schema,
        "output_schema": descriptor.output_schema,
        "provider_ref": descriptor.provider_ref,
        "side_effects": descriptor.side_effects,
    }


def business_definition_hash(descriptor: CapabilityDescriptorV2) -> str:
    raw = json.dumps(
        business_definition_projection(descriptor),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def substantive_business_definition_errors(
    descriptor: CapabilityDescriptorV2,
) -> tuple[str, ...]:
    """Return Task 1 author-contract gaps that prevent V2.5 approval."""
    errors: set[str] = set()
    if is_generated_business_effect(descriptor.business_effect, descriptor.description):
        errors.add("business_effect_invalid")
    criteria = descriptor.business_acceptance_criteria
    if not criteria or any(not item.strip() for item in criteria):
        errors.add("business_acceptance_criteria_invalid")
    if descriptor.business_invariants:
        identities: set[tuple[str, int]] = set()
        for rule in descriptor.business_invariants:
            identity = (rule.rule_id, rule.version)
            if identity in identities or any(not str(value).strip() for value in (
                rule.rule_id, rule.statement, rule.applies_when,
                rule.enforcement_ref, rule.error_code, *rule.test_refs,
            )):
                errors.add("business_invariant_invalid")
            identities.add(identity)
    elif not str(descriptor.no_business_invariant_reason or "").strip():
        errors.add("business_rule_declaration_missing")
    return tuple(sorted(errors))
