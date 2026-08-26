from __future__ import annotations

from collections import Counter
from pathlib import Path

from backend.capability_v2.existing_capability_migrations import (
    audit_existing_capability_migrations,
    load_existing_capability_migrations,
)


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs/governance/existing-capability-web-migrations.json"


def test_manifest_accounts_for_all_53_groups_and_80_occurrences() -> None:
    manifest = load_existing_capability_migrations(MANIFEST)

    assert len(manifest.groups) == 53
    assert sum(group.occurrence_count for group in manifest.groups) == 80
    assert Counter(group.decision for group in manifest.groups) == {
        "migrate": 12,
        "reclassify": 41,
    }
    assert sum(
        group.occurrence_count for group in manifest.groups if group.decision == "migrate"
    ) == 18


def test_manifest_targets_are_stable_owned_and_decisions_have_evidence() -> None:
    manifest = load_existing_capability_migrations(MANIFEST)

    assert audit_existing_capability_migrations(ROOT, manifest) == ()
    assert all(group.request_transform and group.response_transform for group in manifest.groups)
    assert all(group.transport_evidence for group in manifest.groups)
    assert all(
        group.equivalence_evidence if group.decision == "migrate" else group.reclassification
        for group in manifest.groups
    )


def test_migrated_groups_are_only_the_provider_equivalent_families() -> None:
    manifest = load_existing_capability_migrations(MANIFEST)
    migrated = {(group.method, group.normalized_route) for group in manifest.groups if group.decision == "migrate"}

    assert migrated == {
        ("DELETE", "/api/knowledges/{dynamic}"),
        ("GET", "/api/knowledge/entries"),
        ("GET", "/api/knowledges/{dynamic}"),
        ("PATCH", "/api/knowledges/{dynamic}"),
        ("POST", "/api/knowledges"),
        ("PUT", "/api/knowledge/entries"),
        ("PUT", "/api/knowledges/{dynamic}"),
        ("GET", "/api/tasks/{dynamic}/entries"),
        ("PUT", "/api/tasks/{dynamic}/entries"),
        ("PUT", "/api/tasks"),
        ("PUT", "/api/issues"),
        ("PUT", "/api/rules/{dynamic}"),
    }
