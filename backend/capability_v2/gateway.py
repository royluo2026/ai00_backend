"""The sole governed execution pipeline for Capability V2 consumers."""
from __future__ import annotations

import inspect
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
from .projection import project_result
from .reliability import (
    InvocationLease, ReliabilityCoordinator, ReliabilityError, TransactionalCapabilityOutput,
)
from .reliability import IssuedApproval


class CapabilityGatewayService:
    def __init__(self, resolver: CatalogResolver, policy: GatewayPolicy | None = None,
                 *, reliability: ReliabilityCoordinator | None = None) -> None:
        self._resolver = resolver
        self._policy = policy or FailClosedGatewayPolicy()
        self._reliability = reliability
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
        concurrency_error = self._concurrency_error(descriptor, envelope)
        if concurrency_error:
            return self._rejected(
                envelope, concurrency_error, "Expected resource version is invalid."
            )

        is_write = descriptor.side_effect_level is not SideEffectLevel.READ
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

        context = self._legacy_context(envelope)
        transaction = None
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
            projected = self._policy.project(descriptor, envelope.identity, value)
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
            result = self._failed(envelope, "provider_failed", "Capability provider failed.")
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
        if lease is not None:
            operation_status = (
                OperationStatus.COMPLETED if result.ok else OperationStatus.FAILED
            )
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
        return project_result(
            result,
            descriptor,
            envelope.identity,
            data_scopes=authorization.data_scopes if authorization is not None else (),
        )

    @staticmethod
    def _legacy_context(envelope: InvocationEnvelope) -> CapabilityContext:
        actor = envelope.identity.actor
        return CapabilityContext(
            user_gid=actor.user_id or actor.service_id or "",
            team_gid=envelope.identity.tenant.tenant_id,
            source=envelope.identity.consumer.type.value,
            request_id=envelope.request_id,
            confirmation_token=envelope.approval_reference,
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
        if not expected:
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
    ).bind_release(release.release_id)
    return _default_gateway


def get_default_gateway() -> CapabilityGatewayService:
    if _default_gateway is None:
        from backend.capabilities.registry_next import capability_registry
        return configure_default_gateway(capability_registry)
    return _default_gateway


__all__ = ["CapabilityGatewayService", "configure_default_gateway", "get_default_gateway"]
