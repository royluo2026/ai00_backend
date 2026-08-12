from __future__ import annotations
from backend.capability_v2.provider_contracts import CapabilityOutput, CapabilitySpec
from .gbop_read import get_gbop_item_usage, list_gbop_item_knowledge, search_gbop_items

GBOP_CAPABILITY_IDS = (
 "craft.gbop.draft.create", "craft.gbop.draft.get", "craft.gbop.draft.search", "craft.gbop.draft.change.preview",
 "craft.gbop.draft.change.apply", "craft.gbop.draft.submit", "craft.gbop.release.get", "craft.gbop.release.search",
 "craft.gbop.release.publish", "craft.gbop.release.activate", "craft.gbop.release.archive", "craft.gbop.release.compare",
 "craft.gbop.item.search", "craft.gbop.item.usage.get", "craft.gbop.item.knowledge.list",
)

_READS = {item for item in GBOP_CAPABILITY_IDS if item.endswith((".get", ".search", ".compare", ".list"))}
_EXISTING = {"craft.gbop.item.search": search_gbop_items, "craft.gbop.item.usage.get": get_gbop_item_usage, "craft.gbop.item.knowledge.list": list_gbop_item_knowledge}

def _generic(capability_id):
    def handler(payload, context): return CapabilityOutput(data={"capability_id": capability_id, "ref": payload.get("ref"), "status": "accepted", "lineage_refs": payload.get("lineage_refs", [])})
    return handler

def register_gbop_capabilities(registry):
    for capability_id in GBOP_CAPABILITY_IDS:
        read = capability_id in _READS
        registry.register(CapabilitySpec(id=capability_id, owner="craft", description=capability_id,
          use_when="GBOP draft, immutable release, or item is the subject.", do_not_use_when="The subject is a project BOP.",
          risk="read" if read else "write", confirmation="none" if read else "user", idempotent=not read,
          permissions=() if read else ("craft.gbop.write",), plugin_callable=True, input_schema={"type":"object"}, output_schema={"type":"object"},
          effects=(("read" if read else "write")+":craft.gbop",), tags=("craft","gbop")), _EXISTING.get(capability_id, _generic(capability_id)))

__all__ = ["GBOP_CAPABILITY_IDS", "register_gbop_capabilities"]
