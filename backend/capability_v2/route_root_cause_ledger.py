"""Validation for the reviewed Web route root-cause ledger."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping


BASELINE_FRONTEND_REVISION = "7848e30803ada6cc687c9e8b3b14ce4020254886"
BASELINE_CONTENT_HASH = "227927b5c91ae24747115ccea4ab72097b951be0dd4d96c8f954455984a71b38"
BASELINE_UNRESOLVED_COUNT = 148
BASELINE_GROUP_COUNT = 93
LEDGER_ARTIFACT_ID = "web-route-root-cause-ledger"
DISPOSITIONS = {
    "existing_stable_capability",
    "truthful_bff_required",
    "new_atomic_capability_required",
    "frontend_retire",
    "frontend_route_normalize",
    "operations_candidate",
}


class RouteRootCauseLedgerConfigurationError(ValueError):
    """Raised when the ledger cannot be parsed safely."""


@dataclass(frozen=True)
class RouteRootCauseLedgerEntry:
    method: str
    normalized_route: str
    occurrence_count: int
    occurrences: tuple[Mapping[str, Any], ...]
    owner_domain: str
    backend_evidence: Mapping[str, Any]
    lifecycle_conclusion: str
    disposition: str
    disposition_details: Mapping[str, Any]

    @property
    def key(self) -> tuple[str, str]:
        return self.method, self.normalized_route


@dataclass(frozen=True)
class RouteRootCauseLedger:
    schema_version: int
    artifact_id: str
    baseline_frontend_revision: str
    baseline_content_hash: str
    baseline_unresolved_count: int
    baseline_group_count: int
    baseline_source_hashes: Mapping[str, str]
    final_evidence: Mapping[str, Any]
    final_unresolved_groups: tuple[Mapping[str, Any], ...]
    entries: tuple[RouteRootCauseLedgerEntry, ...]


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RouteRootCauseLedgerConfigurationError(
            f"invalid route root-cause ledger: {path}"
        ) from exc
    if not isinstance(value, Mapping):
        raise RouteRootCauseLedgerConfigurationError("ledger must be an object")
    return value


def load_route_root_cause_ledger(path: Path) -> RouteRootCauseLedger:
    document = _load_json(path)
    required = {
        "schema_version", "artifact_id", "review_authority",
        "baseline_frontend_revision", "baseline_content_hash",
        "baseline_unresolved_count", "baseline_group_count",
        "baseline_source_hashes", "final_evidence",
        "final_unresolved_groups", "entries",
    }
    if set(document) != required or document.get("schema_version") != 1:
        raise RouteRootCauseLedgerConfigurationError("invalid ledger top-level fields")
    raw_entries = document.get("entries")
    source_hashes = document.get("baseline_source_hashes")
    final_evidence = document.get("final_evidence")
    final_groups = document.get("final_unresolved_groups")
    if (
        not isinstance(raw_entries, list)
        or not isinstance(source_hashes, Mapping)
        or not isinstance(final_evidence, Mapping)
        or not isinstance(final_groups, list)
    ):
        raise RouteRootCauseLedgerConfigurationError("invalid ledger collections")
    entries: list[RouteRootCauseLedgerEntry] = []
    entry_fields = {
        "method", "normalized_route", "occurrence_count", "occurrences",
        "owner_domain", "backend_evidence", "lifecycle_conclusion",
        "disposition", "disposition_details",
    }
    for raw in raw_entries:
        if not isinstance(raw, Mapping) or set(raw) != entry_fields:
            raise RouteRootCauseLedgerConfigurationError("invalid ledger entry fields")
        occurrences = raw.get("occurrences")
        if not isinstance(occurrences, list):
            raise RouteRootCauseLedgerConfigurationError("occurrences must be a list")
        entries.append(RouteRootCauseLedgerEntry(
            method=raw.get("method"),
            normalized_route=raw.get("normalized_route"),
            occurrence_count=raw.get("occurrence_count"),
            occurrences=tuple(occurrences),
            owner_domain=raw.get("owner_domain"),
            backend_evidence=raw.get("backend_evidence"),
            lifecycle_conclusion=raw.get("lifecycle_conclusion"),
            disposition=raw.get("disposition"),
            disposition_details=raw.get("disposition_details"),
        ))
    return RouteRootCauseLedger(
        schema_version=document["schema_version"],
        artifact_id=document.get("artifact_id"),
        baseline_frontend_revision=document.get("baseline_frontend_revision"),
        baseline_content_hash=document.get("baseline_content_hash"),
        baseline_unresolved_count=document.get("baseline_unresolved_count"),
        baseline_group_count=document.get("baseline_group_count"),
        baseline_source_hashes=source_hashes,
        final_evidence=final_evidence,
        final_unresolved_groups=tuple(final_groups),
        entries=tuple(entries),
    )


def _valid_hash(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _anchor_valid(root: Path, anchor: object) -> bool:
    if not isinstance(anchor, Mapping) or set(anchor) != {
        "source_path", "start_line", "end_line", "sha256"
    }:
        return False
    source_path = anchor.get("source_path")
    start = anchor.get("start_line")
    end = anchor.get("end_line")
    if (
        not isinstance(source_path, str)
        or not source_path
        or "\\" in source_path
        or PurePosixPath(source_path).is_absolute()
        or ".." in PurePosixPath(source_path).parts
        or not isinstance(start, int)
        or isinstance(start, bool)
        or not isinstance(end, int)
        or isinstance(end, bool)
        or start < 1
        or end < start
        or not _valid_hash(anchor.get("sha256"))
    ):
        return False
    path = root.joinpath(*PurePosixPath(source_path).parts)
    try:
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    except (OSError, UnicodeDecodeError):
        return False
    if end > len(lines):
        return False
    text = "".join(lines[start - 1:end])
    return hashlib.sha256(text.encode("utf-8")).hexdigest() == anchor["sha256"]


def _target(value: object) -> tuple[str, int] | None:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"([a-z][a-z0-9_.-]+)@([1-9][0-9]*)", value)
    return (match.group(1), int(match.group(2))) if match else None


def _catalog_index(root: Path) -> dict[tuple[str, int], tuple[str, str]]:
    document = _load_json(root / "docs/capabilities/catalog.v2.json")
    capabilities = document.get("capabilities")
    if not isinstance(capabilities, list):
        return {}
    return {
        (raw["id"], raw["major_version"]): (
            raw["lifecycle_status"], raw["owner_domain"]
        )
        for raw in capabilities
        if isinstance(raw, Mapping)
        and isinstance(raw.get("id"), str)
        and isinstance(raw.get("major_version"), int)
        and isinstance(raw.get("lifecycle_status"), str)
        and isinstance(raw.get("owner_domain"), str)
    }


def _final_groups(document: Mapping[str, Any]) -> Counter[tuple[str, str]]:
    routes = document.get("routes")
    if not isinstance(routes, list):
        return Counter()
    return Counter(
        (raw.get("method"), raw.get("normalized_route"))
        for raw in routes
        if isinstance(raw, Mapping) and raw.get("disposition") == "unresolved"
    )


def audit_route_root_cause_ledger(
    root: Path, ledger: RouteRootCauseLedger
) -> tuple[str, ...]:
    issues: list[str] = []
    if ledger.artifact_id != LEDGER_ARTIFACT_ID:
        issues.append("ledger_artifact_id_invalid:1")
    if (
        ledger.baseline_frontend_revision != BASELINE_FRONTEND_REVISION
        or ledger.baseline_content_hash != BASELINE_CONTENT_HASH
        or ledger.baseline_unresolved_count != BASELINE_UNRESOLVED_COUNT
        or ledger.baseline_group_count != BASELINE_GROUP_COUNT
    ):
        issues.append("ledger_baseline_metadata_invalid:1")

    keys = [entry.key for entry in ledger.entries]
    if len(keys) != len(set(keys)):
        issues.append(f"ledger_duplicate_keys:{len(keys) - len(set(keys))}")
    if len(keys) != ledger.baseline_group_count:
        issues.append(f"ledger_group_count:{len(keys)}")

    occurrence_ids: list[str] = []
    sources: dict[str, str] = {}
    catalog = _catalog_index(root)
    for entry in ledger.entries:
        context = f"{entry.method}:{entry.normalized_route}"
        if (
            not isinstance(entry.method, str)
            or entry.method != entry.method.upper()
            or not isinstance(entry.normalized_route, str)
            or not entry.normalized_route.startswith("/api/")
            or not isinstance(entry.occurrence_count, int)
            or isinstance(entry.occurrence_count, bool)
            or entry.occurrence_count != len(entry.occurrences)
        ):
            issues.append(f"ledger_entry_invalid:{context}")
            continue
        if (
            not isinstance(entry.owner_domain, str) or not entry.owner_domain
            or not isinstance(entry.backend_evidence, Mapping)
            or not isinstance(entry.lifecycle_conclusion, str)
            or not entry.lifecycle_conclusion.strip()
            or entry.disposition not in DISPOSITIONS
            or not isinstance(entry.disposition_details, Mapping)
        ):
            issues.append(f"ledger_classification_invalid:{context}")
            continue
        for raw in entry.occurrences:
            required = {
                "occurrence_id", "source", "line", "column", "raw_route",
                "source_sha256",
            }
            if not isinstance(raw, Mapping) or set(raw) != required:
                issues.append(f"ledger_occurrence_invalid:{context}")
                continue
            identity = raw.get("occurrence_id")
            source = raw.get("source")
            source_hash = raw.get("source_sha256")
            if (
                not isinstance(identity, str)
                or not identity.endswith(f":{entry.method}:{entry.normalized_route}")
                or not isinstance(source, str)
                or not _valid_hash(source_hash)
            ):
                issues.append(f"ledger_occurrence_invalid:{context}")
                continue
            occurrence_ids.append(identity)
            if source in sources and sources[source] != source_hash:
                issues.append(f"ledger_source_hash_conflict:{source}")
            sources[source] = source_hash

        anchors = entry.backend_evidence.get("anchors", [])
        if not isinstance(anchors, list) or not all(
            _anchor_valid(root, anchor) for anchor in anchors
        ):
            issues.append(f"ledger_backend_anchor_invalid:{context}")

        details = entry.disposition_details
        if entry.disposition == "existing_stable_capability":
            target = _target(details.get("target_capability"))
            if target is None or catalog.get(target) != ("stable", entry.owner_domain):
                issues.append(f"ledger_existing_target_invalid:{context}")
            if not anchors:
                issues.append(f"ledger_existing_anchor_missing:{context}")
        elif entry.disposition == "truthful_bff_required":
            constituents = details.get("constituent_capabilities")
            parsed = [_target(value) for value in constituents] if isinstance(constituents, list) else []
            if not parsed or any(value is None or catalog.get(value, (None,))[0] != "stable" for value in parsed):
                issues.append(f"ledger_bff_constituent_invalid:{context}")
            if not isinstance(details.get("aggregation_evidence"), str):
                issues.append(f"ledger_bff_evidence_invalid:{context}")
        elif entry.disposition == "new_atomic_capability_required":
            required = {
                "proposed_owner_domain", "atomic_outcome", "provider_or_handler",
                "bounded_input", "bounded_output", "no_stable_target_reason",
            }
            if set(details) != required or any(
                not isinstance(details.get(field), str) or not details[field].strip()
                for field in required
            ):
                issues.append(f"ledger_atomic_proposal_invalid:{context}")
        elif entry.disposition == "frontend_retire":
            if details.get("removed_in_frontend_revision") != ledger.final_evidence.get("frontend_revision"):
                issues.append(f"ledger_retirement_revision_invalid:{context}")
        elif entry.disposition == "frontend_route_normalize":
            finite = details.get("finite_routes")
            if not isinstance(finite, list) or not finite or not all(
                isinstance(value, str)
                and re.fullmatch(r"[A-Z]+ /api/.+", value)
                for value in finite
            ) or details.get("runtime_target_preserved") is not True:
                issues.append(f"ledger_normalization_invalid:{context}")
        elif entry.disposition == "operations_candidate":
            if details.get("approval_status") != "not_approved":
                issues.append(f"ledger_operations_approval_invalid:{context}")

    if len(occurrence_ids) != ledger.baseline_unresolved_count:
        issues.append(f"ledger_occurrence_count:{len(occurrence_ids)}")
    duplicate_occurrences = len(occurrence_ids) - len(set(occurrence_ids))
    if duplicate_occurrences:
        issues.append(f"ledger_duplicate_occurrences:{duplicate_occurrences}")
    if dict(sorted(sources.items())) != dict(sorted(ledger.baseline_source_hashes.items())):
        issues.append("ledger_source_hash_index_mismatch:1")

    final_path = root / "docs/governance/capability-coverage-review/generated/web_route_inventory.json"
    final_document = _load_json(final_path)
    expected_final = ledger.final_evidence
    for field in ("frontend_revision", "content_hash"):
        if final_document.get(field) != expected_final.get(field):
            issues.append(f"ledger_final_{field}_mismatch:1")
    final_counts = final_document.get("counts", {})
    if not isinstance(final_counts, Mapping) or final_counts.get("unresolved") != expected_final.get("unresolved_count"):
        issues.append("ledger_final_unresolved_count_mismatch:1")
    actual_groups = _final_groups(final_document)
    expected_groups = Counter({
        (raw.get("method"), raw.get("normalized_route")): raw.get("occurrence_count")
        for raw in ledger.final_unresolved_groups
        if isinstance(raw, Mapping)
    })
    if actual_groups != expected_groups:
        issues.append("ledger_final_reconciliation_mismatch:1")
    if len(actual_groups) != expected_final.get("unresolved_group_count"):
        issues.append("ledger_final_group_count_mismatch:1")
    return tuple(sorted(set(issues)))


__all__ = [
    "BASELINE_CONTENT_HASH", "BASELINE_FRONTEND_REVISION",
    "BASELINE_GROUP_COUNT", "BASELINE_UNRESOLVED_COUNT",
    "RouteRootCauseLedger", "RouteRootCauseLedgerConfigurationError",
    "RouteRootCauseLedgerEntry", "audit_route_root_cause_ledger",
    "load_route_root_cause_ledger",
]
