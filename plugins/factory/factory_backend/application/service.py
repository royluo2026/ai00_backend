"""Factory application port with tenant binding and optimistic transitions."""
from __future__ import annotations

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext


class FactoryApplication:
    def __init__(self, repository):
        self.repository = repository

    @staticmethod
    def _tenant(payload: dict, context: CapabilityContext) -> str:
        tenant_gid = getattr(context, "tenant_gid", None) or getattr(context, "team_gid", None)
        if not tenant_gid:
            raise CapabilityBusinessError("permission_denied", "Factory access requires a tenant-bound principal")
        return str(tenant_gid)

    @staticmethod
    def _required(payload: dict, *keys: str) -> None:
        missing = [key for key in keys if payload.get(key) in (None, "")]
        if missing:
            raise CapabilityBusinessError("invalid_input", f"Missing fields: {', '.join(missing)}")

    @staticmethod
    def _changed(value, message: str):
        if not value:
            raise CapabilityBusinessError("version_conflict", message)
        return value

    def invoke(self, capability_id: str, payload: dict, context: CapabilityContext):
        data = dict(payload)
        tenant_gid = self._tenant(data, context)
        data["tenant_gid"] = tenant_gid
        repo = self.repository

        if capability_id == "factory.structure.create":
            self._required(data, "kind", "name"); return repo.structure_create(data)
        if capability_id == "factory.structure.get":
            self._required(data, "gid"); return repo.structure_get(data["gid"], tenant_gid)
        if capability_id == "factory.structure.search": return repo.structure_search(data)
        if capability_id == "factory.structure.update":
            self._required(data, "gid", "expected_version"); return self._changed(repo.structure_update(data["gid"], int(data["expected_version"]), data.get("updates", {}), tenant_gid), "Structure was changed or archived")
        if capability_id == "factory.structure.archive":
            self._required(data, "gid", "expected_version"); return {"archived": self._changed(repo.structure_archive(data["gid"], int(data["expected_version"]), tenant_gid), "Structure was changed or archived")}

        if capability_id == "factory.resource_catalog.get":
            self._required(data, "gid"); return repo.catalog_get(data["gid"], tenant_gid)
        if capability_id == "factory.resource_catalog.search": return repo.catalog_search(data)
        if capability_id == "factory.resource_catalog.create":
            self._required(data, "resource_type", "name"); return repo.catalog_create(data)
        if capability_id == "factory.resource_catalog.revise":
            self._required(data, "gid", "expected_revision"); return self._changed(repo.catalog_revise(data["gid"], int(data["expected_revision"]), data, tenant_gid), "Catalog entry revision conflict")
        if capability_id in {"factory.resource_catalog.publish", "factory.resource_catalog.deprecate"}:
            self._required(data, "gid", "expected_revision"); target = "published" if capability_id.endswith("publish") else "deprecated"; return {"status": target, "changed": self._changed(repo.catalog_transition(data["gid"], int(data["expected_revision"]), target, tenant_gid), "Catalog entry transition conflict")}

        if capability_id == "factory.asset.register":
            self._required(data, "asset_no", "asset_type"); return repo.asset_register(data)
        if capability_id == "factory.asset.get":
            self._required(data, "gid"); return repo.asset_get(data["gid"], tenant_gid)
        if capability_id == "factory.asset.search": return repo.asset_search(data)
        if capability_id == "factory.asset.update":
            self._required(data, "gid", "expected_version"); return self._changed(repo.asset_update(data["gid"], int(data["expected_version"]), data.get("updates", {}), tenant_gid), "Asset version conflict")
        if capability_id == "factory.asset.maintenance.start": source, target = ("in_use",), "maintenance"
        elif capability_id == "factory.asset.maintenance.complete": source, target = ("maintenance",), "in_use"
        elif capability_id == "factory.asset.scrap": source, target = ("in_use", "maintenance"), "scrapped"
        else: raise CapabilityBusinessError("invalid_input", f"Unsupported Factory outcome: {capability_id}")
        self._required(data, "gid", "expected_version")
        return {"status": target, "changed": self._changed(repo.asset_transition(data["gid"], int(data["expected_version"]), source, target, tenant_gid), "Asset transition conflict")}
