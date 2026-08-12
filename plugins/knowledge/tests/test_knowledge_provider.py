from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_knowledge_provider_is_complete_against_frozen_review():
    from plugins.knowledge.knowledge_backend.capabilities import register_capabilities

    class Registry:
        def __init__(self): self.items = []
        def register(self, spec, handler, *, descriptor=None): self.items.append((spec, descriptor))

    review = json.loads((ROOT / "docs/governance/capability-coverage-review/knowledge.json").read_text(encoding="utf-8"))
    registry = Registry(); register_capabilities(registry)

    assert {descriptor.id for _, descriptor in registry.items} == set(review["capabilities"]) | {
        "knowledge.reference_data.read",
        "knowledge.reference_data.change.apply",
    }
    assert {descriptor.owner_domain for _, descriptor in registry.items} == {"knowledge"}


def test_knowledge_official_artifact_is_independent_plugin():
    document = json.loads((ROOT / "backend/capability_v2/official_domains.json").read_text(encoding="utf-8"))
    knowledge = next(item for item in document["domains"] if item["domain_id"] == "knowledge")
    assert knowledge["artifact"]["module"] == "knowledge_backend.capabilities"
    assert knowledge["artifact_path"] == "plugins/knowledge/knowledge_backend"
