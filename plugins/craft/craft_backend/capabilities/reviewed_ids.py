"""Immutable IDs for the final approved Craft coverage slice."""

READ_CAPABILITIES = frozenset(
    {
        "craft.canvas.read",
        "craft.ebom.read",
        "craft.gbop.read",
        "craft.manufacturing_resource.read",
        "craft.rule.read",
    }
)
WRITE_CAPABILITIES = frozenset(
    {
        "craft.canvas.change.apply",
        "craft.data_exchange.export",
        "craft.ebom.change.apply",
        "craft.gbop.change.apply",
        "craft.manufacturing_resource.change.apply",
        "craft.rule.change.apply",
    }
)
CRAFT_REVIEWED_CAPABILITIES = READ_CAPABILITIES | WRITE_CAPABILITIES

__all__ = ["CRAFT_REVIEWED_CAPABILITIES", "READ_CAPABILITIES", "WRITE_CAPABILITIES"]
