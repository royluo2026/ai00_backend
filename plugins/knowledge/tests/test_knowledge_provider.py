from __future__ import annotations

import json
from pathlib import Path

from backend.capability_v2.schema_validation import validate_payload


ROOT = Path(__file__).resolve().parents[3]


def test_knowledge_provider_is_complete_against_frozen_review():
    from plugins.knowledge.knowledge_backend.capabilities import register_capabilities

    class Registry:
        def __init__(self): self.items = []
        def register(self, spec, handler, *, descriptor=None): self.items.append((spec, descriptor))

    review = json.loads((ROOT / "docs/governance/capability-coverage-review/knowledge.json").read_text(encoding="utf-8"))
    registry = Registry(); register_capabilities(registry)

    assert {
        descriptor.id for _, descriptor in registry.items
        if ".atomic." not in descriptor.id
    } == set(review["capabilities"])
    assert {descriptor.owner_domain for _, descriptor in registry.items} == {"knowledge"}


def test_knowledge_official_artifact_is_independent_plugin():
    document = json.loads((ROOT / "backend/capability_v2/official_domains.json").read_text(encoding="utf-8"))
    knowledge = next(item for item in document["domains"] if item["domain_id"] == "knowledge")
    assert knowledge["artifact"]["module"] == "knowledge_backend.capabilities"
    assert knowledge["artifact_path"] == "plugins/knowledge/knowledge_backend"


def test_reference_dataset_publish_is_a_worker_executable_closed_contract():
    from plugins.knowledge.knowledge_backend.capabilities import register_capabilities

    class Registry:
        def __init__(self):
            self.items = []

        def register(self, spec, handler, *, descriptor=None):
            self.items.append((spec, handler, descriptor))

    registry = Registry()
    register_capabilities(registry)
    registrations = {spec.id: (spec, handler, descriptor) for spec, handler, descriptor in registry.items}

    spec, _handler, descriptor = registrations["knowledge.reference_dataset.publish"]
    persisted_import_payload = {
        "dataset_gid": "dataset-parts",
        "expected_version": 7,
        "schema": {
            "fields": [{"name": "code", "source_field": "part_no"}],
        },
        "rows": [],
    }

    validate_payload(spec.input_schema, persisted_import_payload)
    assert descriptor.input_schema == spec.input_schema
    assert descriptor.lifecycle_status.value == "stable"
    assert descriptor.owner_domain == "knowledge"
    assert descriptor.exposure.worker is True
