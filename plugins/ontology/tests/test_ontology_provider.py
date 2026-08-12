from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_ontology_provider_is_complete_against_frozen_review():
    from plugins.ontology.ontology_backend.capabilities import register_capabilities

    class Registry:
        def __init__(self): self.items = []
        def register(self, spec, handler, *, descriptor=None): self.items.append(descriptor)

    review = json.loads((ROOT / "docs/governance/capability-coverage-review/ontology.json").read_text(encoding="utf-8"))
    registry = Registry(); register_capabilities(registry)
    assert {item.id for item in registry.items} == set(review["capabilities"])
    assert {item.owner_domain for item in registry.items} == {"ontology"}


def test_ontology_official_artifact_is_independent_plugin():
    document = json.loads((ROOT / "backend/capability_v2/official_domains.json").read_text(encoding="utf-8"))
    ontology = next(item for item in document["domains"] if item["domain_id"] == "ontology")
    assert ontology["artifact"]["module"] == "ontology_backend.capabilities"
    assert ontology["artifact_path"] == "plugins/ontology/ontology_backend"

