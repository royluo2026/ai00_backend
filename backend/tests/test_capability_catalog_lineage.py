from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.capability_v2.catalog import build_release
from backend.capability_v2.contracts import (
    AutomationLevel,
    CapabilityDescriptorV2,
    ExposurePolicy,
    LifecycleStatus,
)


def _descriptor(capability_id: str, *, schema_hash: str = "a") -> CapabilityDescriptorV2:
    return CapabilityDescriptorV2(
        id=capability_id,
        major_version=1,
        owner_domain=capability_id.split(".", 1)[0],
        lifecycle_status=LifecycleStatus.STABLE,
        title=capability_id,
        description=f"Stable contract for {capability_id}.",
        use_when="The caller needs this exact outcome.",
        do_not_use_when="The caller needs another outcome.",
        exposure=ExposurePolicy(worker=True),
        automation_level=AutomationLevel.A1,
        authorization_policy=f"{capability_id}.invoke",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        output_schema={"type": "object", "properties": {}, "additionalProperties": False},
        schema_hash="sha256:" + schema_hash * 64,
    )


def _release(*descriptors: CapabilityDescriptorV2):
    return build_release(descriptors, created_at=datetime(2026, 8, 29, tzinfo=UTC))


def test_release_floor_accepts_same_or_newer_compatible_release_and_rejects_older_active_release():
    from backend.capability_v2.catalog_lineage import CatalogLineage

    target = _descriptor("knowledge.reference_dataset.publish")
    older = _release(target)
    newer = _release(target, _descriptor("knowledge.unrelated.read", schema_hash="b"))
    lineage = CatalogLineage.from_releases((older, newer))

    lineage.require_floor(
        minimum_release_id=older.release_id,
        active_release_id=older.release_id,
        capability_id=target.id,
        major_version=1,
        active_schema_hash=target.schema_hash,
    )
    lineage.require_floor(
        minimum_release_id=older.release_id,
        active_release_id=newer.release_id,
        capability_id=target.id,
        major_version=1,
        active_schema_hash=target.schema_hash,
    )
    with pytest.raises(ValueError, match="catalog_release_floor_not_met"):
        lineage.require_floor(
            minimum_release_id=newer.release_id,
            active_release_id=older.release_id,
            capability_id=target.id,
            major_version=1,
            active_schema_hash=target.schema_hash,
        )


def test_release_floor_rejects_a_breaking_target_contract_edge():
    from backend.capability_v2.catalog_lineage import CatalogLineage

    old_target = _descriptor("knowledge.reference_dataset.publish", schema_hash="a")
    changed_target = _descriptor("knowledge.reference_dataset.publish", schema_hash="c")
    older = _release(old_target)
    newer = _release(changed_target)
    lineage = CatalogLineage.from_releases((older, newer))

    with pytest.raises(ValueError, match="catalog_release_incompatible"):
        lineage.require_floor(
            minimum_release_id=older.release_id,
            active_release_id=newer.release_id,
            capability_id=changed_target.id,
            major_version=1,
            active_schema_hash=changed_target.schema_hash,
        )


def test_release_lineage_content_hash_detects_order_metadata_tampering():
    from backend.capability_v2.catalog_lineage import CatalogLineage

    release = _release(_descriptor("knowledge.reference_dataset.publish"))
    document = CatalogLineage.from_releases((release,)).model_dump(mode="json")
    document["entries"][0]["catalog_hash"] = "sha256:" + "f" * 64

    with pytest.raises(ValueError, match="catalog_lineage_hash_mismatch"):
        CatalogLineage.model_validate(document)


def test_catalog_lineage_append_preserves_order_and_compatibility_evidence():
    from backend.capability_v2.catalog_lineage import CatalogLineage

    first = _release(_descriptor("integration.mapping_target.search"))
    second = _release(
        _descriptor("integration.mapping_target.search"),
        _descriptor("knowledge.reference_dataset.publish"),
    )

    lineage = CatalogLineage.from_releases((first,)).append(first, second)

    assert [entry.sequence for entry in lineage.entries] == [1, 2]
    assert lineage.entries[-1].parent_release_id == first.release_id
    assert lineage.entries[-1].release_id == second.release_id
    assert lineage.entries[-1].compatible_with_parent is True


def test_catalog_builder_bootstraps_then_extends_authoritative_lineage():
    from backend.scripts.build_capability_catalog import next_lineage

    first = _release(_descriptor("integration.mapping_target.search"))
    second = _release(
        _descriptor("integration.mapping_target.search"),
        _descriptor("knowledge.reference_dataset.publish"),
    )

    bootstrapped = next_lineage(None, first, first)
    extended = next_lineage(bootstrapped, first, second)

    assert tuple(item.release_id for item in extended.entries) == (
        first.release_id, second.release_id,
    )
