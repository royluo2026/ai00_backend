from __future__ import annotations

import json
from pathlib import Path

from plugins.factory.factory_backend.domain.models import PhysicalStructure


ROOT = Path(__file__).resolve().parents[3]


def test_factory_has_one_official_provider():
    document = json.loads(
        (ROOT / "backend/capability_v2/official_domains.json").read_text(encoding="utf-8")
    )
    factory = next(item for item in document["domains"] if item["domain_id"] == "factory")

    assert factory["artifact"]["module"] == "factory_backend.capabilities"
    assert factory["database"]["database_name"] == "ai00_factory"


def test_factory_model_excludes_bop_plan_nodes():
    assert "line_process" not in PhysicalStructure.model_fields
    assert "station_process" not in PhysicalStructure.model_fields


def test_factory_provider_registers_only_factory_owned_stable_descriptors():
    from plugins.factory.factory_backend.capabilities import register_capabilities

    class Registry:
        def __init__(self):
            self.items = []

        def register(self, spec, handler, *, descriptor=None):
            self.items.append((spec, handler, descriptor))

    registry = Registry()
    register_capabilities(registry)

    assert registry.items
    assert {descriptor.owner_domain for _, _, descriptor in registry.items} == {"factory"}
    assert all(descriptor.lifecycle_status == "stable" for _, _, descriptor in registry.items)

