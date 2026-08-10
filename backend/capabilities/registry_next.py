"""Capability registry for the next migration slice."""
from __future__ import annotations
import inspect
from dataclasses import dataclass
from typing import Any
from .models_next import CapabilityContext, CapabilityHandler, CapabilityOutput, CapabilityResult, CapabilitySpec
from .validation_next import validate_payload
from backend.plugin_platform.metrics import record_usage
from .confirmation_next import confirmation_manager
from .audit_next import audit_sink

class CapabilityPermissionError(PermissionError):
    pass

class CapabilityConfirmationError(PermissionError):
    pass

@dataclass(frozen=True)
class RegisteredCapability:
    spec: CapabilitySpec
    handler: CapabilityHandler
    descriptor: Any | None = None

class CapabilityRegistry:
    def __init__(self) -> None: self._items: dict[tuple[str, int], RegisteredCapability] = {}
    def register(self, spec: CapabilitySpec, handler: CapabilityHandler, *, descriptor: Any | None = None) -> None:
        key = (spec.id, spec.version)
        if key in self._items: raise ValueError(f"Capability already registered: {spec.id}@{spec.version}")
        if descriptor is not None and (
            getattr(descriptor, "id", None) != spec.id
            or getattr(descriptor, "major_version", None) != spec.version
            or getattr(descriptor, "owner_domain", None) != spec.owner
        ):
            raise ValueError("native_descriptor_identity_mismatch")
        self._items[key] = RegisteredCapability(spec, handler, descriptor)
    def get(self, capability_id: str, version: int | None = None) -> RegisteredCapability:
        if version is not None:
            item = self._items.get((capability_id, version))
            if item is None: raise KeyError(f"Unknown capability: {capability_id}@{version}")
            return item
        candidates = [item for (cid, _), item in self._items.items() if cid == capability_id]
        if not candidates: raise KeyError(f"Unknown capability: {capability_id}")
        return max(candidates, key=lambda item: item.spec.version)
    def list(self, *, execution: str | None = None, tag: str | None = None, plugin_callable: bool | None = None) -> list[CapabilitySpec]:
        result = [item.spec for item in self._items.values()]
        if execution: result = [spec for spec in result if spec.execution.value == execution]
        if tag: result = [spec for spec in result if tag in spec.tags]
        if plugin_callable is not None: result = [spec for spec in result if spec.plugin_callable is plugin_callable]
        return sorted(result, key=lambda spec: (spec.id, spec.version))
    def snapshot(self) -> tuple[RegisteredCapability, ...]:
        """Return an exact, deterministically ordered provider registration snapshot."""
        return tuple(self._items[key] for key in sorted(self._items))
    async def invoke(self, capability_id: str, payload: dict[str, Any], context: CapabilityContext, *, version: int | None = None) -> CapabilityResult:
        item = self.get(capability_id, version)
        validate_payload(dict(item.spec.input_schema), payload)
        if item.spec.confirmation != "none":
            if not confirmation_manager.consume(context.confirmation_token or "", item.spec.id, item.spec.version, context.user_gid, payload):
                audit_sink.record(capability_id=item.spec.id, version=item.spec.version, context=context, payload=payload, status="confirmation_rejected", error="invalid_or_expired_confirmation")
                raise CapabilityConfirmationError(f"Confirmation required for {item.spec.id}")
        missing = sorted(set(item.spec.permissions) - set(context.permissions))
        if missing:
            audit_sink.record(capability_id=item.spec.id, version=item.spec.version, context=context, payload=payload, status="permission_denied", error=", ".join(missing))
            raise CapabilityPermissionError(f"Missing permissions for {item.spec.id}: {', '.join(missing)}")
        try:
            value = item.handler(payload, context)
            if inspect.isawaitable(value): value = await value
            evidence = ()
            if isinstance(value, CapabilityOutput):
                evidence = value.evidence
                value = value.data
            validate_payload(dict(item.spec.output_schema), value, label="output")
        except Exception as exc:
            audit_sink.record(capability_id=item.spec.id, version=item.spec.version, context=context, payload=payload, status="failed", error=str(exc))
            record_usage(context, item.spec.id, False)
            raise
        audit_sink.record(capability_id=item.spec.id, version=item.spec.version, context=context, payload=payload, status="succeeded")
        record_usage(context, item.spec.id, True)
        audit = {"source": context.source, "user_gid": context.user_gid, "request_id": context.request_id}
        if getattr(context, "plugin_id", None):
            audit["plugin_id"] = context.plugin_id
            audit["plugin_version"] = getattr(context, "plugin_version", None)
        return CapabilityResult(capability_id=item.spec.id, version=item.spec.version, data=value, evidence=evidence, audit=audit)

capability_registry = CapabilityRegistry()
from backend.base.provider import register_capability as register_base_capability
register_base_capability(capability_registry, CapabilitySpec(id="system.echo", version=1, owner="base", description="Return the supplied JSON payload; used to verify adapters.", plugin_callable=True, input_schema={"type": "object"}, output_schema={"type": "object"}, tags=("system", "diagnostic")), lambda payload, _context: payload)
from .knowledge_next import register_knowledge_capabilities
register_knowledge_capabilities(capability_registry)

from .knowledge_documents_next import register_knowledge_document_capabilities
register_knowledge_document_capabilities(capability_registry)

from .knowledge_context_next import register_knowledge_context_capability
register_knowledge_context_capability(capability_registry)

from .ontology_concepts_next import register_ontology_concept_capabilities
register_ontology_concept_capabilities(capability_registry)

from .ontology_proposals_next import register_ontology_proposal_capabilities
register_ontology_proposal_capabilities(capability_registry)

from .ontology_releases_next import register_ontology_release_capabilities
register_ontology_release_capabilities(capability_registry)

from .system_shared_next import register_system_shared_capabilities
register_system_shared_capabilities(capability_registry)

from .knowledge_migration_next import register_knowledge_migration_capabilities
register_knowledge_migration_capabilities(capability_registry)

from .proposals_next import register_proposal_capability
register_proposal_capability(capability_registry)

from .review_next import register_review_capability
register_review_capability(capability_registry)

from .proposal_query_next import register_proposal_query_capabilities
register_proposal_query_capabilities(capability_registry)

from .outbox_next import register_outbox_capability
register_outbox_capability(capability_registry)

from .outbox_retry_next import register_retry_capability
register_retry_capability(capability_registry)

from backend.base.operations import register_worker_capability
register_worker_capability(capability_registry)

from .plugin_marketplace_next import register_plugin_marketplace_capabilities
register_plugin_marketplace_capabilities(capability_registry)

from backend.plugin_platform.storage import register_plugin_storage_capabilities
register_plugin_storage_capabilities(capability_registry)
