from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypedDict
from urllib.parse import quote
from pathlib import Path

from backend.capability_v2.catalog import load_catalog_release


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


class CatalogReferenceResolver(ReferenceResolver):
    """Production resolver backed by the server-owned Catalog snapshot.

    No caller-provided dictionary is accepted for capability identity. Other
    domain references remain fail-closed until their owner exposes a governed
    reader through an explicit adapter.
    """

    def __init__(self, registry, *, catalog_path: Path | None = None, authorization_checker: Callable[[str, str], bool] | None = None):
        self._registry = registry
        self._catalog_path = catalog_path or Path(__file__).resolve().parents[4] / "docs/governance/capability-catalog-release.json"
        self._authorization_checker = authorization_checker
        super().__init__(lookups={"capability": self._lookup_capability})

    def for_authorization(self, checker: Callable[[str, str], bool]) -> "CatalogReferenceResolver":
        """Create a request-scoped resolver with a trusted Gateway decision."""
        return CatalogReferenceResolver(
            self._registry, catalog_path=self._catalog_path,
            authorization_checker=checker,
        )

    def _lookup_capability(self, version_gid: str, _actor_gid: str) -> dict[str, Any]:
        release = load_catalog_release(self._catalog_path.read_text(encoding="utf-8"))
        if "@" in version_gid:
            capability_id, major_text = version_gid.rsplit("@", 1)
        else:
            member = next((item for item in release.descriptors if item.capability_version_gid == version_gid), None)
            if member is None:
                return {}
            capability_id, major_text = member.id, str(member.major_version)
        try:
            major = int(major_text)
            registered = self._registry.get(capability_id, major)
        except (ValueError, KeyError):
            return {}
        descriptor = registered.descriptor
        if descriptor is None:
            return {}
        member = release.descriptor(capability_id, major)
        if member is None:
            return {}
        # Provider identity is owned by the Catalog member.  Resolve the
        # matching runtime artifact from that owner instead of assuming the
        # Agent artifact can execute every bound Capability.
        owner = member.owner_domain
        artifact = self._registry.provider_artifact(owner)
        if member is None or artifact is None:
            return {}
        return {
            "capability_version_gid": member.capability_version_gid,
            "capability_id": capability_id,
            "major_version": major,
            "lifecycle_status": getattr(member.lifecycle_status, "value", member.lifecycle_status),
            "provider_ref": member.provider_ref or "agent.provider",
            "gateway_ref": "backend.capability_v2.gateway",
            "catalog_release_gid": release.release_id,
            "artifact_hash": artifact.artifact_hash,
            "catalog_member": True,
            "artifact_match": artifact.artifact_hash == next(
                (item.artifact_hash for item in release.provider_artifacts
                 if item.plugin_id == artifact.plugin_id and item.module == artifact.module),
                None,
            ),
            # Authorization is a separate server-side decision. Without an
            # injected trusted authorizer this resolver must fail closed rather
            # than treating an actor string as proof of permission.
            # Read-only references may be projected for the resolver's
            # standalone catalog inspection. Any write-capable binding must
            # come through the request-scoped Gateway checker injected by the
            # production publish handler.
            "authorized": (
                self._authorization_checker(version_gid, _actor_gid)
                if self._authorization_checker is not None
                else descriptor.side_effect_level.value == "read"
            ),
        }
