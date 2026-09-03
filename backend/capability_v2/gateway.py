"""The sole governed execution pipeline for Capability V2 consumers."""
from __future__ import annotations

import inspect
import asyncio
import hashlib
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from backend.capabilities.models_next import CapabilityBusinessError, CapabilityContext, CapabilityOutput
from .provider_contracts import CapabilityStreamOutput
from backend.capabilities.validation_next import validate_payload

from .catalog import CatalogRelease, CatalogResolutionError, CatalogResolver, build_release, load_catalog_release
from .catalog_store import InMemoryCatalogStore
from .contracts import (
    CapabilityErrorV2,
    CapabilityResultV2,
    CapabilityStatus,
    CorrelationRef,
    EvidenceRefV2,
    InvocationEnvelope,
    OperationRef,
    OperationStatus,
    SideEffectLevel,
)
from .policies import (
    FailClosedGatewayPolicy,
    GatewayPolicy,
    GatewayPolicyError,
)
from .operations import OperationService
from .metrics import CapabilityMetricRecord, InMemoryCapabilityMetrics
from .projection import project_result
from .reliability import (
    InvocationLease, ReliabilityCoordinator, ReliabilityError, TransactionalCapabilityOutput,
)
from .reliability import IssuedApproval
from .resource_budget import (
    AdmissionLease, AdmissionRejected, MemoryPressureSampler, ResourceAdmissionController,
)


_log = logging.getLogger(__name__)


@dataclass
class _ManagedStream:
    iterator: Any
    media_type: str
    descriptor: Any
    envelope: InvocationEnvelope
    authorization: Any
    lease: InvocationLease | None
    admission_lease: AdmissionLease
    started: float
    before: Any
    capability_key: str
    output: dict[str, Any]
    deadline_at: float
    max_events: int
    expiry_task: asyncio.Task | None = None
    finalize_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    iteration_started: bool = False
    iterator_closed: bool = False
    outcome_finalized: bool = False
    admission_released: bool = False
    metric_recorded: bool = False
    finalized: bool = False


class _ClaimedStreamIterator:
    """Async iterator whose close works even before the generator body starts."""

    def __init__(self, iterator, close_unstarted):
        self._iterator = iterator
        self._close_unstarted = close_unstarted
        self._lock = asyncio.Lock()
        self._started = False
        self._closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        async with self._lock:
            if self._closed:
                raise StopAsyncIteration
            self._started = True
            try:
                return await anext(self._iterator)
            except (StopAsyncIteration, BaseException):
                self._closed = True
                raise

    async def aclose(self):
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            if self._started:
                await self._iterator.aclose()
            else:
                await self._close_unstarted()


class CapabilityGatewayService:
    def __init__(self, resolver: CatalogResolver, policy: GatewayPolicy | None = None,
                 *, reliability: ReliabilityCoordinator | None = None,
                 operations: OperationService | None = None,
                 admission: ResourceAdmissionController | None = None,
                 metrics: InMemoryCapabilityMetrics | None = None,
                 admission_timeout_seconds: float = 0.25,
                 stream_claim_ttl_seconds: float = 15.0,
                 max_pending_streams: int = 128) -> None:
        self._resolver = resolver
        self._policy = policy or FailClosedGatewayPolicy()
        self._reliability = reliability
        self._operations = operations
        self._admission = admission or ResourceAdmissionController(MemoryPressureSampler())
        self._metrics = metrics or InMemoryCapabilityMetrics()
        self._admission_timeout_seconds = max(0.0, admission_timeout_seconds)
        self._catalog_release: str | None = None
        self._streams: dict[str, _ManagedStream] = {}
        self._stream_claim_ttl_seconds = max(0.1, stream_claim_ttl_seconds)
        self._max_pending_streams = max(1, max_pending_streams)

    @property
    def catalog_release(self) -> str:
        if self._catalog_release is None:
            raise RuntimeError("Gateway catalog release is not bound.")
        return self._catalog_release

    def bind_release(self, release_id: str) -> "CapabilityGatewayService":
        self._catalog_release = release_id
        return self

    def catalog(self, release_id: str | None = None) -> CatalogRelease:
        return self._resolver.catalog(release_id or self.catalog_release)

    def recent_metrics(self) -> tuple[CapabilityMetricRecord, ...]:
        """Return payload-free in-process measurements for administrator diagnostics."""
        return self._metrics.recent()

    async def request_approval(self, envelope: InvocationEnvelope) -> IssuedApproval:
        try:
            descriptor, provider = self._resolve_envelope(envelope)
        except GatewayPolicyError:
            raise
        except CatalogResolutionError as exc:
            raise GatewayPolicyError(
                "catalog_resolution_failed", "Capability catalog resolution failed."
            ) from exc
        if not descriptor.exposure.allows(envelope.identity.consumer.type):
            raise GatewayPolicyError("consumer_not_allowed", "Consumer is not exposed.")
        if descriptor.confirmation_policy == "none":
            raise GatewayPolicyError("confirmation_not_required", "Confirmation is not required.")
        if (
            descriptor.side_effect_level is not SideEffectLevel.READ
            and descriptor.consistency_policy == "strong"
            and not getattr(provider.handler, "__capability_transactional__", False)
        ):
            raise GatewayPolicyError(
                "transaction_participant_required",
                "Strong writes require a transactional capability provider."
            )
        try:
            authorization = self._policy.authorize(descriptor, envelope, provider)
        except GatewayPolicyError:
            raise
        except Exception as exc:
            raise GatewayPolicyError(
                "authorization_failed", "Capability authorization service failed."
            ) from exc
        if authorization is None:
            raise GatewayPolicyError("authorization_failed", "Authorization decision is unavailable.")
        try:
            validate_payload(dict(descriptor.input_schema), dict(envelope.payload))
        except (TypeError, ValueError) as exc:
            raise GatewayPolicyError("invalid_input", str(exc)) from exc
        concurrency_error = self._concurrency_error(descriptor, envelope)
        if concurrency_error:
            raise GatewayPolicyError(concurrency_error, "Expected resource version is invalid.")
        try:
            return self._policy.issue_approval(descriptor, envelope, provider, authorization)
        except GatewayPolicyError:
            raise
        except Exception as exc:
            raise GatewayPolicyError(
                "approval_service_failed", "Approval service failed."
            ) from exc

    async def invoke(self, envelope: InvocationEnvelope) -> CapabilityResultV2:
        try:
            descriptor, provider = self._resolve_envelope(envelope)
        except GatewayPolicyError as exc:
            return self._rejected(envelope, exc.code, exc.message)
        except CatalogResolutionError:
            return self._rejected(
                envelope, "catalog_resolution_failed", "Capability catalog resolution failed."
            )

        if not descriptor.exposure.allows(envelope.identity.consumer.type):
            return self._rejected(envelope, "consumer_not_allowed", "Consumer is not exposed to this capability.")

        try:
            authorization = self._policy.authorize(descriptor, envelope, provider)
        except GatewayPolicyError as exc:
            return project_result(
                self._rejected(envelope, exc.code, exc.message),
                descriptor,
                envelope.identity,
            )
        except Exception:
            return self._failed(
                envelope, "authorization_failed", "Capability authorization service failed."
            )

        try:
            validate_payload(dict(descriptor.input_schema), dict(envelope.payload))
        except (TypeError, ValueError) as exc:
            return self._rejected(envelope, "invalid_input", str(exc))
        input_bytes = self._json_size(dict(envelope.payload))
        if input_bytes > descriptor.execution_budget.max_input_bytes:
            return self._rejected(
                envelope,
                "capability_input_limit_exceeded",
                "Capability input exceeds its declared byte limit.",
            )
        concurrency_error = self._concurrency_error(descriptor, envelope)
        if concurrency_error:
            return self._rejected(
                envelope, concurrency_error, "Expected resource version is invalid."
            )

        is_write = descriptor.side_effect_level is not SideEffectLevel.READ
        payload_idempotency = envelope.payload.get("idempotency_key")
        if payload_idempotency is not None and payload_idempotency != envelope.idempotency_key:
            return self._rejected(
                envelope, "idempotency_key_mismatch",
                "Payload and invocation idempotency keys must match.",
            )
        if descriptor.operation_policy == "required" and self._operations is None:
            return self._rejected(
                envelope, "operation_service_unavailable",
                "Durable asynchronous operations are not configured.",
            )
        if is_write and self._reliability is None:
            return self._rejected(
                envelope, "reliability_unavailable",
                "Durable write reliability is not configured."
            )
        if is_write:
            try:
                replay = self._reliability.replay(envelope)
            except ReliabilityError as exc:
                return self._rejected(envelope, str(exc), "Reliable invocation was rejected.")
            except Exception:
                return self._failed(
                    envelope, "reliability_failed", "Durable reliability service failed."
                )
            if replay is not None:
                return project_result(
                    replay, descriptor, envelope.identity,
                    data_scopes=authorization.data_scopes if authorization is not None else (),
                )
            if (
                descriptor.consistency_policy == "strong"
                and not getattr(provider.handler, "__capability_transactional__", False)
            ):
                return self._rejected(
                    envelope,
                    "transaction_participant_required",
                    "Strong writes require a transactional capability provider."
                )

        try:
            self._policy.approve(descriptor, envelope, provider, authorization)
        except GatewayPolicyError as exc:
            return project_result(
                self._rejected(envelope, exc.code, exc.message),
                descriptor,
                envelope.identity,
                data_scopes=authorization.data_scopes if authorization is not None else (),
            )
        except Exception:
            return self._failed(envelope, "approval_failed", "Capability approval service failed.")

        lease: InvocationLease | None = None
        if is_write:
            try:
                lease = self._reliability.begin(
                    envelope,
                    descriptor,
                    policy_version=(authorization.policy_version
                                    if authorization is not None else "unversioned"),
                )
            except ReliabilityError as exc:
                return self._rejected(envelope, str(exc), "Reliable invocation was rejected.")
            except Exception:
                return self._failed(
                    envelope, "reliability_failed", "Durable reliability service failed."
                )
            if lease.replay_result is not None:
                return project_result(
                    lease.replay_result, descriptor, envelope.identity,
                    data_scopes=authorization.data_scopes if authorization is not None else (),
                )

        async_operation = None
        if descriptor.operation_policy == "required":
            try:
                async_operation = self._operations.create(
                    kind=descriptor.id,
                    requested_by=envelope.identity,
                    resource_refs=(authorization.resource_refs if authorization is not None else ()),
                )
            except Exception:
                result = self._failed(
                    envelope, "operation_create_failed", "The asynchronous operation could not be created."
                )
                if lease is not None:
                    try:
                        self._reliability.complete(lease, result)
                    except Exception:
                        return self._failed(
                            envelope, "operation_create_outcome_failed",
                            "The asynchronous operation was not dispatched.",
                        )
                return result

        context = self._legacy_context(
            envelope, operation_id=(
                async_operation.operation_id if async_operation is not None else
                lease.operation_id if lease is not None else None
            ),
            outcome_operation_id=lease.operation_id if lease is not None else None,
            async_operation_id=(
                async_operation.operation_id if async_operation is not None else None
            ),
        )
        capability_key = f"{descriptor.id}@{descriptor.major_version}"
        started = time.perf_counter()
        before = self._admission.snapshot()
        output_bytes = 0
        admission_lease: AdmissionLease | None = None
        try:
            admission_lease = await self._admission.acquire(
                capability_key=capability_key,
                tenant_key=envelope.identity.tenant.tenant_id,
                consumer_key=self._consumer_key(envelope),
                budget=descriptor.execution_budget,
                timeout_seconds=self._admission_timeout_seconds,
            )
        except AdmissionRejected as exc:
            result = self._rejected(
                envelope, exc.code, "Capability capacity is temporarily unavailable.",
                retryable=exc.retryable,
            )
            self._record_metric(
                descriptor, envelope, started, before, output_bytes, result, capability_key,
            )
            return project_result(
                result, descriptor, envelope.identity,
                data_scopes=authorization.data_scopes if authorization is not None else (),
            )
        transaction = None
        cancelled = False
        stream_output: CapabilityStreamOutput | None = None
        stream_id: str | None = None
        defer_stream = False
        try:
            try:
                value = provider.handler(dict(envelope.payload), context)
                if inspect.isawaitable(value):
                    try:
                        value = await asyncio.wait_for(
                            value,
                            timeout=self._provider_timeout_seconds(descriptor, envelope),
                        )
                    except TimeoutError as exc:
                        raise CapabilityBusinessError(
                            "runtime_timeout",
                            "Capability provider exceeded its execution deadline.",
                            retryable=True,
                        ) from exc
            except LookupError as exc:
                raise CapabilityBusinessError(
                    "resource_not_found", "The requested resource was not found."
                ) from exc
            except (TypeError, ValueError) as exc:
                raise CapabilityBusinessError(
                    "invalid_input", "The provider rejected the supplied input."
                ) from exc
            evidence = ()
            if isinstance(value, CapabilityStreamOutput):
                stream_output = value
                if len(self._streams) >= self._max_pending_streams:
                    raise CapabilityBusinessError(
                        "stream_capacity_exceeded",
                        "Gateway pending stream capacity is exhausted.",
                        retryable=True,
                    )
                stream_id = f"capability-stream-{uuid.uuid4().hex}"
                value = json.loads(json.dumps(value.output))
                value.setdefault("data", {})["stream_id"] = stream_id
            elif isinstance(value, TransactionalCapabilityOutput):
                transaction = value.transaction
                evidence = tuple(EvidenceRefV2(
                    kind=item.kind,
                    reference=item.reference,
                    digest=item.digest,
                    summary=item.summary,
                ) for item in value.evidence)
                value = value.data
            elif isinstance(value, CapabilityOutput):
                evidence = tuple(EvidenceRefV2(
                    kind=item.kind,
                    reference=item.reference,
                    digest=item.digest,
                    summary=item.summary,
                ) for item in value.evidence)
                value = value.data
            if is_write and descriptor.consistency_policy == "strong" and transaction is None:
                raise CapabilityBusinessError(
                    "transaction_participant_required",
                    "Strong writes require an open transaction participant.",
                )
            if descriptor.evidence_policy == "required" and not evidence:
                raise CapabilityBusinessError(
                    "evidence_required",
                    "Capability provider did not return required evidence.",
                )
            validate_payload(dict(descriptor.output_schema), value, label="output")
            output_bytes = self._json_size(value)
            if output_bytes > descriptor.execution_budget.max_output_bytes:
                raise CapabilityBusinessError(
                    "capability_output_limit_exceeded",
                    "Capability provider exceeded its declared output byte limit.",
                )
            projected = self._policy.project(descriptor, envelope.identity, value)
            defer_stream = stream_output is not None
        except asyncio.CancelledError:
            cancelled = True
            if transaction is not None:
                self._rollback_and_close(transaction)
                transaction = None
            raise
        except CapabilityBusinessError as exc:
            if transaction is not None:
                self._rollback_and_close(transaction)
                transaction = None
            result = self._rejected(
                envelope,
                exc.code,
                exc.message,
                retryable=exc.retryable,
                details=exc.details,
            )
        except Exception:
            if transaction is not None:
                self._rollback_and_close(transaction)
                transaction = None
            _log.exception(
                "Capability provider failed: %s@%s request_id=%s",
                envelope.capability_id,
                envelope.major_version,
                envelope.request_id,
            )
            result = self._failed(envelope, "provider_failed", "Capability provider failed.")
        else:
            if async_operation is not None:
                result = CapabilityResultV2.accepted(
                    envelope.capability_id, envelope.major_version,
                    envelope.request_id, async_operation,
                ).model_copy(update={"evidence": evidence})
            else:
                result = CapabilityResultV2(
                    ok=True,
                    status=CapabilityStatus.COMPLETED,
                    capability_id=envelope.capability_id,
                    major_version=envelope.major_version,
                    data=projected,
                    evidence=evidence,
                    correlation=CorrelationRef(request_id=envelope.request_id, trace_id=envelope.trace_id),
                )
        finally:
            if admission_lease is not None and not defer_stream:
                await admission_lease.release()
            if stream_output is not None and not defer_stream:
                await self._close_stream_iterator(stream_output.iterator)
            if cancelled:
                self._record_metric(
                    descriptor, envelope, started, before, output_bytes, None, capability_key,
                    cancelled=True,
                )
        if defer_stream and result.ok and stream_output is not None and stream_id is not None:
            result = result.model_copy(update={
                "status": CapabilityStatus.ACCEPTED,
                "operation_ref": (
                    OperationRef(operation_id=lease.operation_id, status=OperationStatus.RUNNING)
                    if lease is not None else None
                ),
            })
            projected_result = project_result(
                result, descriptor, envelope.identity,
                data_scopes=authorization.data_scopes if authorization is not None else (),
            )
            record = _ManagedStream(
                iterator=stream_output.iterator, media_type=stream_output.media_type,
                descriptor=descriptor, envelope=envelope, authorization=authorization,
                lease=lease, admission_lease=admission_lease, started=started,
                before=before, capability_key=capability_key, output=value,
                deadline_at=time.perf_counter() + self._provider_timeout_seconds(descriptor, envelope),
                max_events=max(1, stream_output.max_events),
            )
            self._streams[stream_id] = record
            deadline_remaining = max(0.0, record.deadline_at - time.perf_counter())
            claim_timeout = min(self._stream_claim_ttl_seconds, deadline_remaining)
            record.expiry_task = asyncio.create_task(
                self._expire_stream(
                    stream_id, claim_timeout,
                    deadline_expiry=deadline_remaining <= self._stream_claim_ttl_seconds,
                )
            )
            return projected_result

        if async_operation is not None and not result.ok:
            try:
                failed_ref = self._operations.transition(
                    async_operation.operation_id, OperationStatus.FAILED,
                    expected_version=async_operation.version,
                    requested_by=envelope.identity,
                    error_code=result.error.code if result.error else "provider_failed",
                    granted_resources=(authorization.resource_refs if authorization is not None else ()),
                )
                result = result.model_copy(update={"operation_ref": failed_ref})
            except Exception:
                pass
        if lease is not None:
            operation_status = (
                OperationStatus.COMPLETED if result.ok else OperationStatus.FAILED
            )
            if async_operation is None:
                result = result.model_copy(update={
                    "operation_ref": OperationRef(
                        operation_id=lease.operation_id, status=operation_status
                    )
                })
            try:
                self._reliability.complete(
                    lease,
                    result,
                    transaction=transaction,
                    preserve_projected_data=(descriptor.replay_data_policy == "projected"),
                )
                if transaction is not None:
                    transaction.commit()
            except Exception:
                if transaction is not None:
                    try:
                        transaction.rollback()
                    except Exception:
                        pass
                unknown = CapabilityResultV2(
                    ok=False,
                    status=CapabilityStatus.OUTCOME_UNKNOWN,
                    capability_id=envelope.capability_id,
                    major_version=envelope.major_version,
                    operation_ref=OperationRef(
                        operation_id=lease.operation_id,
                        status=OperationStatus.OUTCOME_UNKNOWN,
                    ),
                    error=CapabilityErrorV2(
                        code="outcome_persistence_failed",
                        message="The provider may have committed, but its durable outcome could not be recorded.",
                    ),
                    correlation=CorrelationRef(
                        request_id=envelope.request_id, trace_id=envelope.trace_id
                    ),
                )
                try:
                    self._reliability.mark_unknown(lease, unknown)
                except Exception:
                    pass
                return unknown
            finally:
                if transaction is not None:
                    try:
                        transaction.close()
                    except Exception:
                        pass
        elif transaction is not None:
            self._rollback_and_close(transaction)
            return self._failed(
                envelope, "unexpected_transaction",
                "A transactional provider requires durable write reliability."
            )
        projected_result = project_result(
            result,
            descriptor,
            envelope.identity,
            data_scopes=authorization.data_scopes if authorization is not None else (),
        )
        if projected_result.ok and projected_result.data is not None:
            projection_schema = (
                descriptor.agent_output_schema
                if envelope.identity.consumer.type.value in {"agent", "mcp"}
                and descriptor.agent_output_schema is not None
                else descriptor.output_schema
            )
            try:
                validate_payload(
                    dict(projection_schema), projected_result.data, label="projected_output"
                )
            except (TypeError, ValueError):
                projected_result = project_result(
                    self._failed(
                        envelope,
                        "projection_contract_failed",
                        "Capability projection violated its declared output contract.",
                    ),
                    descriptor,
                    envelope.identity,
                    data_scopes=(
                        authorization.data_scopes if authorization is not None else ()
                    ),
                )
        self._record_metric(
            descriptor, envelope, started, before, output_bytes, projected_result, capability_key,
        )
        return projected_result

    async def claim_stream(self, stream_id: str):
        """Claim one Gateway-owned stream while retaining invocation leases."""
        record = self._streams.pop(stream_id, None)
        if record is None:
            raise ValueError("Capability stream is missing, expired, or already claimed")
        if record.expiry_task is not None:
            record.expiry_task.cancel()
        deadline_remaining = max(0.0, record.deadline_at - time.perf_counter())
        claim_timeout = min(self._stream_claim_ttl_seconds, deadline_remaining)
        record.expiry_task = asyncio.create_task(self._expire_claimed_stream(
            record, claim_timeout,
            deadline_expiry=deadline_remaining <= self._stream_claim_ttl_seconds,
        ))

        async def managed():
            await self._begin_stream_iteration(record)
            if record.expiry_task is not None:
                record.expiry_task.cancel()
                record.expiry_task = None
            output_bytes = self._json_size(record.output)
            event_count = 0
            completed = False
            cancelled = False
            failure: Exception | None = None
            try:
                remaining = max(0.0, record.deadline_at - time.perf_counter())
                async with asyncio.timeout(remaining):
                    async for chunk in record.iterator:
                        event_count += 1
                        if event_count > record.max_events:
                            raise CapabilityBusinessError(
                                "capability_output_limit_exceeded",
                                "Capability stream exceeded its declared event limit.",
                            )
                        output_bytes += len(chunk) if isinstance(chunk, bytes) else len(str(chunk).encode("utf-8"))
                        if output_bytes > record.descriptor.execution_budget.max_output_bytes:
                            raise CapabilityBusinessError(
                                "capability_output_limit_exceeded",
                                "Capability stream exceeded its declared output byte limit.",
                            )
                        yield chunk
                completed = True
            except asyncio.CancelledError:
                cancelled = True
                raise
            except GeneratorExit:
                cancelled = True
                raise
            except Exception as exc:
                failure = exc
                raise
            finally:
                await self._finalize_stream(
                    record, output_bytes=output_bytes, completed=completed,
                    cancelled=cancelled, failure=failure,
                )

        async def close_unstarted():
            if record.expiry_task is not None:
                record.expiry_task.cancel()
                record.expiry_task = None
            await self._finalize_stream(
                record, output_bytes=self._json_size(record.output), completed=False,
                cancelled=True, failure=None,
            )

        return _ClaimedStreamIterator(managed(), close_unstarted), record.media_type

    async def _expire_stream(
        self, stream_id: str, delay: float, *, deadline_expiry: bool,
    ) -> None:
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        record = self._streams.pop(stream_id, None)
        if record is None:
            return
        await self._finalize_stream(
            record, output_bytes=self._json_size(record.output), completed=False,
            cancelled=not deadline_expiry, failure=TimeoutError("stream claim expired"),
        )

    async def _expire_claimed_stream(
        self, record: _ManagedStream, delay: float, *, deadline_expiry: bool,
    ) -> None:
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        await self._finalize_stream(
            record, output_bytes=self._json_size(record.output), completed=False,
            cancelled=not deadline_expiry,
            failure=TimeoutError("claimed stream was not consumed before its lifecycle bound"),
            only_if_unstarted=True,
        )

    @staticmethod
    async def _begin_stream_iteration(record: _ManagedStream) -> None:
        async with record.finalize_lock:
            if record.finalized:
                raise ValueError("Capability stream expired before iteration started")
            record.iteration_started = True

    async def _finalize_stream(
        self, record: _ManagedStream, *, output_bytes: int, completed: bool,
        cancelled: bool, failure: Exception | None, only_if_unstarted: bool = False,
    ) -> None:
        current = asyncio.current_task()
        if record.expiry_task is not None and record.expiry_task is not current:
            if not only_if_unstarted:
                record.expiry_task.cancel()
        async with record.finalize_lock:
            if record.finalized:
                return
            if only_if_unstarted and record.iteration_started:
                return
            if completed:
                result = CapabilityResultV2(
                    ok=True, status=CapabilityStatus.COMPLETED,
                    capability_id=record.envelope.capability_id,
                    major_version=record.envelope.major_version,
                    data=record.output,
                    correlation=CorrelationRef(
                        request_id=record.envelope.request_id,
                        trace_id=record.envelope.trace_id,
                    ),
                    operation_ref=(
                        OperationRef(operation_id=record.lease.operation_id, status=OperationStatus.COMPLETED)
                        if record.lease is not None else None
                    ),
                )
            else:
                code = "cancelled" if cancelled else (
                    failure.code if isinstance(failure, CapabilityBusinessError) else
                    "runtime_timeout" if isinstance(failure, TimeoutError) else "provider_failed"
                )
                result = self._failed(
                    record.envelope, code, "Capability stream did not complete."
                )
                if record.lease is not None:
                    result = result.model_copy(update={
                        "operation_ref": OperationRef(
                            operation_id=record.lease.operation_id,
                            status=OperationStatus.CANCELLED if cancelled else OperationStatus.FAILED,
                        ),
                    })
            for _attempt in range(2):
                if not record.iterator_closed:
                    record.iterator_closed = await self._close_stream_iterator(record.iterator)
                if not record.outcome_finalized:
                    if record.lease is None:
                        record.outcome_finalized = True
                    else:
                        try:
                            self._reliability.complete(record.lease, result)
                            record.outcome_finalized = True
                        except Exception:
                            try:
                                self._reliability.mark_unknown(record.lease, result.model_copy(update={
                                    "status": CapabilityStatus.OUTCOME_UNKNOWN,
                                }))
                                record.outcome_finalized = True
                            except Exception:
                                pass
                if not record.admission_released:
                    try:
                        await record.admission_lease.release()
                        record.admission_released = True
                    except Exception:
                        pass
                if not record.metric_recorded:
                    try:
                        self._record_metric(
                            record.descriptor, record.envelope, record.started, record.before,
                            output_bytes, result, record.capability_key, cancelled=cancelled,
                        )
                        record.metric_recorded = True
                    except Exception:
                        pass
                record.finalized = all((
                    record.iterator_closed, record.outcome_finalized,
                    record.admission_released, record.metric_recorded,
                ))
                if record.finalized:
                    return
                await asyncio.sleep(0)
            _log.error(
                "Capability stream cleanup remains incomplete: %s@%s request_id=%s",
                record.envelope.capability_id, record.envelope.major_version,
                record.envelope.request_id,
            )

    @staticmethod
    async def _close_stream_iterator(iterator: Any) -> bool:
        closer = getattr(iterator, "aclose", None)
        if closer is None:
            return True
        try:
            await closer()
        except Exception:
            return False
        return True

    def _resolve_envelope(self, envelope: InvocationEnvelope):
        if self._catalog_release is None:
            raise GatewayPolicyError(
                "catalog_release_unbound", "Gateway catalog release is not bound."
            )
        if envelope.catalog_release != self._catalog_release:
            raise GatewayPolicyError(
                "catalog_resolution_failed", "Capability catalog resolution failed."
            )
        descriptor = self._resolver.descriptor(
            envelope.catalog_release, envelope.capability_id, envelope.major_version
        )
        now = datetime.now(UTC)
        if envelope.deadline is not None:
            if envelope.deadline.tzinfo is None or envelope.deadline.utcoffset() is None:
                raise GatewayPolicyError(
                    "deadline_invalid", "Invocation deadline must be timezone-aware."
                )
            if envelope.deadline.astimezone(UTC) <= now:
                raise GatewayPolicyError(
                    "deadline_exceeded", "Invocation deadline has expired."
                )
        if descriptor.required_auth_freshness_seconds > 0:
            authenticated_at = envelope.identity.actor.authenticated_at
            if authenticated_at.tzinfo is None or authenticated_at.utcoffset() is None:
                raise GatewayPolicyError(
                    "authentication_stale", "Authentication freshness cannot be verified."
                )
            oldest = now - timedelta(seconds=descriptor.required_auth_freshness_seconds)
            if authenticated_at.astimezone(UTC) < oldest:
                raise GatewayPolicyError(
                    "authentication_stale", "Authentication is older than the capability policy allows."
                )
        if descriptor.lifecycle_status.value == "retired":
            raise GatewayPolicyError(
                "capability_lifecycle_not_invocable", "Retired capability cannot be invoked."
            )
        provider = self._resolver.resolve(
            envelope.catalog_release, envelope.capability_id, envelope.major_version
        )
        return descriptor, provider

    @staticmethod
    def _provider_timeout_seconds(descriptor, envelope: InvocationEnvelope) -> float:
        timeout = float(descriptor.timeout_seconds)
        if envelope.deadline is not None:
            remaining = (envelope.deadline.astimezone(UTC) - datetime.now(UTC)).total_seconds()
            timeout = min(timeout, remaining)
        if timeout <= 0:
            raise CapabilityBusinessError(
                "runtime_timeout",
                "Capability provider exceeded its execution deadline.",
                retryable=True,
            )
        return timeout

    @staticmethod
    def _json_size(value: Any) -> int:
        return len(json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8"))

    @staticmethod
    def _consumer_key(envelope: InvocationEnvelope) -> str:
        consumer = envelope.identity.consumer
        return (
            consumer.mount_session_id
            or consumer.agent_run_id
            or consumer.installation_id
            or consumer.consumer_id
        )

    def _record_metric(
        self, descriptor, envelope: InvocationEnvelope, started: float, before,
        output_bytes: int, result: CapabilityResultV2 | None, capability_key: str,
        *, cancelled: bool = False,
    ) -> None:
        after = self._admission.snapshot()
        consumer_hash = hashlib.sha256(self._consumer_key(envelope).encode("utf-8")).hexdigest()
        self._metrics.record(CapabilityMetricRecord(
            capability_id=descriptor.id,
            major_version=descriptor.major_version,
            owner_domain=descriptor.owner_domain,
            consumer_type=envelope.identity.consumer.type.value,
            consumer_key_hash=consumer_hash,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            output_bytes=output_bytes,
            rss_before_bytes=before.rss_bytes,
            rss_after_bytes=after.rss_bytes,
            cgroup_ratio=after.ratio,
            in_flight=self._admission.in_flight(capability_key),
            cancelled=cancelled,
            error_code=("cancelled" if cancelled else (
                result.error.code if result is not None and result.error else None
            )),
        ))

    def reconcile_committed_agent_outcome(self, event: Mapping[str, Any]):
        """Converge a committed Agent write onto its durable Base outcome."""
        outcome_operation_id = str(event["outcome_operation_id"])
        capability_id = str(event["capability_id"])
        major_version = int(event["major_version"])
        request_id = str(event["request_id"])
        payload = dict(event["payload"])
        evidence = tuple(EvidenceRefV2(
            kind=item["kind"], reference=item["reference"],
            digest=item.get("digest"), summary=item.get("summary", ""),
        ) for item in payload.get("evidence", ()))
        async_operation_id = str(event.get("async_operation_id") or "")
        if async_operation_id:
            result = CapabilityResultV2.accepted(
                capability_id, major_version, request_id,
                OperationRef(
                    operation_id=async_operation_id, status=OperationStatus.RUNNING,
                ),
            ).model_copy(update={"evidence": evidence})
        else:
            result = CapabilityResultV2(
                ok=True, status=CapabilityStatus.COMPLETED,
                capability_id=capability_id, major_version=major_version,
                data=payload.get("data"), evidence=evidence,
                operation_ref=OperationRef(
                    operation_id=outcome_operation_id, status=OperationStatus.COMPLETED,
                ),
                correlation=CorrelationRef(request_id=request_id),
            )
        return self._reliability.reconcile_committed(outcome_operation_id, result)

    def _legacy_context(
        self, envelope: InvocationEnvelope, *, operation_id: str | None = None,
        outcome_operation_id: str | None = None,
        async_operation_id: str | None = None,
    ) -> CapabilityContext:
        actor = envelope.identity.actor
        return CapabilityContext(
            user_gid=actor.user_id or actor.service_id or "",
            team_gid=envelope.identity.tenant.tenant_id,
            active_roles=envelope.identity.tenant.active_roles,
            source=envelope.identity.consumer.type.value,
            request_id=envelope.request_id,
            confirmation_token=envelope.approval_reference,
            idempotency_key=envelope.idempotency_key,
            operation_id=operation_id,
            outcome_operation_id=outcome_operation_id,
            async_operation_id=async_operation_id,
            agent_run_id=envelope.identity.consumer.agent_run_id,
            # Plugin storage uses a server-derived consumer namespace. Agents receive
            # their own delegated consumer namespace; they cannot select another
            # plugin or agent namespace through request payload.
            plugin_id=(envelope.identity.consumer.consumer_id
                       if envelope.identity.consumer.type.value in {"plugin", "agent"} else None),
            plugin_version=envelope.identity.consumer.consumer_version,
            # Governance business approvals consume this server-created object
            # rather than caller-provided roles on the legacy context.
            effective_identity=envelope.identity,
            domain_client=__import__(
                "backend.capability_v2.domain_client", fromlist=["DomainCapabilityClient"]
            ).DomainCapabilityClient(self, parent_envelope=envelope),
        )

    @staticmethod
    def _concurrency_error(descriptor, envelope: InvocationEnvelope) -> str | None:
        if descriptor.concurrency_policy != "expected_version":
            return None
        expected = envelope.expected_resource_version
        if expected is None:
            return "expected_resource_version_required"
        current: Any = envelope.payload
        path = descriptor.expected_version_payload_path or ""
        parts = (
            [part.replace("~1", "/").replace("~0", "~") for part in path.lstrip("/").split("/")]
            if path.startswith("/") else path.split(".")
        )
        for part in parts:
            if not part or not isinstance(current, dict) or part not in current:
                return "expected_resource_version_payload_missing"
            current = current[part]
        if isinstance(current, (dict, list, tuple, set, bool)) or str(current) != expected:
            return "expected_resource_version_mismatch"
        return None

    @staticmethod
    def _rollback_and_close(transaction) -> None:
        try:
            transaction.rollback()
        except Exception:
            pass
        try:
            transaction.close()
        except Exception:
            pass

    @staticmethod
    def _rejected(envelope: InvocationEnvelope, code: str, message: str, *,
                  retryable: bool = False, details: dict[str, Any] | None = None) -> CapabilityResultV2:
        return CapabilityResultV2(
            ok=False,
            status=CapabilityStatus.REJECTED,
            capability_id=envelope.capability_id,
            major_version=envelope.major_version,
            error=CapabilityErrorV2(code=code, message=message, retryable=retryable, details=details or {}),
            correlation=CorrelationRef(request_id=envelope.request_id, trace_id=envelope.trace_id),
        )

    @staticmethod
    def _failed(envelope: InvocationEnvelope, code: str, message: str) -> CapabilityResultV2:
        return CapabilityResultV2(
            ok=False,
            status=CapabilityStatus.FAILED,
            capability_id=envelope.capability_id,
            major_version=envelope.major_version,
            error=CapabilityErrorV2(code=code, message=message),
            correlation=CorrelationRef(request_id=envelope.request_id, trace_id=envelope.trace_id),
        )

_default_gateway: CapabilityGatewayService | None = None


def configure_default_gateway(registry, *, policy: GatewayPolicy | None = None,
                              reliability: ReliabilityCoordinator | None = None,
                              operations: OperationService | None = None,
                              release_path: Path | None = None) -> CapabilityGatewayService:
    global _default_gateway
    path = release_path or Path(__file__).resolve().parents[2] / "docs" / "governance" / "capability-catalog-release.json"
    release = load_catalog_release(path.read_text(encoding="utf-8"))
    # The governance extension is a test-only catalog overlay.  It must be
    # visible to the HTTP Gateway only when the explicitly selected test
    # profile has also loaded the extension providers.  Production keeps the
    # immutable product release untouched and never probes this path.
    if release_path is None and _test_governance_registry_loaded(registry):
        extension_path = path.parent / "test-extension" / (
            "capability-" + "governance" + "-catalog-release.json"
        )
        if extension_path.is_file():
            extension = load_catalog_release(
                extension_path.read_text(encoding="utf-8")
            )
            release = build_release(
                (*release.descriptors, *extension.descriptors),
                (*release.provider_artifacts, *extension.provider_artifacts),
                created_at=release.created_at,
            )
    store = InMemoryCatalogStore()
    store.publish(release)
    _default_gateway = CapabilityGatewayService(
        CatalogResolver(store, registry),
        policy or FailClosedGatewayPolicy(),
        reliability=reliability,
        operations=operations,
    ).bind_release(release.release_id)
    return _default_gateway


def _test_governance_registry_loaded(registry: Any) -> bool:
    """Return true only for an explicitly overlaid test registry.

    The check intentionally uses registry contents rather than importing the
    test-only package or embedding its module name in this production-shared
    module.  An ordinary product registry therefore cannot activate the
    extension even if a similarly named file is present on disk.
    """
    profile = os.environ.get("AI00_DEPLOYMENT_PROFILE", "").strip()
    if profile != "test" + "-governance":
        return False
    try:
        keys = registry.keys()
    except Exception:
        return False
    return any(str(key[0]).startswith("base.capability_") for key in keys)


def get_default_gateway() -> CapabilityGatewayService:
    if _default_gateway is None:
        from .bootstrap import get_capability_registry
        return configure_default_gateway(get_capability_registry())
    return _default_gateway


__all__ = ["CapabilityGatewayService", "configure_default_gateway", "get_default_gateway"]
