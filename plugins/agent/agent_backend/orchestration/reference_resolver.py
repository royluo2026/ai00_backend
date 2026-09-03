from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypedDict
from urllib.parse import quote


Lookup = Callable[[str, str], dict[str, Any]]


class UntrustedCapabilityReference(RuntimeError):
    pass


class ResolvedCapabilityBinding(TypedDict):
    capability_version_gid: str
    capability_id: str
    major_version: int
    lifecycle_status: str
    provider_ref: str
    gateway_ref: str
    catalog_release_gid: str
    artifact_hash: str

_REFERENCE_UI = {
    "capability": ("capability_governance", "/web/admin/capabilities.html?id="),
    "data": ("data", "/web/ext_datasource/index.html?id="),
    "rule": ("rule_governance", "/web/rule_mgmt/rule_mgmt.html?id="),
    "knowledge": ("knowledge", "/web/knowledge_hub/index.html?id="),
    "ontology": ("ontology", "/web/ontology/index.html?id="),
    "code": ("code", "/web/code/index.html?ref="),
}


class ReferenceResolver:
    """Request-scoped external-reference projection; never edits authoritative objects."""

    def __init__(self, capability_lookup: Lookup | None = None, lookups: dict[str, Lookup] | None = None):
        self._lookups = dict(lookups or {})
        if capability_lookup:
            self._lookups["capability"] = capability_lookup

    def resolve_many(self, refs: list[dict[str, str]], actor_gid: str) -> list[dict[str, Any]]:
        cache: dict[tuple[str, str], dict[str, Any]] = {}
        result = []
        for ref in refs:
            ref_type, ref_gid = ref["ref_type"], ref["ref_gid"]
            key = (ref_type, ref_gid)
            if key not in cache:
                cache[key] = self._resolve(ref_type, ref_gid, actor_gid)
            result.append(dict(cache[key]))
        return result

    def resolve_capability_binding(
        self, version_gid: str, actor_gid: str
    ) -> ResolvedCapabilityBinding:
        lookup = self._lookups.get("capability")
        projected = lookup(version_gid, actor_gid) if lookup else {}
        required = (
            "capability_version_gid",
            "capability_id",
            "major_version",
            "lifecycle_status",
            "provider_ref",
            "gateway_ref",
            "catalog_release_gid",
            "artifact_hash",
        )
        if (
            any(projected.get(field) in (None, "") for field in required)
            or projected.get("capability_version_gid") != version_gid
            or projected.get("lifecycle_status") != "stable"
            or projected.get("catalog_member") is not True
            or projected.get("artifact_match") is not True
            or projected.get("authorized") is not True
        ):
            raise UntrustedCapabilityReference(
                f"Capability version is not a trusted published binding: {version_gid}"
            )
        return {field: projected[field] for field in required}  # type: ignore[return-value]

    def _resolve(self, ref_type: str, ref_gid: str, actor_gid: str) -> dict[str, Any]:
        authority, prefix = _REFERENCE_UI.get(ref_type, ("external", "/web/?ref="))
        lookup = self._lookups.get(ref_type)
        projected = lookup(ref_gid, actor_gid) if lookup else {}
        return {
            "ref_type": ref_type,
            "ref_gid": ref_gid,
            "label": projected.get("label", ref_gid),
            "version": projected.get("version"),
            "lifecycle": projected.get("lifecycle", "unverified"),
            "governance_status": projected.get("governance_status", "unverified"),
            "edit_authority": authority,
            "deep_link": f"{prefix}{quote(ref_gid)}",
            "resolved": projected.get("resolved", False),
            "read_only": True,
        }
