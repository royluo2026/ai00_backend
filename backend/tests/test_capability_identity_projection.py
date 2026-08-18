from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from backend.capability_governance_test.fingerprint import canonical_fingerprint
from backend.capability_governance_test.identity_projection import project_snapshot
from backend.capability_governance_test.models import (
    CapabilityBinding,
    ImplementationNode,
    ImplementationRelation,
    ScannedCapability,
    SnapshotDocument,
)
from backend.capability_governance_test.store import MemoryGovernanceStore


def snapshot(capability_id: str, major_version: int) -> SnapshotDocument:
    capability = ScannedCapability(
        capability_id=capability_id,
        major_version=major_version,
        owner_domain="craft",
        semantic_class="query",
        business_effect="Lists governed versions.",
        lifecycle_status="active",
        descriptor_hash="sha256:" + "a" * 64,
        input_schema_hash="sha256:" + "b" * 64,
        output_schema_hash="sha256:" + "c" * 64,
        error_schema_hash="sha256:" + "d" * 64,
        policy_hash="sha256:" + "e" * 64,
        provider_hash="sha256:" + "f" * 64,
        descriptor={"id": capability_id, "major_version": major_version},
    )
    node = ImplementationNode(
        canonical_key="provider:craft.bop",
        owner_domain="craft",
        node_type="provider",
        source_path="plugins/craft/provider.py",
        artifact_hash="sha256:" + "1" * 64,
    )
    return SnapshotDocument(
        product_release_id="product-2026.08",
        extension_release_id="governance-1.0",
        code_revision="abc123",
        snapshot_hash="sha256:" + "2" * 64,
        capabilities=(capability,),
        nodes=(node,),
        bindings=(CapabilityBinding(capability_id, major_version, node.canonical_key, "provider", "sha256:" + "3" * 64),),
        relations=(ImplementationRelation(node.canonical_key, node.canonical_key, "contains", "sha256:" + "4" * 64),),
    )


def test_repeat_projection_reuses_logical_and_major_gid():
    store = MemoryGovernanceStore(next_ids=iter(range(100, 200)).__next__)
    first = project_snapshot(store, snapshot("craft.bop.version.list", 1))
    second = project_snapshot(store, snapshot("craft.bop.version.list", 1))

    assert first.entries[0].capability_gid == second.entries[0].capability_gid
    assert first.entries[0].capability_version_gid == second.entries[0].capability_version_gid


def test_major_version_gets_new_version_gid_but_preserves_logical_gid():
    store = MemoryGovernanceStore(next_ids=iter(range(100, 200)).__next__)
    first = project_snapshot(store, snapshot("craft.bop.version.list", 1))
    second = project_snapshot(store, snapshot("craft.bop.version.list", 2))

    assert first.entries[0].capability_gid == second.entries[0].capability_gid
    assert first.entries[0].capability_version_gid != second.entries[0].capability_version_gid


def test_repeat_projection_does_not_allocate_unused_identity_gids():
    store = MemoryGovernanceStore(next_ids=iter(range(100, 200)).__next__)
    project_snapshot(store, snapshot("craft.bop.version.list", 1))
    repeated = project_snapshot(store, snapshot("craft.bop.version.list", 1))

    assert repeated.scan_run_gid == 108


def test_models_are_immutable_and_json_gids_are_decimal_strings():
    record = project_snapshot(MemoryGovernanceStore(next_ids=iter(range(2**53, 2**53 + 100)).__next__), snapshot("craft.bop.version.list", 1))

    with pytest.raises(FrozenInstanceError):
        record.entries[0].capability_gid = 1

    encoded = record.to_json()
    assert encoded["snapshot_gid"] == str(record.snapshot_gid)
    assert encoded["entries"][0]["capability_gid"] == str(record.entries[0].capability_gid)
    assert encoded["entries"][0]["capability_version_gid"] == str(record.entries[0].capability_version_gid)


def test_canonical_fingerprint_is_independent_of_mapping_order():
    assert canonical_fingerprint({"b": [2, 1], "a": {"y": 2, "x": 1}}) == canonical_fingerprint(
        {"a": {"x": 1, "y": 2}, "b": [2, 1]}
    )
