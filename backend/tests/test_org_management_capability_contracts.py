from __future__ import annotations

from backend.capabilities.registry_next import CapabilityRegistry
from backend.base.official_provider import register_capabilities as register_base
from backend.capability_v2.business_definition import is_generated_business_effect
from plugins.craft.craft_backend.capabilities import register_capabilities as register_craft
from plugins.project_management.project_management_backend.capabilities import (
    register_capabilities as register_project,
)


NEW_CAPABILITIES = {
    ("base.identity.active_principal.get", 1),
    ("base.project_manager.read", 1),
    ("base.project_manager.replace", 1),
    ("base.project_responsibility.projection.apply", 1),
    ("base.project_responsibility.projection.get", 1),
    ("base.bop_edit.authorization.check", 1),
    ("project.project.validation.get", 1),
    ("project.org_management.read", 1),
    ("project.org_management.change.apply", 1),
    ("craft.bop.active_line.search", 1),
    ("craft.bop.active_line.validate", 1),
}


def _registry():
    registry = CapabilityRegistry()
    register_base(registry)
    register_craft(registry)
    register_project(registry)
    return registry


def test_org_management_capabilities_are_registered_with_closed_governed_contracts():
    registry = _registry()

    assert NEW_CAPABILITIES <= set(registry.keys())
    for capability_id, version in NEW_CAPABILITIES:
        item = registry.get(capability_id, version)
        assert item.descriptor is not None
        assert item.descriptor.domain_errors_complete is True
        assert not is_generated_business_effect(
            item.descriptor.business_effect, item.spec.description
        )
        assert item.spec.input_schema.get("additionalProperties") is False
        assert item.spec.output_schema.get("additionalProperties") is False


def test_project_org_management_handlers_are_owned_by_the_capability_provider_boundary():
    registry = _registry()

    for capability_id in (
        "project.project.validation.get",
        "project.org_management.read",
        "project.org_management.change.apply",
    ):
        assert registry.get(capability_id, 1).handler.__module__.endswith(
            ".capabilities.org_management"
        )


def test_permission_changing_entrypoints_have_exact_confirmation_and_exposure():
    registry = _registry()

    for capability_id in (
        "base.project_manager.replace",
        "project.org_management.change.apply",
    ):
        item = registry.get(capability_id, 1)
        assert item.spec.confirmation == "user"
        assert item.descriptor.idempotency_policy == "required"

    projection = registry.get("base.project_responsibility.projection.apply", 1)
    assert projection.spec.confirmation == "none"
    assert projection.descriptor.exposure.worker is True
    assert projection.descriptor.exposure.web is False
    assert projection.descriptor.exposure.agent is False

    authorization = registry.get("base.bop_edit.authorization.check", 1)
    assert authorization.descriptor.exposure.local_runtime is True
    assert authorization.descriptor.exposure.web is False
    assert authorization.descriptor.exposure.agent is False

    validator = registry.get("project.project.validation.get", 1)
    assert validator.descriptor.exposure.local_runtime is True
    assert validator.descriptor.exposure.web is False
