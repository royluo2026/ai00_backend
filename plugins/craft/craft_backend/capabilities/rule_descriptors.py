from __future__ import annotations
from backend.capability_v2.provider_contracts import CapabilityOutput, CapabilitySpec

RULE_CAPABILITY_IDS = (
 "craft.rule.draft.create", "craft.rule.draft.get", "craft.rule.draft.search", "craft.rule.draft.revise", "craft.rule.draft.submit",
 "craft.rule.release.get", "craft.rule.release.search", "craft.rule.release.publish", "craft.rule.release.activate",
 "craft.rule.evaluate", "craft.bop.validation.run", "craft.bop.validation.get",
 "craft.rule.waiver.create", "craft.rule.waiver.search", "craft.rule.waiver.revoke",
)
_READS = {item for item in RULE_CAPABILITY_IDS if item.endswith((".get", ".search", ".evaluate"))}

def register_rule_capabilities(registry):
    for capability_id in RULE_CAPABILITY_IDS:
        read = capability_id in _READS
        def handler(payload, context, _id=capability_id):
            return CapabilityOutput(data={"capability_id": _id, "status": "evaluated" if _id.endswith("evaluate") else "accepted", "evidence": payload.get("evidence", []), "release_ref": payload.get("release_ref")})
        registry.register(CapabilitySpec(id=capability_id, owner="craft", description=capability_id,
          use_when="A published Craft rule release, validation, or waiver is required.", do_not_use_when="Rules are unreviewed or inputs are mutable.",
          risk="read" if read else "write", confirmation="none" if read else "user", idempotent=not read,
          permissions=() if read else ("craft.rule.write",), plugin_callable=True, input_schema={"type":"object"}, output_schema={"type":"object"},
          effects=(("read" if read else "write")+":craft.rule",), tags=("craft","rule")), handler)

__all__ = ["RULE_CAPABILITY_IDS", "register_rule_capabilities"]
