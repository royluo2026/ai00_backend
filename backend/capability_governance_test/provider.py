"""Test-only Base registration for governance catalog descriptors."""
from __future__ import annotations

from typing import Any, Callable
from unittest.mock import patch

from backend.base import provider as base_provider
from backend.capability_v2.provider_contracts import CapabilityRisk, CapabilitySpec

from .contracts import ALL_IDS, INPUT_SCHEMAS, OUTPUT_SCHEMAS, WRITE_IDS


def _handler(capability_id: str, service_port: Any) -> Callable[[dict[str, Any], object], dict[str, str]]:
    def invoke(payload: dict[str, Any], context: object) -> dict[str, str]:
        method = getattr(service_port, capability_id.replace(".", "_"), None) if service_port else None
        if callable(method):
            return method(payload, context)
        return {"capability_id": capability_id, "status": "accepted" if capability_id in WRITE_IDS else "completed"}
    return invoke


def register_governance_capabilities(registry: Any, service_port: Any = None) -> None:
    """Register the extension only when explicitly requested by test bootstrap."""
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
                permissions=("system.tech_config",),
                input_schema=INPUT_SCHEMAS[capability_id],
                output_schema=OUTPUT_SCHEMAS[capability_id],
                tags=("governance", "test-only", "write" if is_write else "read"),
            ), _handler(capability_id, service_port))


__all__ = ["register_governance_capabilities"]
