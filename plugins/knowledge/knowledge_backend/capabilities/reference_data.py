from __future__ import annotations

from backend.capability_v2.provider_contracts import CapabilityRisk, CapabilitySpec

from ..application.reference_data import ReferenceDataService
from ..infrastructure.reference_data import ReferenceDataRepository
from ..provider import register_capability


service = ReferenceDataService(ReferenceDataRepository())


def register_reference_data_capabilities(registry):
    for capability_id, read in (("knowledge.reference_data.read", True), ("knowledge.reference_data.change.apply", False)):
        spec = CapabilitySpec(
            id=capability_id, owner="knowledge", description="Read or publish immutable versioned reference datasets.",
            use_when="Other domains need low-frequency maintained tabular data for reproducible calculations.",
            do_not_use_when="The caller needs mutable operational transactions or cross-domain SQL.",
            risk=CapabilityRisk.READ if read else CapabilityRisk.WRITE, confirmation="none" if read else "user",
            permissions=("knowledge.reference_data.read",) if read else ("knowledge.reference_data.publish",),
            input_schema={"type": "object", "additionalProperties": True},
            output_schema={"type": "object", "required": ["data"], "properties": {"data": {}}},
            tags=("knowledge", "reference_data"), plugin_callable=True,
        )
        def handler(payload, context, *, _read=read):
            tenant_gid = context.team_gid
            if _read:
                rows = service.lookup(dataset_gid=payload["dataset_gid"], version_gid=payload["version_gid"], keys=payload["keys"], tenant_gid=tenant_gid)
                return {"data": {"dataset_version_ref": f"knowledge-reference-version:{payload['version_gid']}", "rows": rows}}
            result = service.publish(dataset_gid=payload["dataset_gid"], expected_version=int(payload["expected_version"]), schema=payload["schema"], rows=payload["rows"], actor_gid=context.user_gid, tenant_gid=tenant_gid)
            return {"data": {**result, "dataset_version_ref": f"knowledge-reference-version:{result['version_gid']}"}}
        register_capability(registry, spec, handler)

