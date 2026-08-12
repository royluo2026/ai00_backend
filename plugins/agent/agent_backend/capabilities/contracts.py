from __future__ import annotations


def obj(properties: dict, required: tuple[str, ...] = ()) -> dict:
    value = {"type": "object", "properties": properties, "additionalProperties": False}
    if required: value["required"] = list(required)
    return value


STRING = {"type": "string", "minLength": 1}
INPUT = obj({
    "resource_gid": STRING, "expected_version": {"type": "integer", "minimum": 0},
    "status": STRING, "content": {"type": "object", "additionalProperties": True},
    "query": STRING, "limit": {"type": "integer", "minimum": 1, "maximum": 200},
})
RESOURCE = obj({
    "resource_gid": STRING, "resource_type": STRING, "version": {"type": "integer", "minimum": 0},
    "status": STRING, "content": {"type": "object", "additionalProperties": True},
    "content_json": {"type": ["object", "string"]},
})
OUTPUT = obj({
    **RESOURCE["properties"], "items": {"type": "array", "items": RESOURCE},
    "interaction_id": STRING,
})

CAPABILITY_IDS = (
    "agent.audit.read", "agent.audit.record", "agent.flow.change.apply", "agent.flow.read",
    "agent.interaction.request", "agent.memory.change.apply", "agent.memory.read",
    "agent.run.change.apply", "agent.run.read", "agent.session.change.apply", "agent.session.read",
    "agent.skill.change.apply", "agent.skill.read",
)
INPUT_SCHEMAS = {capability_id: INPUT for capability_id in CAPABILITY_IDS}
OUTPUT_SCHEMAS = {capability_id: OUTPUT for capability_id in CAPABILITY_IDS}

__all__ = ["CAPABILITY_IDS", "INPUT_SCHEMAS", "OUTPUT_SCHEMAS"]
