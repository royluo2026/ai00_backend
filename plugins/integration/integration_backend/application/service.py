from __future__ import annotations

import asyncio
import hashlib
import inspect
from typing import Any, Callable, Mapping

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityContext

from .network_policy import NetworkPolicy
from .operations import IntegrationOperations, operation_ref
from .ports import ResourceNotFound, RevisionConflict
from .transform import RestrictedExpression


RUNTIME_TIMEOUT_SECONDS = 15
MAX_RESULTS = 200
REDACTED = "[REDACTED]"
_SENSITIVE_KEYS = (
    "password", "secret", "credential", "authorization", "api_key", "apikey",
    "token", "session", "cookie", "private_key", "privatekey",
)
_SENSITIVE_VALUE_MARKERS = (
    "authorization:", "bearer ", "basic ", "api_key=", "apikey=", "password=", "token=", "vault://",
)


class IntegrationApplication:
    def __init__(
        self,
        repository,
        connector_runtime=None,
        *,
        credential_enrollment=None,
        catalog=None,
        operation_identity=None,
        network_policy=None,
    ):
        self.repository = repository
        self.connector_runtime = connector_runtime
        self.credential_enrollment = credential_enrollment
        self.catalog = catalog
        self.network_policy = network_policy or NetworkPolicy()
        self.operations = IntegrationOperations(repository, identity=operation_identity)

    @staticmethod
    def _bind(data: dict, context: CapabilityContext) -> dict:
        owner = getattr(context, "user_gid", None) or getattr(context, "actor_gid", None)
        if not owner:
            raise CapabilityBusinessError("permission_denied", "Integration access requires an actor-bound principal")
        return {**data, "owner_gid": str(owner), "team_gid": getattr(context, "team_gid", None)}

    @staticmethod
    def _closed(data: Mapping[str, Any], allowed: set[str]) -> None:
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise CapabilityBusinessError("invalid_input", "Unknown fields: " + ", ".join(unknown))

    @staticmethod
    def _require(data: Mapping[str, Any], *fields: str) -> None:
        missing = [field for field in fields if data.get(field) in (None, "")]
        if missing:
            raise CapabilityBusinessError("invalid_input", "Missing fields: " + ", ".join(missing))

    @staticmethod
    def _limit(data: Mapping[str, Any], default: int = 100) -> int:
        value = data.get("limit", default)
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_RESULTS:
            raise CapabilityBusinessError("invalid_input", "limit must be between 1 and 200")
        return value

    @classmethod
    def _validate_mappings(cls, items: list[dict] | tuple[dict, ...]) -> list[dict]:
        if len(items) > MAX_RESULTS:
            raise CapabilityBusinessError("invalid_input", "field mapping batch exceeds 200 items")
        validated = []
        for item in items:
            if not isinstance(item, dict):
                raise CapabilityBusinessError("invalid_input", "field mappings must be objects")
            cls._closed(item, {"source_field", "target_field", "transform_expression"})
            cls._require(item, "source_field", "target_field")
            try:
                if item.get("transform_expression"):
                    RestrictedExpression(item["transform_expression"])
            except ValueError as exc:
                raise CapabilityBusinessError("invalid_input", str(exc)) from exc
            validated.append(dict(item))
        return validated

    def _credential_ref(self, data: Mapping[str, Any]) -> str | None:
        handle = data.get("credential_enrollment_handle")
        reference = data.get("credential_ref")
        if handle and reference:
            raise CapabilityBusinessError("invalid_input", "Provide one credential enrollment handle or credential_ref")
        if handle:
            if self.credential_enrollment is None:
                raise CapabilityBusinessError(
                    "credential_enrollment_unavailable", "Credential enrollment vault is unavailable", retryable=True
                )
            try:
                reference = self.credential_enrollment.consume(
                    str(handle), str(data["owner_gid"]), data.get("team_gid")
                )
            except Exception as exc:
                raise CapabilityBusinessError(
                    "credential_enrollment_invalid", "Credential enrollment handle is invalid or already consumed"
                ) from exc
        if reference is not None and not str(reference).strip():
            raise CapabilityBusinessError("invalid_input", "credential_ref cannot be empty")
        return str(reference) if reference is not None else None

    def _require_target(self, mapping: Mapping[str, Any]) -> None:
        self._require(
            mapping, "target_domain", "target_capability_id", "target_major_version", "minimum_catalog_release"
        )
        if not str(mapping["target_capability_id"]).startswith(str(mapping["target_domain"]) + "."):
            raise CapabilityBusinessError("invalid_input", "Target Capability must belong to target_domain")
        if self.catalog is None:
            raise CapabilityBusinessError(
                "target_capability_unavailable", "Target Catalog resolver is unavailable", retryable=True
            )
        try:
            self.catalog.require_stable(
                str(mapping["target_capability_id"]),
                int(mapping["target_major_version"]),
                str(mapping["minimum_catalog_release"]),
            )
        except Exception as exc:
            raise CapabilityBusinessError(
                "target_capability_unavailable", "Target Capability is not stable at the required Catalog release"
            ) from exc

    def _validate_network(self, host: str) -> None:
        try:
            self.network_policy.validate_host(host)
        except ValueError as exc:
            raise CapabilityBusinessError("network_policy_rejected", str(exc)) from exc

    @staticmethod
    def _connector(row: Mapping[str, Any]) -> dict[str, Any]:
        keys = (
            "gid", "revision", "name", "connector_type", "host", "port",
            "database_name", "username", "status",
        )
        return {key: row[key] for key in keys}

    @staticmethod
    def _mapping(row: Mapping[str, Any]) -> dict[str, Any]:
        keys = (
            "gid", "revision", "datasource_gid", "name", "source_object", "target_domain",
            "target_capability_id", "target_major_version", "minimum_catalog_release", "status",
        )
        return {key: row[key] for key in keys}

    @staticmethod
    def _field(mapping_gid: str, item: Mapping[str, Any], revision: int) -> dict[str, Any]:
        digest = hashlib.sha256(
            f"{mapping_gid}\0{item['source_field']}\0{item['target_field']}".encode("utf-8")
        ).hexdigest()[:32]
        projected = {
            "gid": str(item.get("gid") or f"field_mapping-{digest}"),
            "revision": int(item.get("revision") or revision),
            "source_field": str(item["source_field"]),
            "target_field": str(item["target_field"]),
        }
        if item.get("transform_expression"):
            projected["transform_expression"] = str(item["transform_expression"])
        return projected

    @staticmethod
    def _translate_repository(exc: Exception) -> CapabilityBusinessError:
        if isinstance(exc, ResourceNotFound):
            return CapabilityBusinessError("resource_not_found", "Integration resource does not exist")
        if isinstance(exc, RevisionConflict):
            return CapabilityBusinessError("version_conflict", "Integration resource revision changed")
        raise exc

    def _get_connector(self, data: Mapping[str, Any]) -> dict[str, Any]:
        row = self.repository.get_connector(dict(data))
        if row is None:
            raise CapabilityBusinessError("resource_not_found", "Integration connector does not exist")
        return dict(row)

    def _get_mapping(self, data: Mapping[str, Any], gid: str) -> dict[str, Any]:
        row = self.repository.get_mapping({**data, "gid": gid})
        if row is None:
            raise CapabilityBusinessError("resource_not_found", "Integration mapping does not exist")
        return dict(row)

    def _write(
        self,
        capability_id: str,
        data: dict[str, Any],
        action: Callable[[], dict[str, Any]],
        *,
        unknown_external: bool = False,
    ) -> dict[str, Any]:
        claim = self.operations.start(
            capability_id=capability_id,
            payload={key: value for key, value in data.items() if key not in {"owner_gid", "team_gid"}},
            owner_gid=data["owner_gid"],
            team_gid=data.get("team_gid"),
            idempotency_key=str(data.get("idempotency_key") or ""),
        )
        if claim.replayed:
            if claim.record.result is not None:
                return dict(claim.record.result)
            raise CapabilityBusinessError(
                "idempotency_conflict", f"Previous Integration request is {claim.record.status}"
            )
        try:
            result = action()
        except (ResourceNotFound, RevisionConflict) as exc:
            error = self._translate_repository(exc)
            self.operations.failed(claim.record, error_code=error.code)
            raise error from exc
        except CapabilityBusinessError as exc:
            self.operations.failed(claim.record, error_code=exc.code)
            raise
        except Exception as exc:
            if unknown_external:
                self.operations.outcome_unknown(claim.record, error_code=type(exc).__name__)
            else:
                self.operations.failed(claim.record, error_code=type(exc).__name__)
            raise
        self.operations.succeeded(claim.record, result)
        return result

    async def invoke(self, capability_id: str, payload: dict, context: CapabilityContext):
        raw = dict(payload)
        data = self._bind(raw, context)
        if capability_id.startswith("integration.connector."):
            return await self._connector_outcome(capability_id, raw, data, context)
        if capability_id in {
            "integration.mapping.get", "integration.mapping.search", "integration.field_mapping.search",
            "integration.mapping.source_columns.discover", "integration.mapping.preview",
        }:
            return await self._mapping_read(capability_id, raw, data, context)
        if capability_id in {
            "integration.mapping.create", "integration.mapping.update", "integration.mapping.archive",
            "integration.field_mapping.batch.update",
        }:
            return self._mapping_write(capability_id, raw, data)
        if capability_id in {"integration.mapping.import.start", "integration.sync.start"}:
            return self._mapping_import(capability_id, raw, data, context)
        raise CapabilityBusinessError("invalid_input", f"Unsupported Integration outcome: {capability_id}")

    async def _connector_outcome(
        self, capability_id: str, raw: dict[str, Any], data: dict[str, Any], context: CapabilityContext
    ) -> dict[str, Any]:
        if capability_id == "integration.connector.create":
            allowed = {
                "name", "connector_type", "host", "port", "database_name", "username",
                "credential_enrollment_handle", "credential_ref", "idempotency_key",
            }
            self._closed(raw, allowed)
            self._require(data, "name", "connector_type", "host", "port", "database_name", "username", "idempotency_key")

            def create() -> dict[str, Any]:
                self._validate_network(str(data["host"]))
                reference = self._credential_ref(data)
                if reference is None:
                    raise CapabilityBusinessError("invalid_input", "Credential enrollment handle or credential_ref is required")
                stored = {
                    key: data[key] for key in (
                        "name", "connector_type", "host", "port", "database_name", "username", "owner_gid", "team_gid"
                    )
                }
                stored["credential_ref"] = reference
                return self._connector(self.repository.create_connector(stored))

            return self._write(capability_id, data, create, unknown_external=True)

        if capability_id == "integration.connector.update":
            allowed = {
                "gid", "expected_revision", "name", "connector_type", "host", "port", "database_name",
                "username", "credential_enrollment_handle", "credential_ref", "idempotency_key",
            }
            self._closed(raw, allowed)
            self._require(data, "gid", "expected_revision", "idempotency_key")

            def update() -> dict[str, Any]:
                if data.get("host"):
                    self._validate_network(str(data["host"]))
                reference = self._credential_ref(data)
                stored = {
                    key: value for key, value in data.items()
                    if key in allowed | {"owner_gid", "team_gid"}
                    and key not in {"credential_enrollment_handle", "credential_ref", "idempotency_key"}
                }
                if reference is not None:
                    stored["credential_ref"] = reference
                return self._connector(self.repository.update_connector(stored))

            return self._write(capability_id, data, update, unknown_external=bool(data.get("credential_enrollment_handle")))

        if capability_id == "integration.connector.archive":
            self._closed(raw, {"gid", "expected_revision"})
            self._require(data, "gid", "expected_revision")
            try:
                return self.repository.archive_connector(data)
            except (ResourceNotFound, RevisionConflict) as exc:
                raise self._translate_repository(exc) from exc

        if capability_id == "integration.connector.search":
            self._closed(raw, {"query", "limit"})
            limit = self._limit(data)
            return {"items": [self._connector(row) for row in self.repository.search_connectors({**data, "limit": limit})[:limit]]}

        self._closed(raw, {"gid", "limit"} if capability_id.endswith("schema.discover") else {"gid"})
        self._require(data, "gid")
        connector = self._get_connector(data)
        self._validate_network(str(connector["host"]))
        limit = self._limit(data, 100) if capability_id.endswith("schema.discover") else 1
        method = "discover" if capability_id.endswith("schema.discover") else "test"
        return await self._runtime(
            capability_id, data, context, getattr(self.connector_runtime, method, None),
            (connector,), limit, self._project_objects if method == "discover" else self._project_test,
            {"objects": []} if method == "discover" else {},
        )

    async def _mapping_read(
        self, capability_id: str, raw: dict[str, Any], data: dict[str, Any], context: CapabilityContext
    ) -> dict[str, Any]:
        if capability_id == "integration.mapping.get":
            self._closed(raw, {"gid"})
            self._require(data, "gid")
            row = self._get_mapping(data, str(data["gid"]))
            fields = [self._field(str(row["gid"]), item, int(row["revision"])) for item in row.get("field_mappings", ())]
            return {**self._mapping(row), "field_mappings": fields[:MAX_RESULTS]}
        if capability_id == "integration.mapping.search":
            self._closed(raw, {"datasource_gid", "query", "limit"})
            limit = self._limit(data)
            return {"items": [self._mapping(row) for row in self.repository.search_mappings({**data, "limit": limit})[:limit]]}
        if capability_id == "integration.field_mapping.search":
            self._closed(raw, {"mapping_gid", "limit"})
            self._require(data, "mapping_gid")
            limit = self._limit(data)
            mapping = self._get_mapping(data, str(data["mapping_gid"]))
            rows = self.repository.search_field_mappings({**data, "limit": limit})
            if rows is None:
                raise CapabilityBusinessError("resource_not_found", "Integration mapping does not exist")
            return {"items": [self._field(str(mapping["gid"]), row, int(mapping["revision"])) for row in rows[:limit]]}

        self._closed(raw, {"mapping_gid", "limit"} if capability_id.endswith("source_columns.discover") else {"gid", "limit"})
        mapping_gid = str(data.get("mapping_gid") or data.get("gid") or "")
        self._require({"mapping_gid": mapping_gid}, "mapping_gid")
        limit = self._limit(data)
        mapping = self._get_mapping(data, mapping_gid)
        connector = self._get_connector({**data, "gid": mapping["datasource_gid"]})
        self._validate_network(str(connector["host"]))
        source_columns = capability_id.endswith("source_columns.discover")
        method = getattr(self.connector_runtime, "source_columns" if source_columns else "preview", None)
        return await self._runtime(
            capability_id, data, context, method, (connector, mapping), limit,
            self._project_columns if source_columns else self._project_preview,
            {"columns": []} if source_columns else {"rows": [], "truncated": False},
        )

    def _mapping_write(
        self, capability_id: str, raw: dict[str, Any], data: dict[str, Any]
    ) -> dict[str, Any]:
        if capability_id == "integration.mapping.create":
            allowed = {
                "datasource_gid", "name", "source_object", "target_domain", "target_capability_id",
                "target_major_version", "minimum_catalog_release", "field_mappings", "idempotency_key",
            }
            self._closed(raw, allowed)
            self._require(
                data, "datasource_gid", "name", "source_object", "target_domain", "target_capability_id",
                "target_major_version", "minimum_catalog_release", "idempotency_key",
            )
            mappings = self._validate_mappings(data.get("field_mappings", []))

            def create() -> dict[str, Any]:
                self._get_connector({**data, "gid": str(data["datasource_gid"])})
                self._require_target(data)
                mapping_gid = self.operations.new_id("mapping")
                stored = {key: value for key, value in data.items() if key != "idempotency_key"}
                stored["gid"] = mapping_gid
                stored["field_mappings"] = [
                    self._field(mapping_gid, item, 1) for item in mappings
                ]
                return self._mapping(self.repository.create_mapping(stored))

            return self._write(capability_id, data, create)

        if capability_id == "integration.field_mapping.batch.update":
            self._closed(raw, {"mapping_gid", "expected_revision", "items", "idempotency_key"})
            self._require(data, "mapping_gid", "expected_revision", "idempotency_key")
            items = self._validate_mappings(data.get("items", []))
            if not items:
                raise CapabilityBusinessError("invalid_input", "field mapping batch requires 1 to 200 items")

            def replace_batch() -> dict[str, Any]:
                mapping = self._get_mapping(data, str(data["mapping_gid"]))
                self._require_target(mapping)
                stored_items = [self._field(str(mapping["gid"]), item, int(data["expected_revision"]) + 1) for item in items]
                return self.repository.replace_field_mappings({
                    **data, "items": stored_items,
                })

            return self._write(capability_id, data, replace_batch)

        if capability_id == "integration.mapping.update":
            self._closed(raw, {"gid", "expected_revision", "field_mappings"})
            self._require(data, "gid", "expected_revision")
            try:
                mapping = self._get_mapping(data, str(data["gid"]))
                items = self._validate_mappings(data.get("field_mappings", []))
                stored = {
                    **data,
                    "field_mappings": [
                        self._field(str(mapping["gid"]), item, int(data["expected_revision"]) + 1)
                        for item in items
                    ],
                }
                return self.repository.update_mapping(stored)
            except (ResourceNotFound, RevisionConflict) as exc:
                raise self._translate_repository(exc) from exc

        self._closed(raw, {"gid", "expected_revision"})
        self._require(data, "gid", "expected_revision")
        try:
            return self.repository.archive_mapping(data)
        except (ResourceNotFound, RevisionConflict) as exc:
            raise self._translate_repository(exc) from exc

    def _mapping_import(
        self, capability_id: str, raw: dict[str, Any], data: dict[str, Any], context: CapabilityContext
    ) -> dict[str, Any]:
        exact = capability_id == "integration.mapping.import.start"
        self._closed(raw, {"mapping_gid", "idempotency_key"} if exact else {"mapping_gid"})
        self._require(data, "mapping_gid")
        if not exact:
            data["idempotency_key"] = context.request_id or self.operations.new_id("request")
        self._require(data, "idempotency_key")
        operation_payload = {
            key: value for key, value in data.items() if key not in {"owner_gid", "team_gid"}
        }
        replay = self.operations.replay_import(
            capability_id=capability_id, payload=operation_payload,
            owner_gid=data["owner_gid"], team_gid=data.get("team_gid"),
            idempotency_key=str(data["idempotency_key"]),
        )
        if replay is not None:
            run_id = str((replay.record.result or {}).get("run_id") or "")
            if not run_id:
                raise CapabilityBusinessError(
                    "idempotency_conflict", "Integration import operation has no durable run identity"
                )
            return {"run_id": run_id, "operation_ref": operation_ref(replay.record)}
        mapping = self._get_mapping(data, str(data["mapping_gid"]))
        self._require_target(mapping)
        run_id = self.operations.new_id("run")
        claim = self.operations.start_import(
            capability_id=capability_id,
            payload=operation_payload,
            owner_gid=data["owner_gid"], team_gid=data.get("team_gid"),
            idempotency_key=str(data["idempotency_key"]),
            run={
                "run_id": run_id,
                "mapping_gid": mapping["gid"],
                "target_capability_id": mapping["target_capability_id"],
                "target_major_version": mapping["target_major_version"],
                "catalog_release": mapping["minimum_catalog_release"],
                "status": "accepted",
                "owner_gid": data["owner_gid"],
                "team_gid": data.get("team_gid"),
                "idempotency_key": data["idempotency_key"],
            },
        )
        run_id = str((claim.record.result or {}).get("run_id") or "")
        if not run_id:
            raise CapabilityBusinessError(
                "idempotency_conflict", "Integration import operation has no durable run identity"
            )
        return {"run_id": run_id, "operation_ref": operation_ref(claim.record)}

    async def _runtime(
        self,
        capability_id: str,
        data: dict[str, Any],
        context: CapabilityContext,
        method,
        args: tuple,
        limit: int,
        projector: Callable[[Mapping[str, Any], int], dict[str, Any]],
        unknown_result: dict[str, Any],
    ) -> dict[str, Any]:
        if method is None or not inspect.iscoroutinefunction(method):
            raise CapabilityBusinessError(
                "connector_runtime_unavailable", "External connector runtime is unavailable", retryable=True
            )
        key = context.request_id or self.operations.new_id("request")
        claim = self.operations.start(
            capability_id=capability_id,
            payload={key: value for key, value in data.items() if key not in {"owner_gid", "team_gid"}},
            owner_gid=data["owner_gid"], team_gid=data.get("team_gid"), idempotency_key=key,
        )
        if claim.replayed and claim.record.result is not None:
            replay = self._sanitize_runtime_result(claim.record.result)
            return {**replay, "operation_ref": operation_ref(claim.record)}
        try:
            raw = await asyncio.wait_for(
                method(*args, timeout_seconds=RUNTIME_TIMEOUT_SECONDS, result_limit=limit),
                timeout=RUNTIME_TIMEOUT_SECONDS,
            )
            result = self._sanitize_runtime_result(projector(raw, limit))
            record = self.operations.succeeded(claim.record, result)
            return {**result, "operation_ref": operation_ref(record)}
        except TimeoutError:
            record = self.operations.outcome_unknown(claim.record, error_code="external_timeout")
            return {**unknown_result, "operation_ref": operation_ref(record)}
        except Exception as exc:
            self.operations.failed(claim.record, error_code="connector_runtime_unavailable")
            raise CapabilityBusinessError(
                "connector_runtime_unavailable", "External connector runtime failed", retryable=True
            ) from exc

    @staticmethod
    def _project_test(raw: Mapping[str, Any], _limit: int) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if isinstance(raw.get("reachable"), bool):
            result["reachable"] = raw["reachable"]
        if isinstance(raw.get("latency_ms"), int) and not isinstance(raw.get("latency_ms"), bool):
            result["latency_ms"] = raw["latency_ms"]
        if raw.get("message") is not None:
            result["message"] = REDACTED
        return result

    @classmethod
    def _project_objects(cls, raw: Mapping[str, Any], limit: int) -> dict[str, Any]:
        objects = []
        for item in list(raw.get("objects") or ())[:limit]:
            if not isinstance(item, Mapping):
                continue
            name = cls._scalar_text(item.get("name"))
            if not name:
                continue
            kind = cls._scalar_text(item.get("kind")) or "object"
            objects.append({"name": name, "kind": kind})
        return {"objects": objects}

    @classmethod
    def _project_columns(cls, raw: Mapping[str, Any], limit: int) -> dict[str, Any]:
        columns = []
        for item in list(raw.get("columns") or ())[:limit]:
            if not isinstance(item, Mapping):
                continue
            name = cls._scalar_text(item.get("name"))
            if not name:
                continue
            data_type = cls._scalar_text(item.get("data_type")) or "unknown"
            nullable = item.get("nullable", True)
            columns.append({
                "name": name,
                "data_type": data_type,
                "nullable": nullable if isinstance(nullable, bool) else True,
            })
        return {"columns": columns}

    @staticmethod
    def _project_preview(raw: Mapping[str, Any], limit: int) -> dict[str, Any]:
        rows = []
        for row in list(raw.get("rows") or ())[:limit]:
            if not isinstance(row, Mapping):
                continue
            values = []
            for field, value in sorted(row.items(), key=lambda item: str(item[0]))[:MAX_RESULTS]:
                sensitive = IntegrationApplication._secret_exposed({str(field): value})
                scalar = value if value is None or isinstance(value, (str, int, float, bool)) else REDACTED
                values.append({
                    "field": str(field),
                    "value": REDACTED if sensitive else scalar,
                    "redacted": sensitive or scalar == REDACTED,
                })
            rows.append({"values": values})
        return {"rows": rows, "truncated": bool(raw.get("truncated") or len(list(raw.get("rows") or ())) > limit)}

    @staticmethod
    def _sensitive_key(key: object) -> bool:
        normalized = str(key).casefold().replace("-", "_")
        return any(token in normalized for token in _SENSITIVE_KEYS)

    @classmethod
    def _scalar_text(cls, value: Any) -> str | None:
        if not isinstance(value, (str, int, float, bool)):
            return None
        if cls._secret_exposed(value):
            return REDACTED
        return str(value)

    @classmethod
    def _secret_exposed(cls, value: Any) -> bool:
        if isinstance(value, Mapping):
            return any(cls._sensitive_key(key) or cls._secret_exposed(child) for key, child in value.items())
        if isinstance(value, (list, tuple, set)):
            return any(cls._secret_exposed(child) for child in value)
        if isinstance(value, str):
            normalized = value.casefold()
            return any(marker in normalized for marker in _SENSITIVE_VALUE_MARKERS)
        return False

    @classmethod
    def _sanitize_runtime_result(cls, value: Any, *, key: object | None = None) -> Any:
        if key is not None and cls._sensitive_key(key):
            return REDACTED
        if isinstance(value, Mapping):
            return {
                str(child_key): cls._sanitize_runtime_result(child, key=child_key)
                for child_key, child in value.items()
            }
        if isinstance(value, list):
            return [cls._sanitize_runtime_result(child) for child in value]
        if isinstance(value, tuple):
            return [cls._sanitize_runtime_result(child) for child in value]
        if isinstance(value, str) and cls._secret_exposed(value):
            return REDACTED
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return REDACTED


__all__ = ["IntegrationApplication", "MAX_RESULTS", "RUNTIME_TIMEOUT_SECONDS"]
