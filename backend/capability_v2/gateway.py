"""The sole governed execution pipeline for Capability V2 consumers."""
from __future__ import annotations

import inspect
import asyncio
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

from backend.capabilities.models_next import CapabilityBusinessError, CapabilityContext, CapabilityOutput
from backend.capabilities.validation_next import validate_payload

from .catalog import CatalogRelease, CatalogResolutionError, CatalogResolver
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


class CapabilityGatewayService:
    def __init__(self, resolver: CatalogResolver, policy: GatewayPolicy | None = None,
                 *, reliability: ReliabilityCoordinator | None = None,
                 operations: OperationService | None = None,
                 admission: ResourceAdmissionController | None = None,
                 metrics: InMemoryCapabilityMetrics | None = None,
                 admission_timeout_seconds: float = 0.25) -> None:
        self._resolver = resolver
        self._policy = policy or FailClosedGatewayPolicy()
        self._reliability = reliability
        self._operations = operations
        self._admission = admission or ResourceAdmissionController(MemoryPressureSampler())
        self._metrics = metrics or InMemoryCapabilityMetrics()
        self._admission_timeout_seconds = max(0.0, admission_timeout_seconds)
        self._catalog_release: str | None = None

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

    async def request_approval(self, envelope: InvocationEnvelope) -> IssuedApproval:
        try:
            descriptor = self._resolver.descriptor(
                envelope.catalog_release, envelope.capability_id, envelope.major_version
            )
            provider = self._resolver.resolve(
                envelope.catalog_release, envelope.capability_id, envelope.major_version
            )
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
            descriptor = self._resolver.descriptor(
                envelope.catalog_release, envelope.capability_id, envelope.major_version
            )
            provider = self._resolver.resolve(
                envelope.catalog_release, envelope.capability_id, envelope.major_version
            )
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
            envelope, operation_id=(async_operation.operation_id if async_operation else None)
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
        try:
            try:
                value = provider.handler(dict(envelope.payload), context)
                if inspect.isawaitable(value):
                    value = await value
            except LookupError as exc:
                raise CapabilityBusinessError(
                    "resource_not_found", "The requested resource was not found."
                ) from exc
            except (TypeError, ValueError) as exc:
                raise CapabilityBusinessError(
                    "invalid_input", "The provider rejected the supplied input."
                ) from exc
            evidence = ()
            if isinstance(value, TransactionalCapabilityOutput):
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
            validate_payload(dict(descriptor.output_schema), value, label="output")
            output_bytes = self._json_size(value)
            if output_bytes > descriptor.execution_budget.max_output_bytes:
                raise CapabilityBusinessError(
                    "capability_output_limit_exceeded",
                    "Capability provider exceeded its declared output byte limit.",
                )
            projected = self._policy.project(descriptor, envelope.identity, value)
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
            if admission_lease is not None:
                await admission_lease.release()
            if cancelled:
                self._record_metric(
                    descriptor, envelope, started, before, output_bytes, None, capability_key,
                    cancelled=True,
                )
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
                self._reliability.complete(lease, result, transaction=transaction)
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
        self._record_metric(
            descriptor, envelope, started, before, output_bytes, projected_result, capability_key,
        )
        return projected_result

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

    @staticmethod
    def _legacy_context(envelope: InvocationEnvelope, *, operation_id: str | None = None) -> CapabilityContext:
        actor = envelope.identity.actor
        return CapabilityContext(
            user_gid=actor.user_id or actor.service_id or "",
            team_gid=envelope.identity.tenant.tenant_id,
            active_roles=envelope.identity.tenant.active_roles,
            source=envelope.identity.consumer.type.value,
            request_id=envelope.request_id,
            confirmation_token=envelope.approval_reference,
            operation_id=operation_id,
            agent_run_id=envelope.identity.consumer.agent_run_id,
            # Plugin storage uses a server-derived consumer namespace. Agents receive
            # their own delegated consumer namespace; they cannot select another
            # plugin or agent namespace through request payload.
            plugin_id=(envelope.identity.consumer.consumer_id
                       if envelope.identity.consumer.type.value in {"plugin", "agent"} else None),
            plugin_version=envelope.identity.consumer.consumer_version,
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
    release = CatalogRelease.model_validate_json(path.read_text(encoding="utf-8"))
    store = InMemoryCatalogStore()
    store.publish(release)
    _default_gateway = CapabilityGatewayService(
        CatalogResolver(store, registry),
        policy or FailClosedGatewayPolicy(),
        reliability=reliability,
        operations=operations,
    ).bind_release(release.release_id)
    return _default_gateway


def get_default_gateway() -> CapabilityGatewayService:
    if _default_gateway is None:
        from .bootstrap import get_capability_registry
        return configure_default_gateway(get_capability_registry())
    return _default_gateway


__all__ = ["CapabilityGatewayService", "configure_default_gateway", "get_default_gateway"]
