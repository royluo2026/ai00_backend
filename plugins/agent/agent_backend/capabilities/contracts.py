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
    "operation": STRING, "name": STRING, "description": STRING, "flowdef": STRING,
    "mode": STRING, "flow_gid": STRING, "run_gid": STRING, "skill_type": STRING,
    "scope": STRING, "scope_filter": STRING, "skill_gid": STRING, "title": STRING, "icon": STRING,
    "tags": {"type": ["array", "string"]}, "sort_order": {"type": "integer"},
    "is_pinned": {"type": "boolean"},
    "session_gid": STRING, "user_gid": STRING, "tool_name": STRING,
    "is_write": {"type": ["boolean", "string"]},
    "is_confirmed": {"type": "boolean"}, "inputs_json": STRING,
    "result_json": STRING, "resource_type": STRING,
    "offset": {"type": "integer", "minimum": 0},
})
RESOURCE = obj({
    "resource_gid": STRING, "resource_type": STRING, "version": {"type": "integer", "minimum": 0},
    "status": STRING, "content": {"type": "object", "additionalProperties": True},
    "content_json": {"type": ["object", "string"]},
})
OUTPUT = obj({
    **RESOURCE["properties"], "items": {"type": "array", "maxItems": 500, "items": RESOURCE},
    "interaction_id": STRING, "gid": STRING,
    "logs": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}},
    "total": {"type": "integer", "minimum": 0},
    "limit": {"type": "integer", "minimum": 1, "maximum": 500},
    "offset": {"type": "integer", "minimum": 0},
    "session_gid": STRING, "success": {"type": "boolean"},
    "sessions": {"type": "array", "maxItems": 50, "items": {"type": "object", "additionalProperties": True}},
    "turns": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}},
})

SCRIPT_INPUT = obj({
    "description": {"type": "string", "minLength": 1, "maxLength": 4000},
    "inputs_schema": {"type": "object", "additionalProperties": True},
    "outputs_schema": {"type": "object", "additionalProperties": True},
}, required=("description",))
SCRIPT_OUTPUT = obj({
    "success": {"type": "boolean"},
    "code": {"type": "string", "maxLength": 20000},
    "error": {"type": "string", "maxLength": 300},
})

RUNTIME_CONFIG_INPUT = obj({})
RUNTIME_CONFIG_OUTPUT = obj({
    "source": {"type": "string", "maxLength": 64},
    "model": {"type": "string", "maxLength": 200},
    "has_key": {"type": "boolean"},
    "key_preview": {"type": "string", "maxLength": 32},
    "is_admin": {"type": "boolean"},
    "api_base": {"type": "string", "maxLength": 500},
})

CAPABILITY_IDS = (
    "agent.audit.read", "agent.audit.record", "agent.flow.change.apply", "agent.flow.read",
    "agent.interaction.request", "agent.interaction.cancel", "agent.memory.change.apply", "agent.memory.read", "agent.runtime.config.read", "agent.tool_catalog.read", "agent.script.generate",
    "agent.run.change.apply", "agent.run.read", "agent.session.change.apply", "agent.session.read",
    "agent.skill.change.apply", "agent.skill.read",
)
INPUT_SCHEMAS = {capability_id: INPUT for capability_id in CAPABILITY_IDS}
OUTPUT_SCHEMAS = {capability_id: OUTPUT for capability_id in CAPABILITY_IDS}
INPUT_SCHEMAS["agent.script.generate"] = SCRIPT_INPUT
OUTPUT_SCHEMAS["agent.script.generate"] = SCRIPT_OUTPUT
INPUT_SCHEMAS["agent.runtime.config.read"] = RUNTIME_CONFIG_INPUT
OUTPUT_SCHEMAS["agent.runtime.config.read"] = RUNTIME_CONFIG_OUTPUT
INPUT_SCHEMAS["agent.tool_catalog.read"] = obj({"operation": {"type": "string", "enum": ["list"]}})
OUTPUT_SCHEMAS["agent.tool_catalog.read"] = obj({
    "read": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}},
    "write_confirm": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}},
    "write_no_confirm": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}},
    "system": {"type": "array", "maxItems": 500, "items": {"type": "object", "additionalProperties": True}},
    "total": {"type": "integer", "minimum": 0},
})
INPUT_SCHEMAS["agent.interaction.cancel"] = obj({"session_gid": STRING}, required=("session_gid",))
OUTPUT_SCHEMAS["agent.interaction.cancel"] = obj({"ok": {"type": "boolean"}, "session_gid": STRING}, required=("ok", "session_gid"))
INPUT_SCHEMAS["agent.interaction.chat.change.apply"] = obj({"operation": {"type": "string", "enum": ["chat_stream", "chat_sync", "confirm", "confirm_sync"]}, "body": {"type": "object", "additionalProperties": True}, "ai00_token": STRING}, required=("operation", "body"))
OUTPUT_SCHEMAS["agent.interaction.chat.change.apply"] = obj({"data": {"type": "object", "additionalProperties": True}}, required=("data",))

__all__ = ["CAPABILITY_IDS", "INPUT_SCHEMAS", "OUTPUT_SCHEMAS"]
