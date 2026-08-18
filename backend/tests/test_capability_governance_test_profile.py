from __future__ import annotations

from backend.capabilities.models_next import CapabilityContext
from backend.capability_governance_test.fingerprint import snapshot_fingerprint
from backend.capability_governance_test.models import (
    CapabilityBinding,
    ImplementationNode,
    ScannedCapability,
    SnapshotDocument,
)
from backend.capability_governance_test.store import MemoryGovernanceStore
from backend.capability_v2.bootstrap import build_test_governance_capability_registry


def _hash(value: str) -> str:
    return "sha256:" + value * 64


def test_test_profile_accepts_seeded_store_and_exposes_authoritative_graph_data() -> None:
    capability = ScannedCapability(
        "base.example.read", 1, "base", "read", "Read an example", "stable",
        _hash("a"), _hash("b"), _hash("c"), _hash("d"), _hash("e"), _hash("f"),
        {"description": "Read an example"},
    )
    node = ImplementationNode(
        "provider:base:example", "base", "provider", "backend/example.py", _hash("1"),
    )
    binding = CapabilityBinding(
        capability.capability_id, 1, node.canonical_key, "implemented_by", _hash("2"),
    )
    draft = SnapshotDocument(
        "product-1", "extension-1", "revision-1", "", (capability,), (node,), (binding,), (),
    )
    document = SnapshotDocument(
        draft.product_release_id, draft.extension_release_id, draft.code_revision,
        snapshot_fingerprint(draft), draft.capabilities, draft.nodes, draft.bindings, draft.relations,
    )
    ids = iter(range(100, 1000)).__next__
    store = MemoryGovernanceStore(next_ids=ids)
    registry = build_test_governance_capability_registry(store=store, seed_document=document)
    snapshot = next(iter(store._snapshots.values()))
    context = CapabilityContext(user_gid="42", permissions=("system.capability.read",))

    graph = registry.get("base.capability_graph.get").handler({
        "target_gid": str(snapshot.snapshot_gid), "max_depth": 2, "max_nodes": 20,
    }, context)
    assert graph["bindings"][0]["binding_gid"] == str(snapshot.binding_gids[0])
    assert graph["nodes"][0]["implementation_node_gid"] == str(snapshot.node_gids[node.canonical_key])

    findings = registry.get("base.capability_finding.search").handler({
        "target_gid": str(snapshot.snapshot_gid), "limit": 20,
    }, context)
    assert findings["findings"]
    assert all("finding_gid" in finding and "evidence" in finding for finding in findings["findings"])
