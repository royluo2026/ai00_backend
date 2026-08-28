from __future__ import annotations

from dataclasses import dataclass
import asyncio
from contextlib import suppress
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
    def __init__(self, client: DomainCapabilityClient, catalog=None):
        self._client = client
        self._catalog = catalog

    async def apply_batch(
        self, *, adapter: TargetAdapter, payload: Mapping[str, Any], idempotency_key: str,
        correlation: CorrelationRef, identity: ConsumerIdentity,
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
        return await self._client.invoke(invocation, identity, correlation)


class ImportDispatcher:
    """Claim and execute one durable Integration import through the governed Gateway."""

    def __init__(self, repository, connector_runtime, sync_service: SyncService, identity_factory):
        self._repository = repository
        self._runtime = connector_runtime
        self._sync = sync_service
        self._identity_factory = identity_factory

    async def dispatch_next(self, *, worker_id: str, correlation: CorrelationRef) -> Mapping[str, Any] | None:
        run = self._repository.claim_next_import_run(worker_id)
        if run is None:
            return None
        scope = {"owner_gid": run["owner_gid"], "team_gid": run.get("team_gid")}
        try:
            identity = self._identity_factory(run)
            if identity.actor.user_id != run["owner_gid"] or identity.tenant.tenant_id != (run.get("team_gid") or f"user:{run['owner_gid']}"):
                return self._finish(run, "failed", error_code="worker_principal_mismatch")
            mapping = self._repository.get_mapping({**scope, "gid": run["mapping_gid"]})
            if mapping is None or mapping.get("status") == "binding_required":
                return self._finish(run, "failed", error_code="target_binding_unavailable")
            connector = self._repository.get_connector({**scope, "gid": mapping["datasource_gid"]})
            if connector is None:
                return self._finish(run, "failed", error_code="resource_not_found")
            invocation = dict(run["target_invocation"])
            if run.get("target_dispatched_at"):
                payload = dict(invocation["payload"])
            else:
                raw = await asyncio.wait_for(
                    self._runtime.preview(connector, mapping, timeout_seconds=15, result_limit=200),
                    timeout=15,
                )
                rows = self._transform_rows(raw, mapping)
                payload = {**dict(invocation["payload"]), "rows": rows}
                invocation = {**invocation, "payload": payload}
                run = {**run, **self._repository.mark_target_invocation(
                    run_id=run["run_id"], claim_token=run["claim_token"], owner_gid=run["owner_gid"],
                    team_gid=run.get("team_gid"), target_invocation=invocation,
                    target_idempotency_key=str(run.get("target_idempotency_key") or f"{run['run_id']}:target"),
                ), "target_invocation": invocation}
            result = await self._sync.apply_batch(
                adapter=TargetAdapter(
                    target_domain=str(mapping["target_domain"]),
                    capability_id=str(invocation["capability_id"]),
                    major_version=int(invocation["major_version"]),
                    minimum_catalog_release=str(invocation["minimum_catalog_release"]),
                ),
                payload=payload,
                idempotency_key=str(run.get("target_idempotency_key") or f"{run['run_id']}:target"),
                correlation=correlation, identity=identity,
            )
            if getattr(result, "status", None) is CapabilityStatus.OUTCOME_UNKNOWN:
                return self._uncertain(run, "target_outcome_unknown")
            if not getattr(result, "ok", False):
                return self._finish(
                    run, "failed", error_code=getattr(getattr(result, "error", None), "code", None) or "target_failed"
                )
            return self._finish(run, "succeeded", result={"target": result.data or {}})
        except TimeoutError:
            return self._uncertain(run, "external_timeout")
        except Exception as exc:
            return self._finish(run, "failed", error_code=type(exc).__name__)

    def _finish(self, run, status, *, result=None, error_code=None):
        return self._repository.transition_import_run(
            run_id=run["run_id"], claim_token=run["claim_token"],
            owner_gid=run["owner_gid"], team_gid=run.get("team_gid"), status=status,
            result=result, error_code=error_code,
        )

    def _uncertain(self, run, error_code):
        return self._repository.record_import_uncertainty(
            run_id=run["run_id"], claim_token=run["claim_token"], owner_gid=run["owner_gid"],
            team_gid=run.get("team_gid"), error_code=error_code,
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


@dataclass(frozen=True)
class ImportWorkerHealth:
    status: str
    consecutive_errors: int
    last_error_code: str | None
    retry_delay_seconds: float


class IntegrationImportWorker:
    """Lifecycle-managed bounded poller for accepted and reconcilable imports."""

    def __init__(
        self, dispatcher: ImportDispatcher, *, worker_id: str = "integration-import",
        idle_seconds: float = 0.25, maximum_backoff_seconds: float = 5.0,
    ):
        self._dispatcher = dispatcher
        self._worker_id = worker_id
        self._idle_seconds = max(0.05, float(idle_seconds))
        self._maximum_backoff_seconds = max(self._idle_seconds, float(maximum_backoff_seconds))
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()
        self._health = ImportWorkerHealth("stopped", 0, None, 0.0)

    @property
    def health(self) -> ImportWorkerHealth:
        return self._health

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self._task is None:
            self._stopping.clear()
            self._health = ImportWorkerHealth("starting", 0, self._health.last_error_code, 0.0)
            self._task = asyncio.create_task(self._run(), name=self._worker_id)

    async def stop(self) -> None:
        self._stopping.set()
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await task
        self._health = ImportWorkerHealth(
            "stopped", self._health.consecutive_errors, self._health.last_error_code, 0.0,
        )

    @staticmethod
    def _is_transient(exc: Exception) -> bool:
        if isinstance(exc, (ConnectionError, TimeoutError)):
            return True
        return (
            type(exc).__module__.startswith("pymysql.")
            and type(exc).__name__ in {"InterfaceError", "OperationalError"}
        )

    async def _run(self) -> None:
        while not self._stopping.is_set():
            correlation = CorrelationRef(request_id=f"{self._worker_id}-{id(asyncio.current_task())}")
            try:
                consumed = await self._dispatcher.dispatch_next(
                    worker_id=self._worker_id, correlation=correlation,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if not self._is_transient(exc):
                    self._health = ImportWorkerHealth(
                        "fatal", self._health.consecutive_errors,
                        type(exc).__name__, 0.0,
                    )
                    raise
                failures = min(self._health.consecutive_errors + 1, 31)
                delay = min(
                    self._maximum_backoff_seconds,
                    self._idle_seconds * (2 ** min(failures - 1, 10)),
                )
                self._health = ImportWorkerHealth(
                    "degraded", failures, type(exc).__name__, delay,
                )
                await asyncio.sleep(delay)
                continue
            self._health = ImportWorkerHealth(
                "healthy", 0, self._health.last_error_code, 0.0,
            )
            if consumed is None:
                await asyncio.sleep(self._idle_seconds)
            else:
                await asyncio.sleep(0)
