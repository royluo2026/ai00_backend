"""Validated legacy schema-name conversion for Craft-owned entity tables."""
from __future__ import annotations

import re

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
_SCHEMA_PREFIX = {
    "bop": "workmanship_bop_",
    "factory": "workmanship_factory_",
    "proj": "workmanship_proj_",
    "template": "workmanship_tpl_",
    "work": "workmanship_work_",
}
_ALLOWED_PREFIXES = tuple(_SCHEMA_PREFIX.values())
_SPECIAL = {
    "template.gbop": "workmanship_tpl_gbop_entries",
    "proj.task_templates": "workmanship_work_task_templates",
    "proj.task_template_items": "workmanship_work_task_template_items",
    "knowledge.craft_rules": "workmanship_know_craft_rules",
}


def craft_entity_table_name(value: str) -> str:
    """Return a safe physical table name and reject non-Craft ownership."""
    raw = str(value or "").strip().lower()
    if raw in _SPECIAL:
        return _SPECIAL[raw]
    if raw.startswith(_ALLOWED_PREFIXES) and _IDENTIFIER.fullmatch(raw):
        return raw
    if "." not in raw:
        raise ValueError(f"unrecognized Craft entity table: {value}")
    schema, table = raw.split(".", 1)
    if schema not in _SCHEMA_PREFIX or not _IDENTIFIER.fullmatch(table):
        raise ValueError(f"non-Craft or invalid entity table: {value}")
    return _SCHEMA_PREFIX[schema] + table


def is_craft_table(value: str) -> bool:
    try:
        craft_entity_table_name(value)
        return True
    except ValueError:
        return False
