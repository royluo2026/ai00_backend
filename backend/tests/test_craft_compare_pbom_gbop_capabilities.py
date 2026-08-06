from unittest.mock import patch

import pytest

from backend.capabilities.models_next import CapabilityContext
from backend.capabilities.registry_next import CapabilityRegistry
from plugins.craft.craft_backend.capabilities import register_capabilities
from plugins.craft.craft_backend.capabilities.gbop_read import (
    get_gbop_item_usage,
    repository as gbop_repository,
)
from plugins.craft.craft_backend.capabilities.pbom_read import search_pbom_parts


def _registry() -> CapabilityRegistry:
    registry = CapabilityRegistry()
    register_capabilities(registry)
    return registry


def test_approved_compare_pbom_gbop_ids_are_registered():
    ids = {spec.id for spec in _registry().list()}
    assert {
        "craft.bop.version.compare",
        "craft.pbom.snapshot.get",
        "craft.pbom.snapshot.compare",
        "craft.pbom.part.search",
        "craft.gbop.item.search",
        "craft.gbop.item.usage.get",
        "craft.gbop.item.knowledge.list",
    } <= ids


def test_no_pbom_gbop_match_capability_is_registered():
    ids = {spec.id for spec in _registry().list()}
    assert not any("gbop.match" in value or "pbom.gbop" in value for value in ids)


def test_pbom_part_search_requires_snapshot():
    with pytest.raises(ValueError, match="snapshot_gid"):
        search_pbom_parts(
            {"query": "bolt"},
            CapabilityContext(user_gid="u1"),
        )


def test_gbop_usage_returns_only_explicit_provenance_statuses():
    with patch.object(gbop_repository, "resolve_active_release", return_value={"gid": "g-active"}), patch.object(
        gbop_repository,
        "get_item",
        return_value={"gid": "item-1", "version_gid": "g-active", "meta": {}},
    ), patch.object(
        gbop_repository,
        "list_usage",
        return_value=[
            {"bop_version_gid": "b1", "entry_gid": "e1", "is_inherited": 1},
            {"bop_version_gid": "b2", "entry_gid": "e2", "provenance_status": "unknown"},
        ],
    ):
        result = get_gbop_item_usage(
            {"item_gid": "item-1"},
            CapabilityContext(user_gid="u1"),
        )

    assert result.data["active_release_gid"] == "g-active"
    assert {item["provenance_status"] for item in result.data["items"]} <= {
        "exact",
        "modified",
        "outdated",
        "inherited",
        "broken",
    }
