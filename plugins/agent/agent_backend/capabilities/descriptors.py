from __future__ import annotations

from backend.capability_v2.provider_contracts import CapabilityRisk, CapabilitySpec
from .contracts import CAPABILITY_IDS, INPUT_SCHEMAS, OUTPUT_SCHEMAS


def specs() -> tuple[CapabilitySpec, ...]:
    result = []
    for capability_id in CAPABILITY_IDS:
        read = capability_id.endswith(".read")
        result.append(CapabilitySpec(
            id=capability_id, owner="agent",
            description=f"Execute the governed {capability_id} Agent outcome.",
            use_when="A consumer needs Agent-owned run, session, memory, skill, flow, trace, audit, or interaction state.",
            do_not_use_when="The outcome belongs to another business domain; invoke that domain Capability instead.",
            risk=CapabilityRisk.READ if read else CapabilityRisk.WRITE,
            confirmation="none" if read else "user",
            permissions=("agent.read",) if read else ("agent.write",),
            input_schema=INPUT_SCHEMAS[capability_id], output_schema=OUTPUT_SCHEMAS[capability_id],
            tags=("agent", "read" if read else "write"),
        ))
    return tuple(result)

__all__ = ["specs"]
