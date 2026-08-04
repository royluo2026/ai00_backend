"""Public rule evaluation surface consumed by official domains."""

from plugins.craft.craft_backend.rule_engine.checker import check_entry_rules

__all__ = ["check_entry_rules"]
