from __future__ import annotations

from backend.capability_v2.provider_contracts import CapabilityRisk, CapabilitySpec

from ..application.outcomes import knowledge_outcomes
from ..provider import register_capability


CAPABILITY_IDS = (
    "knowledge.entry.change.apply", "knowledge.space.change.apply",
    "knowledge.document.archive", "knowledge.personalization.change.apply",
    "knowledge.personalization.read",
)
SCHEMA = {"type": "object", "required": ["operation", "arguments"], "properties": {"operation": {"type": "string"}, "arguments": {}}, "additionalProperties": False}


def register_reviewed_capabilities(registry):
    for capability_id in CAPABILITY_IDS:
        read = capability_id.endswith(".read")
        spec = CapabilitySpec(
            id=capability_id, owner="knowledge", description=f"Execute {capability_id}.",
            use_when="A governed consumer needs this Knowledge outcome.", do_not_use_when="The resource belongs to another domain.",
            risk=CapabilityRisk.READ if read else CapabilityRisk.WRITE, confirmation="none" if read else "user",
            permissions=("knowledge.read",) if read else ("knowledge.write",), input_schema=SCHEMA,
            output_schema={"type": "object", "required": ["data"], "properties": {"data": {}}}, tags=("knowledge",), plugin_callable=True,
        )
        def handler(payload, context, *, _id=capability_id): return {"data": knowledge_outcomes.invoke(_id, payload, context)}
        register_capability(registry, spec, handler)

