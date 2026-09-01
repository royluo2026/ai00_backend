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
