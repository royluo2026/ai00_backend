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

# These final-wave IDs have a registration shell but no bound Craft outcome
# provider. Keep their identity for migration discovery, but do not publish
# them as invocable stable capabilities.
DEPRECATED_REVIEWED_CAPABILITIES = CRAFT_REVIEWED_CAPABILITIES - {
    "craft.canvas.read", "craft.canvas.change.apply", "craft.data_exchange.export", "craft.ebom.change.apply",
}

__all__ = [
    "CRAFT_REVIEWED_CAPABILITIES", "DEPRECATED_REVIEWED_CAPABILITIES",
    "READ_CAPABILITIES", "WRITE_CAPABILITIES",
]
