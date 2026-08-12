from __future__ import annotations

import importlib
from pathlib import Path

from backend.capability_v2.bootstrap import build_capability_registry


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
OFFICIAL_DOMAINS = REPOSITORY_ROOT / "backend/capability_v2/official_domains.json"


def test_registry_module_is_empty_until_bootstrap() -> None:
    module = importlib.reload(importlib.import_module("backend.capabilities.registry_next"))

    assert module.CapabilityRegistry().snapshot() == ()
    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "register_knowledge" not in source
    assert "register_ontology" not in source
    assert "register_plugin_marketplace" not in source


def test_bootstrap_builds_one_complete_registry() -> None:
    registry = build_capability_registry(REPOSITORY_ROOT, OFFICIAL_DOMAINS)

    keys = registry.keys()
    assert len(keys) == len(set(keys))
    assert ("system.search", 1) in keys
    assert ("knowledge.document.get", 1) in keys
    assert ("ontology.release.get", 1) in keys
    assert ("system.echo", 1) not in keys
