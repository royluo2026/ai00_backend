from __future__ import annotations

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext
from backend.platform_sdk.ids import next_gid

from .network_policy import NetworkPolicy
from .transform import RestrictedExpression


class IntegrationApplication:
    def __init__(self, repository, connector_runtime=None):
        self.repository = repository
        self.connector_runtime = connector_runtime
        self.network_policy = NetworkPolicy()

    @staticmethod
    def _bind(data: dict, context: CapabilityContext) -> dict:
        owner = getattr(context, "user_gid", None) or getattr(context, "actor_gid", None)
        if not owner:
            raise CapabilityBusinessError("permission_denied", "Integration access requires an actor-bound principal")
        return {**data, "owner_gid": str(owner), "team_gid": getattr(context, "team_gid", None)}

    @staticmethod
    def _require(data: dict, *fields: str) -> None:
        missing = [field for field in fields if data.get(field) in (None, "")]
        if missing:
            raise CapabilityBusinessError("invalid_input", "Missing fields: " + ", ".join(missing))

    @staticmethod
    def _validate_mappings(items: list[dict]) -> None:
        for item in items:
            if item.get("transform_expression"):
                RestrictedExpression(item["transform_expression"])

    async def invoke(self, capability_id: str, payload: dict, context: CapabilityContext):
        data = self._bind(dict(payload), context)
        repo = self.repository
        if capability_id == "integration.connector.create":
            self._require(data, "name", "connector_type", "host", "port", "database_name", "username", "credential_ref")
            self.network_policy.validate_host(data["host"])
            return repo.create_connector(data)
        if capability_id == "integration.connector.update":
            self._require(data, "gid", "expected_revision"); return repo.update_connector(data)
        if capability_id == "integration.connector.archive":
            self._require(data, "gid", "expected_revision"); return repo.archive_connector(data)
        if capability_id == "integration.connector.search":
            return {"items": repo.search_connectors(data)}
        if capability_id in {"integration.connector.connection.test", "integration.connector.schema.discover"}:
            self._require(data, "gid")
            if self.connector_runtime is None:
                raise CapabilityBusinessError("connector_runtime_unavailable", "External connector runtime is unavailable")
            method = self.connector_runtime.test if capability_id.endswith("connection.test") else self.connector_runtime.discover
            return await method(data)
        if capability_id == "integration.mapping.create":
            self._require(data, "datasource_gid", "name", "source_object", "target_domain", "target_capability_id", "target_major_version", "minimum_catalog_release")
            self._validate_mappings(data.get("field_mappings", [])); return repo.create_mapping(data)
        if capability_id == "integration.mapping.get":
            self._require(data, "gid"); return repo.get_mapping(data)
        if capability_id == "integration.mapping.search":
            return {"items": repo.search_mappings(data)}
        if capability_id == "integration.mapping.update":
            self._require(data, "gid", "expected_revision"); self._validate_mappings(data.get("field_mappings", [])); return repo.update_mapping(data)
        if capability_id == "integration.mapping.archive":
            self._require(data, "gid", "expected_revision"); return repo.archive_mapping(data)
        if capability_id == "integration.mapping.preview":
            self._require(data, "gid")
            if self.connector_runtime is None:
                raise CapabilityBusinessError("connector_runtime_unavailable", "External connector runtime is unavailable")
            return await self.connector_runtime.preview(data)
        if capability_id == "integration.sync.start":
            self._require(data, "mapping_gid")
            return {"run_id": str(next_gid()), "operation_ref": {"operation_id": str(next_gid()), "status": "accepted", "version": 1}}
        raise CapabilityBusinessError("invalid_input", f"Unsupported Integration outcome: {capability_id}")
