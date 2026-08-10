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
)
from .policies import (
    FailClosedGatewayPolicy,
    GatewayPolicy,
    GatewayPolicyError,
)
from .projection import project_result


class CapabilityGatewayService:
    def __init__(self, resolver: CatalogResolver, policy: GatewayPolicy | None = None) -> None:
        self._resolver = resolver
        self._policy = policy or FailClosedGatewayPolicy()
        self._catalog_release: str | None = None

    @property
    def catalog_release(self) -> str:
        if self._catalog_release is None:
            raise RuntimeError("Gateway catalog release is not bound.")
        return self._catalog_release

    def bind_release(self, release_id: str) -> "CapabilityGatewayService":
        self._catalog_release = release_id
        return self

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

        try:
            self._policy.approve(descriptor, envelope, provider)
        except GatewayPolicyError as exc:
            return project_result(
                self._rejected(envelope, exc.code, exc.message),
                descriptor,
                envelope.identity,
                data_scopes=authorization.data_scopes if authorization is not None else (),
            )
        except Exception:
            return self._failed(envelope, "approval_failed", "Capability approval service failed.")

        context = self._legacy_context(envelope)
        try:
            value = provider.handler(dict(envelope.payload), context)
            if inspect.isawaitable(value):
                value = await value
            evidence = ()
            if isinstance(value, CapabilityOutput):
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
            return project_result(
                self._rejected(
                    envelope,
                    exc.code,
                    exc.message,
                    retryable=exc.retryable,
                    details=exc.details,
                ),
                descriptor,
                envelope.identity,
                data_scopes=authorization.data_scopes if authorization is not None else (),
            )
        except Exception:
            return self._failed(envelope, "provider_failed", "Capability provider failed.")

        result = CapabilityResultV2(
            ok=True,
            status=CapabilityStatus.COMPLETED,
            capability_id=envelope.capability_id,
            major_version=envelope.major_version,
            data=projected,
            evidence=evidence,
            correlation=CorrelationRef(request_id=envelope.request_id, trace_id=envelope.trace_id),
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
            plugin_id=(envelope.identity.consumer.consumer_id
                       if envelope.identity.consumer.type.value == "plugin" else None),
            plugin_version=envelope.identity.consumer.consumer_version,
        )

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
                              release_path: Path | None = None) -> CapabilityGatewayService:
    global _default_gateway
    path = release_path or Path(__file__).resolve().parents[2] / "docs" / "governance" / "capability-catalog-release.json"
    release = CatalogRelease.model_validate_json(path.read_text(encoding="utf-8"))
    store = InMemoryCatalogStore()
    store.publish(release)
    _default_gateway = CapabilityGatewayService(
        CatalogResolver(store, registry),
        policy or FailClosedGatewayPolicy(),
    ).bind_release(release.release_id)
    return _default_gateway


def get_default_gateway() -> CapabilityGatewayService:
    if _default_gateway is None:
        from backend.capabilities.registry_next import capability_registry
        return configure_default_gateway(capability_registry)
    return _default_gateway


__all__ = ["CapabilityGatewayService", "configure_default_gateway", "get_default_gateway"]
