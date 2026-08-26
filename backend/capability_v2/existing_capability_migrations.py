"""Validated Task 3B.3b Web migration decisions."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any, Mapping


@dataclass(frozen=True)
class ExistingCapabilityMigrationGroup:
    method: str
    normalized_route: str
    occurrence_count: int
    occurrences: tuple[Mapping[str, Any], ...]
    target_capability_id: str
    target_major_version: int
    owner_domain: str
    transport_evidence: Mapping[str, Any]
    request_transform: str
    response_transform: str
    decision: str
    equivalence_evidence: Mapping[str, Any] | None
    reclassification: Mapping[str, Any] | None


@dataclass(frozen=True)
class ExistingCapabilityMigrationManifest:
    schema_version: str
    artifact_id: str
    source_ledger: str
    groups: tuple[ExistingCapabilityMigrationGroup, ...]


def load_existing_capability_migrations(path: Path) -> ExistingCapabilityMigrationManifest:
    raw = json.loads(path.read_text(encoding="utf-8"))
    groups = tuple(
        ExistingCapabilityMigrationGroup(
            method=item["method"],
            normalized_route=item["normalized_route"],
            occurrence_count=item["occurrence_count"],
            occurrences=tuple(item["occurrences"]),
            target_capability_id=item["target_capability_id"],
            target_major_version=item["target_major_version"],
            owner_domain=item["owner_domain"],
            transport_evidence=item["transport_evidence"],
            request_transform=item["request_transform"],
            response_transform=item["response_transform"],
            decision=item["decision"],
            equivalence_evidence=item.get("equivalence_evidence"),
            reclassification=item.get("reclassification"),
        )
        for item in raw["groups"]
    )
    return ExistingCapabilityMigrationManifest(
        schema_version=raw["schema_version"], artifact_id=raw["artifact_id"],
        source_ledger=raw["source_ledger"], groups=groups,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_existing_capability_migrations(
    root: Path, manifest: ExistingCapabilityMigrationManifest
) -> tuple[str, ...]:
    issues: list[str] = []
    if manifest.schema_version != "1.0" or manifest.artifact_id != "existing-capability-web-migrations":
        issues.append("migration_manifest_identity_invalid")
    keys = [(group.method, group.normalized_route) for group in manifest.groups]
    if len(keys) != len(set(keys)):
        issues.append("migration_manifest_duplicate_key")
    if len(keys) != 53 or sum(group.occurrence_count for group in manifest.groups) != 80:
        issues.append("migration_manifest_baseline_count_invalid")

    catalog = json.loads((root / "docs/capabilities/catalog.v2.json").read_text(encoding="utf-8"))
    targets = {
        (raw["id"], raw["major_version"]): raw
        for raw in catalog.get("capabilities", []) if isinstance(raw, Mapping)
    }
    for group in manifest.groups:
        context = f"{group.method}:{group.normalized_route}"
        target = targets.get((group.target_capability_id, group.target_major_version))
        if not target or target.get("lifecycle_status") != "stable" or target.get("owner_domain") != group.owner_domain:
            issues.append(f"migration_target_invalid:{context}")
        if group.occurrence_count != len(group.occurrences) or not group.occurrences:
            issues.append(f"migration_occurrences_invalid:{context}")
        if group.decision not in {"migrate", "reclassify"}:
            issues.append(f"migration_decision_invalid:{context}")
        if not group.request_transform.strip() or not group.response_transform.strip():
            issues.append(f"migration_transform_missing:{context}")
        if group.decision == "migrate":
            evidence = group.equivalence_evidence
            if not isinstance(evidence, Mapping) or evidence.get("proof_kind") != "provider_equivalent_adapter":
                issues.append(f"migration_equivalence_invalid:{context}")
                continue
        else:
            evidence = group.reclassification
            if not isinstance(evidence, Mapping) or evidence.get("reason_code") not in {
                "adapter_side_effect_missing", "contract_shape_mismatch", "outcome_mismatch",
                "projection_mismatch", "provider_equivalence_missing", "state_model_mismatch",
            } or evidence.get("followup") not in {"atomic_capability_review", "provider_adapter_review", "bff_review"}:
                issues.append(f"migration_reclassification_invalid:{context}")
                continue
        sources = evidence.get("sources") if isinstance(evidence, Mapping) else None
        if not isinstance(sources, list) or not sources:
            issues.append(f"migration_evidence_sources_missing:{context}")
            continue
        for source in sources:
            if not isinstance(source, Mapping):
                issues.append(f"migration_evidence_source_invalid:{context}")
                continue
            relative = source.get("source_path")
            if not isinstance(relative, str) or PurePosixPath(relative).is_absolute() or ".." in PurePosixPath(relative).parts:
                issues.append(f"migration_evidence_source_invalid:{context}")
                continue
            path = root.joinpath(*PurePosixPath(relative).parts)
            if not path.is_file() or source.get("sha256") != _sha256(path):
                issues.append(f"migration_evidence_hash_invalid:{context}")
    return tuple(issues)


__all__ = [
    "ExistingCapabilityMigrationGroup", "ExistingCapabilityMigrationManifest",
    "audit_existing_capability_migrations", "load_existing_capability_migrations",
]
