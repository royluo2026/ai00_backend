from __future__ import annotations

from dataclasses import dataclass
import asyncio
from typing import Any, Mapping

from backend.capability_v2.contracts import ConsumerIdentity, CorrelationRef
from backend.capability_v2.domain_client import DomainCapabilityClient, DomainInvocation
from backend.capability_v2.contracts import CapabilityStatus

from .transform import RestrictedExpression


@dataclass(frozen=True)
class TargetAdapter:
    target_domain: str
    capability_id: str
    major_version: int
    minimum_catalog_release: str


class SyncService:
    def __init__(self, client: DomainCapabilityClient, identity: ConsumerIdentity, catalog=None):
        self._client = client
        self._identity = identity
        self._catalog = catalog

    async def apply_batch(
        self, *, adapter: TargetAdapter, payload: Mapping[str, Any], idempotency_key: str,
        correlation: CorrelationRef,
    ) -> Any:
        if not adapter.capability_id.startswith(adapter.target_domain + "."):
            raise ValueError("target adapter domain and capability do not match")
        if self._catalog is None:
            raise ValueError("target catalog is required at dispatch")
        self._catalog.require_stable(
            adapter.capability_id, adapter.major_version, adapter.minimum_catalog_release
        )
        invocation = DomainInvocation(
            capability_id=adapter.capability_id,
            major_version=adapter.major_version,
            payload=dict(payload),
            idempotency_key=idempotency_key,
        )
        return await self._client.invoke(invocation, self._identity, correlation)


class ImportDispatcher:
    """Claim and execute one durable Integration import through the governed Gateway."""

    def __init__(self, repository, connector_runtime, sync_service: SyncService):
        self._repository = repository
        self._runtime = connector_runtime
        self._sync = sync_service

    async def dispatch_next(self, *, worker_id: str, correlation: CorrelationRef) -> Mapping[str, Any] | None:
        run = self._repository.claim_next_import_run(worker_id)
        if run is None:
            return None
        scope = {"owner_gid": run["owner_gid"], "team_gid": run.get("team_gid")}
        try:
            mapping = self._repository.get_mapping({**scope, "gid": run["mapping_gid"]})
            if mapping is None or mapping.get("status") == "binding_required":
                return self._finish(run, "failed", error_code="target_binding_unavailable")
            connector = self._repository.get_connector({**scope, "gid": mapping["datasource_gid"]})
            if connector is None:
                return self._finish(run, "failed", error_code="resource_not_found")
            raw = await asyncio.wait_for(
                self._runtime.preview(connector, mapping, timeout_seconds=15, result_limit=200),
                timeout=15,
            )
            rows = self._transform_rows(raw, mapping)
            invocation = dict(run["target_invocation"])
            payload = {**dict(invocation["payload"]), "rows": rows}
            result = await self._sync.apply_batch(
                adapter=TargetAdapter(
                    target_domain=str(mapping["target_domain"]),
                    capability_id=str(invocation["capability_id"]),
                    major_version=int(invocation["major_version"]),
                    minimum_catalog_release=str(invocation["minimum_catalog_release"]),
                ),
                payload=payload,
                idempotency_key=f"{run['run_id']}:target",
                correlation=correlation,
            )
            if getattr(result, "status", None) is CapabilityStatus.OUTCOME_UNKNOWN:
                return self._finish(run, "outcome_unknown", error_code="target_outcome_unknown")
            if not getattr(result, "ok", False):
                return self._finish(
                    run, "failed", error_code=getattr(getattr(result, "error", None), "code", None) or "target_failed"
                )
            return self._finish(run, "succeeded", result={"target": result.data or {}})
        except TimeoutError:
            return self._finish(run, "outcome_unknown", error_code="external_timeout")
        except Exception as exc:
            return self._finish(run, "failed", error_code=type(exc).__name__)

    def _finish(self, run, status, *, result=None, error_code=None):
        return self._repository.transition_import_run(
            run_id=run["run_id"], claim_token=run["claim_token"],
            owner_gid=run["owner_gid"], team_gid=run.get("team_gid"), status=status,
            result=result, error_code=error_code,
        )

    @staticmethod
    def _transform_rows(raw: Mapping[str, Any], mapping: Mapping[str, Any]) -> list[dict[str, Any]]:
        result = []
        source_rows = list(raw.get("rows") or ())[:200]
        fields = list(mapping.get("field_mappings") or ())[:200]
        for index, source in enumerate(source_rows):
            if not isinstance(source, Mapping):
                continue
            values = []
            for field in fields:
                expression = field.get("transform_expression")
                value = (
                    RestrictedExpression(str(expression)).evaluate(source)
                    if expression else source.get(str(field["source_field"]))
                )
                values.append({"field": str(field["target_field"]), "value": value})
            result.append({"key": str(index + 1), "values": values})
        return result
