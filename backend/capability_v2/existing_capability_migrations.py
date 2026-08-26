"""Independent evidence review for Task 3B.3b Web migration decisions."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Any, Mapping

from .existing_capability_migration_decisions import (
    BASELINE_REVISION,
    MIGRATIONS,
    REVIEWED_DECISIONS,
)


BASELINE_LEDGER_PATH = "docs/governance/web-route-root-cause-ledger.json"
CANONICAL_INVENTORY_PATH = (
    "docs/governance/capability-coverage-review/generated/web_route_inventory.json"
)
FRONTEND_CLIENT = "web/core/existing_capability_client.js"


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
    frontend_operation: str | None
    frontend_call_sites: tuple[Mapping[str, Any], ...]

    @property
    def key(self) -> tuple[str, str]:
        return self.method, self.normalized_route


@dataclass(frozen=True)
class ExistingCapabilityMigrationManifest:
    schema_version: str
    artifact_id: str
    source_ledger: str
    baseline_revision: str
    frontend_revision: str
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
            frontend_operation=item.get("frontend_operation"),
            frontend_call_sites=tuple(item.get("frontend_call_sites", [])),
        )
        for item in raw["groups"]
    )
    return ExistingCapabilityMigrationManifest(
        schema_version=raw["schema_version"],
        artifact_id=raw["artifact_id"],
        source_ledger=raw["source_ledger"],
        baseline_revision=raw["baseline_revision"],
        frontend_revision=raw["frontend_revision"],
        groups=groups,
    )


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


@lru_cache(maxsize=64)
def _git_text(root: Path, revision: str, relative: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), "show", f"{revision}:{relative}"],
        text=True,
        encoding="utf-8",
    )


def _git_revision(root: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        text=True,
        encoding="utf-8",
    ).strip()


def _pinned_groups(root: Path) -> dict[tuple[str, str], Mapping[str, Any]]:
    ledger = json.loads(_git_text(root, BASELINE_REVISION, BASELINE_LEDGER_PATH))
    return {
        (item["method"], item["normalized_route"]): item
        for item in ledger["entries"]
        if item["disposition"] == "existing_capability_migration_required"
    }


def _line_anchor(root: Path, relative: str, needle: str) -> dict[str, Any]:
    path = root.joinpath(*PurePosixPath(relative).parts)
    text = path.read_text(encoding="utf-8")
    offset = text.find(needle)
    if offset < 0:
        raise ValueError(f"candidate anchor missing: {relative}:{needle}")
    line = text.count("\n", 0, offset) + 1
    line_text = text.splitlines(keepends=True)[line - 1]
    return {
        "source_path": relative,
        "source_sha256": _sha256(path),
        "start_line": line,
        "end_line": line,
        "sha256": _sha256_bytes(line_text.encode("utf-8")),
        "needle": needle,
    }


def _operation_targets(source: str) -> dict[str, str]:
    match = re.search(
        r"const\s+operationTargets\s*=\s*Object\.freeze\(\{(?P<body>.*?)\}\);",
        source,
        flags=re.DOTALL,
    )
    if match is None:
        return {}
    pairs = re.findall(
        r"^\s*['\"]([^'\"]+)['\"]\s*:\s*['\"]([^'\"]+)['\"]\s*,?\s*$",
        match.group("body"),
        flags=re.MULTILINE,
    )
    return dict(pairs) if len(pairs) == len(dict(pairs)) else {}


def _source_text(
    web_root: Path,
    relative: str,
    overrides: Mapping[str, str] | None,
) -> str:
    if overrides and relative in overrides:
        return overrides[relative]
    return web_root.joinpath(*PurePosixPath(relative).parts).read_text(encoding="utf-8")


def _frontend_call_sites(
    web_root: Path,
    operation: str,
    sources: list[str],
    overrides: Mapping[str, str] | None = None,
) -> tuple[dict[str, Any], ...]:
    pattern = re.compile(r"\.call\(\s*['\"]" + re.escape(operation) + r"['\"]")
    sites: list[dict[str, Any]] = []
    for relative in sorted(set(sources)):
        source = _source_text(web_root, relative, overrides)
        source_hash = _sha256_bytes(source.encode("utf-8"))
        for match in pattern.finditer(source):
            operation_offset = match.start() + match.group(0).find(operation)
            line = source.count("\n", 0, operation_offset) + 1
            line_start = source.rfind("\n", 0, operation_offset) + 1
            sites.append({
                "source_path": relative,
                "line": line,
                "column": operation_offset - line_start + 1,
                "operation": operation,
                "source_sha256": source_hash,
            })
    return tuple(sorted(sites, key=lambda item: (
        item["source_path"], item["line"], item["column"]
    )))


def _legacy_contract(root: Path, pinned: Mapping[str, Any]) -> dict[str, Any]:
    evidence = pinned["backend_evidence"]
    route_definition = evidence.get("route_definition")
    relative = (
        route_definition["source_path"]
        if isinstance(route_definition, Mapping)
        else evidence["source_path"]
    )
    source = _git_text(root, BASELINE_REVISION, relative)
    if not isinstance(route_definition, Mapping):
        return {
            "kind": "reviewed_handler_absence",
            "source_path": relative,
            "source_sha256": _sha256_bytes(source.encode("utf-8")),
            "revision": BASELINE_REVISION,
            "method": pinned["method"],
            "normalized_route": pinned["normalized_route"],
            "finding": evidence["finding"],
        }
    route = dict(route_definition)
    lines = source.splitlines(keepends=True)
    anchored = "".join(lines[route["start_line"] - 1:route["end_line"]])
    if _sha256_bytes(anchored.encode("utf-8")) != route["sha256"]:
        raise ValueError(f"pinned legacy anchor drift: {pinned['method']}:{pinned['normalized_route']}")
    return {
        "kind": "registered_route_definition",
        **route,
        "revision": BASELINE_REVISION,
        "source_sha256": _sha256_bytes(source.encode("utf-8")),
    }


def build_existing_capability_migration_document(
    root: Path,
    web_root: Path,
) -> dict[str, Any]:
    pinned_groups = _pinned_groups(root)
    if set(pinned_groups) != set(REVIEWED_DECISIONS):
        raise ValueError("reviewed decisions do not match the pinned 53-group baseline")
    client_source = _source_text(web_root, FRONTEND_CLIENT, None)
    actual_targets = _operation_targets(client_source)
    expected_targets = {
        item["operation"]: item["target"].rsplit("@", 1)[0]
        for item in MIGRATIONS.values()
    }
    if actual_targets != expected_targets:
        raise ValueError("frontend operation target map does not match reviewed decisions")

    groups: list[dict[str, Any]] = []
    for key in sorted(pinned_groups):
        pinned = pinned_groups[key]
        reviewed = REVIEWED_DECISIONS[key]
        target, major = reviewed["target"].rsplit("@", 1)
        base = {
            "method": key[0],
            "normalized_route": key[1],
            "occurrence_count": pinned["occurrence_count"],
            "occurrences": pinned["occurrences"],
            "target_capability_id": target,
            "target_major_version": int(major),
            "owner_domain": pinned["owner_domain"],
            "transport_evidence": pinned["backend_evidence"],
            "decision": reviewed["decision"],
        }
        if reviewed["decision"] == "migrate":
            operation = reviewed["operation"]
            source_paths = [item["source"] for item in pinned["occurrences"]]
            call_sites = _frontend_call_sites(web_root, operation, source_paths)
            if len(call_sites) != pinned["occurrence_count"]:
                raise ValueError(f"frontend call-site count mismatch: {key}")
            evidence = _line_anchor(
                root, reviewed["provider_source"], reviewed["provider_needle"]
            )
            groups.append({
                **base,
                "request_transform": reviewed["request"],
                "response_transform": reviewed["response"],
                "frontend_operation": operation,
                "frontend_call_sites": list(call_sites),
                "equivalence_evidence": {
                    "proof_kind": "provider_equivalent_adapter",
                    "provider_contract": evidence,
                },
                "reclassification": None,
            })
        else:
            candidate = _line_anchor(
                root, reviewed["candidate_source"], reviewed["candidate_needle"]
            )
            mismatch = reviewed["contract_mismatch"]
            groups.append({
                **base,
                "request_transform": "not applied: " + mismatch["input"],
                "response_transform": "not applied: " + mismatch["output"],
                "frontend_operation": None,
                "frontend_call_sites": [],
                "equivalence_evidence": None,
                "reclassification": {
                    "reason_code": reviewed["reason_code"],
                    "followup": reviewed["followup"],
                    "finding": " | ".join(mismatch.values()),
                    "legacy_contract": _legacy_contract(root, pinned),
                    "candidate_contracts": [candidate],
                    "contract_mismatch": mismatch,
                },
            })
    return {
        "schema_version": "2.0",
        "artifact_id": "existing-capability-web-migrations",
        "source_ledger": BASELINE_LEDGER_PATH,
        "baseline_revision": BASELINE_REVISION,
        "frontend_revision": _git_revision(web_root),
        "groups": groups,
    }


def _anchor_issues(root: Path, raw: Mapping[str, Any], context: str) -> list[str]:
    issues: list[str] = []
    relative = raw.get("source_path")
    if not isinstance(relative, str):
        return [f"migration_contract_anchor_invalid:{context}"]
    path = root.joinpath(*PurePosixPath(relative).parts)
    if not path.is_file() or raw.get("source_sha256") != _sha256(path):
        issues.append(f"migration_contract_source_hash_invalid:{context}")
        return issues
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    start, end = raw.get("start_line"), raw.get("end_line")
    if not isinstance(start, int) or not isinstance(end, int) or not 1 <= start <= end <= len(lines):
        issues.append(f"migration_contract_anchor_invalid:{context}")
        return issues
    text = "".join(lines[start - 1:end])
    if raw.get("sha256") != _sha256_bytes(text.encode("utf-8")):
        issues.append(f"migration_contract_anchor_hash_invalid:{context}")
    if not isinstance(raw.get("needle"), str) or raw["needle"] not in text:
        issues.append(f"migration_contract_anchor_needle_invalid:{context}")
    return issues


def audit_existing_capability_migrations(
    root: Path,
    manifest: ExistingCapabilityMigrationManifest,
    *,
    web_root: Path | None = None,
    ledger_path: Path | None = None,
    ledger_document: Mapping[str, Any] | None = None,
    frontend_source_overrides: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    issues: list[str] = []
    if (
        manifest.schema_version != "2.0"
        or manifest.artifact_id != "existing-capability-web-migrations"
        or manifest.baseline_revision != BASELINE_REVISION
        or manifest.source_ledger != BASELINE_LEDGER_PATH
    ):
        issues.append("migration_manifest_identity_invalid")
    pinned = _pinned_groups(root)
    groups = {group.key: group for group in manifest.groups}
    if len(groups) != len(manifest.groups):
        issues.append("migration_manifest_duplicate_key")
    if set(groups) != set(pinned) or len(groups) != 53:
        issues.append("migration_manifest_pinned_key_mismatch")

    catalog = json.loads((root / "docs/capabilities/catalog.v2.json").read_text(encoding="utf-8"))
    targets = {
        (item["id"], item["major_version"]): item
        for item in catalog["capabilities"]
    }
    actual_operation_targets: dict[str, str] = {}
    if web_root is not None:
        client = _source_text(web_root, FRONTEND_CLIENT, frontend_source_overrides)
        actual_operation_targets = _operation_targets(client)
        expected_operation_targets = {
            item["operation"]: item["target"].rsplit("@", 1)[0]
            for item in MIGRATIONS.values()
        }
        if actual_operation_targets != expected_operation_targets:
            issues.append("migration_frontend_operation_map_mismatch")
        if manifest.frontend_revision != _git_revision(web_root):
            issues.append("migration_frontend_revision_mismatch")

    for key, group in groups.items():
        context = f"{key[0]}:{key[1]}"
        baseline = pinned.get(key)
        reviewed = REVIEWED_DECISIONS.get(key)
        if baseline is None or reviewed is None:
            continue
        expected_target, expected_major = reviewed["target"].rsplit("@", 1)
        if (
            group.target_capability_id != expected_target
            or group.target_major_version != int(expected_major)
        ):
            issues.append(f"migration_reviewed_target_mismatch:{context}")
        if group.decision != reviewed["decision"]:
            issues.append(f"migration_reviewed_decision_mismatch:{context}")
        if (
            group.occurrence_count != baseline["occurrence_count"]
            or list(group.occurrences) != baseline["occurrences"]
        ):
            issues.append(f"migration_pinned_occurrence_mismatch:{context}")
        target = targets.get((group.target_capability_id, group.target_major_version))
        if (
            not target
            or target.get("lifecycle_status") != "stable"
            or target.get("owner_domain") != group.owner_domain
        ):
            issues.append(f"migration_target_invalid:{context}")
        if group.decision == "migrate":
            if group.frontend_operation != reviewed.get("operation"):
                issues.append(f"migration_frontend_operation_mismatch:{context}")
            evidence = group.equivalence_evidence
            provider = evidence.get("provider_contract") if isinstance(evidence, Mapping) else None
            if not isinstance(provider, Mapping):
                issues.append(f"migration_equivalence_invalid:{context}")
            else:
                issues.extend(_anchor_issues(root, provider, context))
            if web_root is not None:
                sources = [item["source"] for item in baseline["occurrences"]]
                actual_sites = _frontend_call_sites(
                    web_root, reviewed["operation"], sources, frontend_source_overrides
                )
                if list(actual_sites) != list(group.frontend_call_sites):
                    issues.append(f"migration_frontend_call_site_mismatch:{context}")
                if actual_operation_targets.get(reviewed["operation"]) != expected_target:
                    issues.append(f"migration_frontend_target_mismatch:{context}")
        else:
            evidence = group.reclassification
            mismatch = evidence.get("contract_mismatch") if isinstance(evidence, Mapping) else None
            if (
                not isinstance(evidence, Mapping)
                or evidence.get("reason_code") != reviewed.get("reason_code")
                or evidence.get("followup") != reviewed.get("followup")
                or not isinstance(mismatch, Mapping)
                or mismatch != reviewed.get("contract_mismatch")
                or any(
                    not isinstance(mismatch.get(field), str)
                    or group.normalized_route not in mismatch[field]
                    or len(mismatch[field]) < 40
                    for field in ("input", "output", "side_effects")
                )
            ):
                issues.append(f"migration_reclassification_contract_invalid:{context}")
                continue
            legacy = evidence.get("legacy_contract")
            candidates = evidence.get("candidate_contracts")
            if not isinstance(legacy, Mapping) or legacy != _legacy_contract(root, baseline):
                issues.append(f"migration_legacy_contract_mismatch:{context}")
            if not isinstance(candidates, list) or not candidates:
                issues.append(f"migration_candidate_contract_missing:{context}")
            else:
                for candidate in candidates:
                    if isinstance(candidate, Mapping):
                        issues.extend(_anchor_issues(root, candidate, context))
                    else:
                        issues.append(f"migration_candidate_contract_invalid:{context}")

    ledger_raw = ledger_document
    if ledger_raw is None and ledger_path is not None:
        ledger_raw = json.loads(ledger_path.read_text(encoding="utf-8"))
    if ledger_raw is not None:
        ledger_entries = {
            (item["method"], item["normalized_route"]): item
            for item in ledger_raw.get("entries", [])
        }
        for key, group in groups.items():
            entry = ledger_entries.get(key)
            expected_disposition = (
                "existing_capability_migrated"
                if group.decision == "migrate"
                else "existing_capability_reclassified"
            )
            if entry is None or entry.get("disposition") != expected_disposition:
                issues.append(f"migration_ledger_decision_mismatch:{key[0]}:{key[1]}")
                continue
            details = entry.get("disposition_details", {})
            target = (
                details.get("target_capability")
                or details.get("candidate_target_capability")
            )
            if target != f"{group.target_capability_id}@{group.target_major_version}":
                issues.append(f"migration_ledger_target_mismatch:{key[0]}:{key[1]}")

    if web_root is not None:
        inventory_path = root / CANONICAL_INVENTORY_PATH
        if inventory_path.is_file():
            inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
            final_keys = Counter(
                (item.get("method"), item.get("normalized_route"))
                for item in inventory.get("routes", [])
                if item.get("disposition") == "unresolved"
            )
            for key, group in groups.items():
                if group.decision == "migrate" and key in final_keys:
                    issues.append(f"migration_final_route_remains:{key[0]}:{key[1]}")
                if group.decision == "reclassify" and final_keys[key] != group.occurrence_count:
                    issues.append(f"migration_final_reclassification_mismatch:{key[0]}:{key[1]}")
    return tuple(sorted(set(issues)))


__all__ = [
    "BASELINE_REVISION",
    "ExistingCapabilityMigrationGroup",
    "ExistingCapabilityMigrationManifest",
    "audit_existing_capability_migrations",
    "build_existing_capability_migration_document",
    "load_existing_capability_migrations",
]
