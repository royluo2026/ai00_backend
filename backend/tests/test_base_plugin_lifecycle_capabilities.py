from __future__ import annotations

import pytest

from backend.capabilities.registry_next import CapabilityRegistry
from backend.capabilities.validation_next import validate_payload


def test_plugin_lifecycle_capabilities_are_closed_confirmed_and_transactional():
    """Removing closed schemas, confirmation, or transaction metadata must fail this test."""
    from backend.base.web_atomic import register_atomic_web_capabilities

    registry = CapabilityRegistry()
    register_atomic_web_capabilities(registry)
    payloads = {
        "base.plugin.installation.request.create": {
            "plugin_id": "plugin.example", "release_version": "1.2.3", "release_sha256": "sha256:" + "b" * 64,
            "requested_grants": ["project.read"], "idempotency_key": "idem-plugin-1",
        },
        "base.plugin.installation.transition.uninstall": {
            "plugin_id": "plugin.example", "expected_revision": 3, "retain_tenant_data": True,
            "idempotency_key": "idem-plugin-2",
        },
    }
    for capability_id, payload in payloads.items():
        item = registry.get(capability_id)
        validate_payload(dict(item.spec.input_schema), payload)
        with pytest.raises(ValueError, match="unknown field"):
            validate_payload(dict(item.spec.input_schema), {**payload, "url": "https://evil.example"})
        assert item.descriptor.confirmation_policy == "user"
        assert item.descriptor.consistency_policy == "strong"
        assert item.descriptor.transaction_policy["mode"] == "single_transaction"
        assert getattr(item.handler, "__capability_transactional__", False) is True
