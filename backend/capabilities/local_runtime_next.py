"""Base Capability adapter for the Device domain public control plane."""
from __future__ import annotations

from typing import Callable

from plugins.device.device_backend import public as control_plane
from .models_next import CapabilityContext, CapabilitySpec


def _handler(capability_id: str) -> Callable:
    return lambda payload, context: control_plane.enqueue_command(
        capability_id, 1, payload, context.user_gid
    )


def _get_command(payload: dict, context: CapabilityContext) -> dict:
    return control_plane.get_command(payload["command_gid"], context.user_gid)


def register_local_runtime_capabilities(registry) -> None:
    common = {"type": "object", "required": ["device_gid"], "properties": {"device_gid": {"type": "string", "minLength": 1}}, "additionalProperties": False}
    specs = [
        ("vismockup.status", "读取 VisMockup 连接状态。", "read", "none", common),
        ("vismockup.launch", "启动或连接 VisMockup。", "write", "user", common),
        ("vismockup.open_file", "打开允许目录中的 PLMXML/JT 文件。", "write", "user", {"type":"object","required":["device_gid","file_path"],"properties":{"device_gid":{"type":"string"},"file_path":{"type":"string","minLength":1}},"additionalProperties":False}),
        ("vismockup.tree", "读取 VisMockup 结构树。", "read", "none", {"type":"object","required":["device_gid"],"properties":{"device_gid":{"type":"string"},"max_depth":{"type":"integer"},"force":{"type":"boolean"}},"additionalProperties":False}),
        ("vismockup.highlight", "按 CATIA occurrence 名称高亮节点。", "write", "user", {"type":"object","required":["device_gid","catia_names"],"properties":{"device_gid":{"type":"string"},"catia_names":{"type":"array","items":{"type":"string"}}},"additionalProperties":False}),
        ("vismockup.visibility", "执行全显、全隐或取消选择。", "write", "user", {"type":"object","required":["device_gid","action"],"properties":{"device_gid":{"type":"string"},"action":{"type":"string","enum":["all_on","all_off","deselect"]}},"additionalProperties":False}),
        ("vismockup.capture", "捕获当前 VisMockup 视图。", "write", "user", common),
    ]
    for capability_id, description, risk, confirmation, schema in specs:
        registry.register(CapabilitySpec(
            id=capability_id, version=1, description=description, execution="local", risk=risk,
            confirmation=confirmation, permissions=("agent.run",), input_schema=schema,
            output_schema={"type":"object"}, device_capability=capability_id,
            tags=("vismockup", "local", risk),
        ), _handler(capability_id))
    registry.register(CapabilitySpec(
        id="local.command.get", version=1, description="读取本人发起的本地命令状态和结果。",
        permissions=("agent.run",), input_schema={"type":"object","required":["command_gid"],"properties":{"command_gid":{"type":"string"}},"additionalProperties":False},
        output_schema={"type":"object"}, tags=("local", "read"),
    ), _get_command)
