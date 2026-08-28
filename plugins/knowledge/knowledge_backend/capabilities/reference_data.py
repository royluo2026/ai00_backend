from __future__ import annotations

from backend.capability_v2.provider_contracts import CapabilityRisk, CapabilitySpec

from ..application.reference_data import ReferenceDataService
from ..infrastructure.reference_data import ReferenceDataRepository
from ..provider import register_capability


service = ReferenceDataService(ReferenceDataRepository())


_SCALAR_VALUE = {
    "oneOf": [
        {"type": "string"},
        {"type": "number"},
        {"type": "boolean"},
        {"type": "null"},
    ],
}
_FIELD = {
    "type": "object",
    "required": ["name", "source_field"],
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "source_field": {"type": "string", "minLength": 1},
    },
    "additionalProperties": False,
}
_ROW_VALUE = {
    "type": "object",
    "required": ["field", "value"],
    "properties": {
        "field": {"type": "string", "minLength": 1},
        "value": _SCALAR_VALUE,
    },
    "additionalProperties": False,
}
_ROW = {
    "type": "object",
    "required": ["key", "values"],
    "properties": {
        "key": {"type": "string", "minLength": 1},
        "values": {"type": "array", "items": _ROW_VALUE, "maxItems": 200},
    },
    "additionalProperties": False,
}
_PUBLISH_INPUT = {
    "type": "object",
    "required": ["dataset_gid", "expected_version", "schema", "rows"],
    "properties": {
        "dataset_gid": {"type": "string", "minLength": 1},
        "expected_version": {"type": "integer", "minimum": 0},
        "schema": {
            "type": "object",
            "required": ["fields"],
            "properties": {
                "fields": {"type": "array", "items": _FIELD, "maxItems": 200},
            },
            "additionalProperties": False,
        },
        "rows": {"type": "array", "items": _ROW, "maxItems": 1000},
    },
    "additionalProperties": False,
}
_PUBLISH_OUTPUT = {
    "type": "object",
    "required": ["data"],
    "properties": {
        "data": {
            "type": "object",
            "required": [
                "dataset_gid", "version_gid", "version_no", "schema", "rows",
                "immutable", "dataset_version_ref",
            ],
            "properties": {
                "dataset_gid": {"type": "string"},
                "version_gid": {"type": "string"},
                "version_no": {"type": "integer", "minimum": 1},
                "schema": _PUBLISH_INPUT["properties"]["schema"],
                "rows": _PUBLISH_INPUT["properties"]["rows"],
                "immutable": {"type": "boolean"},
                "dataset_version_ref": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
    "additionalProperties": False,
}


def register_reference_data_capabilities(registry):
    capabilities = (
        ("knowledge.reference_data.read", True, {"type": "object", "additionalProperties": True}, None),
        ("knowledge.reference_data.change.apply", False, {"type": "object", "additionalProperties": True}, None),
        ("knowledge.reference_dataset.publish", False, _PUBLISH_INPUT, _PUBLISH_OUTPUT),
    )
    for capability_id, read, input_schema, output_schema in capabilities:
        spec = CapabilitySpec(
            id=capability_id, owner="knowledge", description="Read or publish immutable versioned reference datasets.",
            use_when="Other domains need low-frequency maintained tabular data for reproducible calculations.",
            do_not_use_when="The caller needs mutable operational transactions or cross-domain SQL.",
            risk=CapabilityRisk.READ if read else CapabilityRisk.WRITE, confirmation="none" if read else "user",
            permissions=("knowledge.reference_data.read",) if read else ("knowledge.reference_data.publish",),
            input_schema=input_schema,
            output_schema=output_schema or {
                "type": "object", "required": ["data"], "properties": {"data": {}}
            },
            tags=("knowledge", "reference_data"), plugin_callable=True,
        )
        def handler(payload, context, *, _read=read):
            tenant_gid = context.team_gid
            if _read:
                rows = service.lookup(dataset_gid=payload["dataset_gid"], version_gid=payload["version_gid"], keys=payload["keys"], tenant_gid=tenant_gid)
                return {"data": {"dataset_version_ref": f"knowledge-reference-version:{payload['version_gid']}", "rows": rows}}
            result = service.publish(dataset_gid=payload["dataset_gid"], expected_version=int(payload["expected_version"]), schema=payload["schema"], rows=payload["rows"], actor_gid=context.user_gid, tenant_gid=tenant_gid)
            return {"data": {
                **result,
                "schema": payload["schema"],
                "rows": payload["rows"],
                "dataset_version_ref": f"knowledge-reference-version:{result['version_gid']}",
            }}
        register_capability(registry, spec, handler)
