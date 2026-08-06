"""Governed plugin installation lifecycle capabilities."""
from __future__ import annotations

from .models_next import CapabilityRisk, CapabilitySpec
from backend.plugin_platform import service


BASE_SCHEMA = {"type": "object", "required": ["plugin_id"], "properties": {"plugin_id": {"type": "string", "minLength": 3}}, "additionalProperties": False}


def _spec(capability_id: str, description: str, schema: dict) -> CapabilitySpec:
    return CapabilitySpec(owner="plugin", id=capability_id, version=1, description=description, risk=CapabilityRisk.WRITE, confirmation="admin", permissions=("system.plugin.manage",), input_schema=schema, output_schema={"type": "object"}, tags=("plugin", "marketplace", "admin"))


def register_plugin_marketplace_capabilities(registry) -> None:
    install_schema = {"type": "object", "required": ["plugin_id", "version", "granted_capabilities"], "properties": {"plugin_id": {"type": "string"}, "version": {"type": "string"}, "granted_capabilities": {"type": "array", "items": {"type": "string"}}}, "additionalProperties": False}
    upgrade_schema = {"type": "object", "required": ["plugin_id", "version", "granted_capabilities"], "properties": {"plugin_id": {"type": "string"}, "version": {"type": "string"}, "granted_capabilities": {"type": "array", "items": {"type": "string"}}}, "additionalProperties": False}
    finish_schema = {"type": "object", "required": ["plugin_id", "healthy"], "properties": {"plugin_id": {"type": "string"}, "healthy": {"type": "boolean"}}, "additionalProperties": False}
    registry.register(_spec("plugin.install", "Install a platform-signed release in disabled state.", install_schema), service.install)
    registry.register(_spec("plugin.enable", "Enable an installed plugin.", BASE_SCHEMA), lambda p, c: service.transition(p, c, "enabled"))
    registry.register(_spec("plugin.disable", "Disable an installed plugin.", BASE_SCHEMA), lambda p, c: service.transition(p, c, "disabled"))
    registry.register(_spec("plugin.upgrade", "Stage a signed version upgrade pending health result.", upgrade_schema), service.upgrade)
    registry.register(_spec("plugin.upgrade.finish", "Complete or fail a staged upgrade after health validation.", finish_schema), service.finish_upgrade)
    registry.register(_spec("plugin.rollback", "Roll back to the previous platform-signed version.", BASE_SCHEMA), service.rollback)
    registry.register(_spec("plugin.revoke", "Revoke an installed plugin immediately.", BASE_SCHEMA), lambda p, c: service.transition(p, c, "revoked"))
    registry.register(_spec("plugin.uninstall", "Uninstall a disabled or revoked plugin.", BASE_SCHEMA), lambda p, c: service.transition(p, c, "uninstalled"))
