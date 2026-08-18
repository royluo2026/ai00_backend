from __future__ import annotations

from dataclasses import replace

from backend.capability_governance_test.analysis import AnalysisRequest, run_deterministic_analysis
from backend.capability_governance_test.fingerprint import snapshot_fingerprint
from backend.capability_governance_test.models import (
    CapabilityBinding,
    ImplementationNode,
    ImplementationRelation,
    ScannedCapability,
    SnapshotDocument,
)
from backend.capability_governance_test.rules import RULES


def _capability(**overrides: object) -> ScannedCapability:
    values: dict[str, object] = {
        "capability_id": "craft.resource.create",
        "major_version": 1,
        "owner_domain": "craft",
        "semantic_class": "strong_write",
        "business_effect": "Create resource.",
        "lifecycle_status": "active",
        "descriptor_hash": "sha256:" + "a" * 64,
        "input_schema_hash": "sha256:" + "b" * 64,
        "output_schema_hash": "sha256:" + "c" * 64,
        "error_schema_hash": "sha256:" + "d" * 64,
        "policy_hash": "sha256:" + "e" * 64,
        "provider_hash": "sha256:" + "f" * 64,
        "descriptor": {
            "id": "craft.resource.create", "major_version": 1,
            "side_effect_level": "strong_write", "business_object": "resource",
            "operation_family": "create", "consistency_policy": "strong",
            "authorization_policy": {"family": "resource.write"},
            "confirmation_policy": {"required": True},
        },
    }
    values.update(overrides)
    return ScannedCapability(**values)  # type: ignore[arg-type]


def _snapshot(
    capability: ScannedCapability | None = None,
    *,
    nodes: tuple[ImplementationNode, ...] = (),
    bindings: tuple[CapabilityBinding, ...] = (),
    relations: tuple[ImplementationRelation, ...] = (),
) -> SnapshotDocument:
    document = SnapshotDocument(
        "product-test", None, "revision", "", (capability or _capability,), nodes, bindings, relations,
    )
    return replace(document, snapshot_hash=snapshot_fingerprint(document))


def _find(result, code: str):
    return next(item for item in result.findings if item.code == code)


def test_strong_write_without_transactional_provider_blocks_release() -> None:
    capability = _capability()
    provider = ImplementationNode("provider:craft:create", "craft", "provider", "craft/provider.py", "sha256:" + "1" * 64)
    snapshot = _snapshot(capability, nodes=(provider,), bindings=(
        CapabilityBinding(capability.capability_id, 1, provider.canonical_key, "implemented_by", "sha256:" + "2" * 64),
    ))

    finding = _find(run_deterministic_analysis(snapshot, AnalysisRequest()), "transaction_participant_missing")

    assert finding.severity == "blocking"
    assert finding.remediation_boundary == "provider_transaction_boundary"


def test_release_rules_are_named_and_detect_representative_missing_evidence() -> None:
    capability = _capability(lifecycle_status="active")
    repository = ImplementationNode("repository:craft:resource", "craft", "repository", "craft/repository.py", "sha256:" + "3" * 64)
    table = ImplementationNode("database_table:craft:resource", "craft", "database_table", "tables/resource", "sha256:" + "9" * 64)
    exposure = ImplementationNode("rest_route:craft:resource", "craft", "rest_route", "craft/routes.py", "sha256:" + "4" * 64)
    stale = ImplementationNode("provider:craft:stale", "craft", "provider", "craft/provider.py", "", metadata={"stale": True})
    governance = ImplementationNode("worker:craft:governance", "craft", "worker", "backend/capability_governance_test/prod.py", "sha256:" + "5" * 64)
    snapshot = _snapshot(capability, nodes=(repository, table, exposure, stale, governance), relations=(
        ImplementationRelation(repository.canonical_key, table.canonical_key, "persists_to", "sha256:" + "8" * 64),
    ))

    result = run_deterministic_analysis(snapshot, AnalysisRequest())
    codes = {item.code for item in result.findings}

    assert {rule.__name__ for rule in RULES} == {
        "descriptor_without_provider", "provider_without_descriptor", "exposure_without_capability",
        "strong_write_without_transactional_provider", "repository_table_migration_mismatch",
        "permission_policy_mismatch", "confirmation_policy_mismatch", "catalog_schema_drift",
        "required_test_missing", "stale_evidence", "lifecycle_incompatibility",
        "production_governance_artifact_present",
    }
    assert {"provider_missing", "exposure_without_capability", "repository_table_migration_mismatch",
            "required_test_missing", "stale_evidence", "production_governance_artifact_present"} <= codes


def test_finding_fingerprint_is_stable_when_input_order_changes() -> None:
    capability = _capability()
    provider = ImplementationNode("provider:craft:create", "craft", "provider", "craft/provider.py", "sha256:" + "1" * 64, metadata={"transactional": True})
    test_case = ImplementationNode("test_case:craft:create", "craft", "test_case", "craft/test_provider.py", "sha256:" + "2" * 64)
    bindings = (
        CapabilityBinding(capability.capability_id, 1, provider.canonical_key, "implemented_by", "sha256:" + "3" * 64),
        CapabilityBinding(capability.capability_id, 1, test_case.canonical_key, "tested_by", "sha256:" + "4" * 64),
    )

    first = run_deterministic_analysis(_snapshot(capability, nodes=(provider, test_case), bindings=bindings), AnalysisRequest())
    second = run_deterministic_analysis(_snapshot(capability, nodes=(test_case, provider), bindings=tuple(reversed(bindings))), AnalysisRequest())

    assert [(item.code, item.fingerprint) for item in first.findings] == [(item.code, item.fingerprint) for item in second.findings]
