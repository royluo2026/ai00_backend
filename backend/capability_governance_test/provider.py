"""Test-only Base registration for governance catalog descriptors."""
from __future__ import annotations

from typing import Any, Callable
from unittest.mock import patch

from backend.base import provider as base_provider
from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilityRisk, CapabilitySpec

from .contracts import ALL_IDS, ANALYZE_IDS, GOVERN_IDS, INPUT_SCHEMAS, OUTPUT_SCHEMAS, RELEASE_IDS, WRITE_IDS


_READ_PERMISSION = "system.capability.read"
_ANALYZE_PERMISSION = "system.capability.analyze"
_GOVERN_PERMISSION = "system.capability.govern"
_RELEASE_PERMISSION = "system.capability.release"


def _permissions(capability_id: str) -> tuple[str, ...]:
    if capability_id in RELEASE_IDS:
        return (_READ_PERMISSION, _ANALYZE_PERMISSION, _GOVERN_PERMISSION, _RELEASE_PERMISSION)
    if capability_id in GOVERN_IDS:
        return (_READ_PERMISSION, _ANALYZE_PERMISSION, _GOVERN_PERMISSION)
    if capability_id in ANALYZE_IDS:
        return (_READ_PERMISSION, _ANALYZE_PERMISSION)
    return (_READ_PERMISSION,)


def _handler(capability_id: str, service_port: Any) -> Callable[[dict[str, Any], object], dict[str, str]]:
    def invoke(payload: dict[str, Any], context: object) -> dict[str, str]:
        method = getattr(service_port, capability_id.replace(".", "_"), None) if service_port is not None else None
        if callable(method):
            result = method(payload, context)
            return {"capability_id": capability_id, "status": str(result["status"])}
        raise CapabilityBusinessError("provider_unavailable", "provider_unavailable", retryable=True)
    return invoke


def register_governance_capabilities(registry: Any, service_port: Any = None) -> None:
    """Register the extension only when explicitly requested by test bootstrap."""
    service = service_port
    with patch.dict(base_provider.INPUT_SCHEMAS, INPUT_SCHEMAS), patch.dict(
        base_provider.OUTPUT_SCHEMAS, OUTPUT_SCHEMAS,
    ):
        for capability_id in ALL_IDS:
            is_write = capability_id in WRITE_IDS
            base_provider.register_capability(registry, CapabilitySpec(
                owner="base",
                id=capability_id,
                version=1,
                description=f"Test-only governance operation {capability_id}.",
                use_when="The test-governance profile needs this governed capability contract.",
                do_not_use_when="The test-governance extension is not explicitly enabled.",
                risk=CapabilityRisk.WRITE if is_write else CapabilityRisk.READ,
                confirmation="admin" if is_write else "none",
                idempotent=True,
                permissions=_permissions(capability_id),
                input_schema=INPUT_SCHEMAS[capability_id],
                output_schema=OUTPUT_SCHEMAS[capability_id],
                tags=("governance", "test-only", "write" if is_write else "read"),
            ), _handler(capability_id, service))


__all__ = ["register_governance_capabilities"]
