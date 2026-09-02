"""Trusted effective-identity projection shared by REST and capabilities."""
from __future__ import annotations

import os
from typing import Any


ROLE_PERMISSIONS = {
    "super_admin": {"system.tech_config", "system.app_config", "system.user.manage", "system.plugin.manage", "project.create", "project.manage_any", "project.view", "craft.write_direct", "craft.write_draft", "craft.view", "rule.manage", "rule.view", "template.manage", "template.view", "knowledge.manage", "knowledge.view", "approval.submit", "approval.approve", "feishu.view"},
    "team_admin": {"system.app_config", "system.user.manage", "project.create", "project.manage_any", "project.view", "craft.write_direct", "craft.write_draft", "craft.view", "rule.manage", "rule.view", "template.manage", "template.view", "knowledge.manage", "knowledge.view", "approval.submit", "approval.approve", "feishu.view"},
    "project_admin": {"project.manage_assigned", "project.view", "craft.write_direct", "craft.write_draft", "craft.view", "rule.view", "template.view", "knowledge.view", "approval.submit", "approval.approve", "feishu.view"},
    "rule_admin": {"project.view", "craft.view", "rule.manage", "rule.view", "template.view", "knowledge.view", "approval.submit", "feishu.view"},
    "knowledge_admin": {"project.view", "craft.view", "rule.view", "template.manage", "template.view", "knowledge.manage", "knowledge.view", "approval.submit", "feishu.view"},
    "member": {"project.view", "craft.write_direct", "craft.write_draft", "craft.view", "rule.view", "template.view", "knowledge.view", "approval.submit", "feishu.view"},
    "external": {"external.view"},
}
ORG_ROLE_PERMISSIONS = {
    "super_admin": ROLE_PERMISSIONS["super_admin"],
    "member": ROLE_PERMISSIONS["member"],
    "external": ROLE_PERMISSIONS["external"],
}
GRANT_PERMISSIONS = {
    "team_admin": {"system.app_config", "system.user.manage", "system.plugin.manage", "project.create", "project.manage_any", "rule.manage", "knowledge.manage", "template.manage", "approval.approve"},
    "project_owner": {"project.manage_assigned", "craft.write_direct", "ebom.import", "approval.approve"},
    "section_lead": {"craft.write_direct"},
    "capability_analyst": {"system.capability.read", "system.capability.analyze"},
    "capability_governor": {"system.capability.read", "system.capability.analyze", "system.capability.govern"},
    "capability_release_manager": {"system.capability.read", "system.capability.analyze", "system.capability.govern", "system.capability.release"},
}
SETTINGS_VISIBILITY = {
    "super_admin": ["appearance", "shortcuts", "general", "database", "file-store", "feishu", "plugin-market", "user-management"],
    "team_admin": ["appearance", "shortcuts", "general", "file-store", "feishu", "plugin-market", "user-management"],
    "project_admin": ["appearance", "shortcuts", "general", "feishu", "plugin-market"],
    "rule_admin": ["appearance", "shortcuts", "general", "feishu", "plugin-market"],
    "knowledge_admin": ["appearance", "shortcuts", "general", "feishu", "plugin-market"],
    "member": ["appearance", "shortcuts", "general", "feishu", "plugin-market"],
    "external": ["appearance"],
}


def derive_org_role(system_role: str) -> str:
    if system_role == "super_admin":
        return "super_admin"
    if system_role == "external":
        return "external"
    return "member"


def build_effective_profile(user: dict[str, Any], grants: list[dict[str, Any]]) -> dict[str, Any]:
    role = str(user.get("system_role") or "external")
    org_role = str(user.get("org_role") or derive_org_role(role))
    permissions = set(ORG_ROLE_PERMISSIONS.get(org_role) or ROLE_PERMISSIONS.get(role, set()))
    if role == "external" and user.get("external_subtype") == "outsource":
        permissions = set(ROLE_PERMISSIONS["member"])
    if role == "team_admin":
        permissions.add("system.user.manage")
    for grant in grants:
        permissions.update(GRANT_PERMISSIONS.get(str(grant.get("grant_type") or ""), set()))
    if org_role == "super_admin" and os.environ.get("AI00_DEPLOYMENT_PROFILE") == "test-governance":
        permissions.update({"system.capability.read", "system.capability.analyze", "system.capability.govern", "system.capability.release"})
    if "craft.view" in permissions:
        permissions.update({"craft.read", "factory.read"})
    if "craft.write_direct" in permissions:
        permissions.add("craft.write")
    if "knowledge.view" in permissions:
        permissions.add("knowledge.read")
    if "knowledge.manage" in permissions:
        permissions.add("knowledge.write")
    if org_role == "super_admin" or role in {"super_admin", "team_admin", "project_admin", "knowledge_admin"} or any(g.get("grant_type") == "team_admin" for g in grants):
        permissions.add("factory.write")
    if org_role != "external":
        permissions.update({"digital_model.use", "simulation.use"})
    return {
        **{key: value for key, value in user.items() if key != "feishu_open_id"},
        "org_role": org_role,
        "permissions": sorted(permissions),
        "grants": grants,
        "visible_panels": SETTINGS_VISIBILITY.get(role, ["appearance"]),
    }


__all__ = ["build_effective_profile", "derive_org_role"]
