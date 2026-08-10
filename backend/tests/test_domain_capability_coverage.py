"""Registry-driven acceptance gates for independently maintained domains."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
DOMAINS = {
    "Base Platform": "base",
    "Project Management": "project_management",
    "Knowledge": "knowledge",
    "Craft": "craft",
}
MIGRATED_DOMAINS = {
    "Project Management": "project_management",
    "Knowledge": "knowledge",
    "Craft": "craft",
}


def _documents() -> tuple[list[dict], dict[str, dict]]:
    registry_document = json.loads(
        (ROOT / "docs/governance/user-function-registry.json").read_text(encoding="utf-8")
    )
    catalog_document = json.loads(
        (ROOT / "docs/governance/capability-catalog-release.json").read_text(encoding="utf-8")
    )
    records = list(registry_document["functions"].values())
    descriptors = {item["id"]: item for item in catalog_document["descriptors"]}
    return records, descriptors


def _stable_targets(domain: str, records: list[dict]) -> set[str]:
    return {
        row["target_capability"]
        for row in records
        if row["domain"] == domain
        and row["stability"] == "stable"
        and row.get("target_capability")
    }


@pytest.mark.parametrize("domain", DOMAINS)
def test_stable_domain_functions_have_catalog_descriptors(domain: str):
    records, descriptors = _documents()
    missing = _stable_targets(domain, records) - set(descriptors)
    assert missing == set()


@pytest.mark.parametrize("domain,owner", MIGRATED_DOMAINS.items())
def test_stable_domain_capabilities_have_the_governed_owner(domain: str, owner: str):
    records, descriptors = _documents()
    mismatches = {
        capability_id: descriptors[capability_id]["owner_domain"]
        for capability_id in _stable_targets(domain, records)
        if capability_id in descriptors and descriptors[capability_id]["owner_domain"] != owner
    }
    assert mismatches == {}


@pytest.mark.parametrize("domain", MIGRATED_DOMAINS)
def test_stable_domain_capabilities_publish_nonempty_output_contracts(domain: str):
    records, descriptors = _documents()
    incomplete = {
        capability_id
        for capability_id in _stable_targets(domain, records)
        if capability_id in descriptors
        and not (descriptors[capability_id]["output_schema"].get("properties") or {})
    }
    assert incomplete == set()


@pytest.mark.parametrize("domain", MIGRATED_DOMAINS)
def test_stable_domain_capabilities_are_available_to_plugins_and_agents(domain: str):
    records, descriptors = _documents()
    unavailable = {
        capability_id
        for capability_id in _stable_targets(domain, records)
        if capability_id in descriptors
        and descriptors[capability_id]["lifecycle_status"] != "deprecated"
        and not (
            descriptors[capability_id]["exposure"].get("plugin")
            and descriptors[capability_id]["exposure"].get("agent")
        )
    }
    assert unavailable == set()
