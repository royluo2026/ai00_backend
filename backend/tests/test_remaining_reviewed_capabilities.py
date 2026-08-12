"""Release contracts for the final approved Craft and Local Runtime candidates."""
from __future__ import annotations

from backend.tests.capability_completion_support import registered_descriptor_ids


CRAFT_REVIEWED_IDS = frozenset(
    {
        "craft.canvas.change.apply",
        "craft.canvas.read",
        "craft.data_exchange.export",
        "craft.ebom.change.apply",
        "craft.ebom.read",
        "craft.gbop.change.apply",
        "craft.gbop.read",
        "craft.manufacturing_resource.change.apply",
        "craft.manufacturing_resource.read",
        "craft.rule.change.apply",
        "craft.rule.read",
    }
)
LOCAL_RUNTIME_REVIEWED_IDS = frozenset(
    {
        "local.device.change.apply",
        "local.device.read",
    }
)


def test_craft_provider_registers_every_final_approved_candidate() -> None:
    actual = registered_descriptor_ids(
        "plugins.craft.craft_backend.capabilities"
    )

    assert CRAFT_REVIEWED_IDS <= actual


def test_local_runtime_provider_registers_every_final_approved_candidate() -> None:
    actual = registered_descriptor_ids(
        "plugins.device.device_backend.capabilities"
    )

    assert LOCAL_RUNTIME_REVIEWED_IDS <= actual
