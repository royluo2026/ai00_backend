"""Validation for the reviewed Web route root-cause ledger."""
from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Any, Mapping


BASELINE_BACKEND_REVISION = "800ec6ba559db3301221e674b2a5026d354214ff"
BASELINE_INVENTORY_PATH = (
    "docs/governance/capability-coverage-review/generated/web_route_inventory.json"
)
BASELINE_INVENTORY_SHA256 = (
    "55f3de074e060a71dc6acab4bee993d42d7af05026e6acd4c0e8d7f6d06b9694"
)
BASELINE_FRONTEND_REVISION = "7848e30803ada6cc687c9e8b3b14ce4020254886"
BASELINE_CONTENT_HASH = "227927b5c91ae24747115ccea4ab72097b951be0dd4d96c8f954455984a71b38"
BASELINE_UNRESOLVED_COUNT = 148
BASELINE_GROUP_COUNT = 93
CLASSIFIED_OCCURRENCE_COUNT = 161
CLASSIFIED_GROUP_COUNT = 102
LEDGER_ARTIFACT_ID = "web-route-root-cause-ledger"
DISPOSITIONS = {
    "existing_stable_capability",
    "existing_capability_migration_required",
    "existing_capability_migrated",
    "existing_capability_reclassified",
    "truthful_bff_required",
    "truthful_bff_registered",
    "conditional_dispatch_required",
    "conditional_dispatch_migrated",
    "conditional_dispatch_partially_migrated",
    "new_atomic_capability_required",
    "frontend_retire",
    "frontend_route_normalize",
    "operations_candidate",
    "file_store_capability_migrated",
}
RETIREMENT_KINDS = {
    "explicit_product_retirement",
    "backend_route_retired",
    "http_410",
    "sample_template_only",
    "backend_route_absent",
}
HTTP_METHODS = {"delete", "get", "head", "options", "patch", "post", "put"}


class RouteRootCauseLedgerConfigurationError(ValueError):
    """Raised when the ledger cannot be parsed safely."""


@dataclass(frozen=True)
class RouteRootCauseLedgerEntry:
    method: str
    normalized_route: str
    occurrence_scope: str
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
    baseline_backend_revision: str
    baseline_inventory_path: str
    baseline_inventory_sha256: str
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
        "baseline_backend_revision", "baseline_inventory_path",
        "baseline_inventory_sha256", "baseline_frontend_revision",
        "baseline_content_hash", "baseline_unresolved_count",
        "baseline_group_count", "baseline_source_hashes", "final_evidence",
        "final_unresolved_groups", "entries",
    }
    if set(document) != required or document.get("schema_version") != 2:
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
    entry_fields = {
        "method", "normalized_route", "occurrence_scope", "occurrence_count",
        "occurrences", "owner_domain", "backend_evidence",
        "lifecycle_conclusion", "disposition", "disposition_details",
    }
    entries: list[RouteRootCauseLedgerEntry] = []
    for raw in raw_entries:
        if not isinstance(raw, Mapping) or set(raw) != entry_fields:
            raise RouteRootCauseLedgerConfigurationError("invalid ledger entry fields")
        occurrences = raw.get("occurrences")
        if not isinstance(occurrences, list):
            raise RouteRootCauseLedgerConfigurationError("occurrences must be a list")
        entries.append(RouteRootCauseLedgerEntry(
            method=raw.get("method"), normalized_route=raw.get("normalized_route"),
            occurrence_scope=raw.get("occurrence_scope"),
            occurrence_count=raw.get("occurrence_count"),
            occurrences=tuple(occurrences), owner_domain=raw.get("owner_domain"),
            backend_evidence=raw.get("backend_evidence"),
            lifecycle_conclusion=raw.get("lifecycle_conclusion"),
            disposition=raw.get("disposition"),
            disposition_details=raw.get("disposition_details"),
        ))
    return RouteRootCauseLedger(
        schema_version=document["schema_version"],
        artifact_id=document.get("artifact_id"),
        baseline_backend_revision=document.get("baseline_backend_revision"),
        baseline_inventory_path=document.get("baseline_inventory_path"),
        baseline_inventory_sha256=document.get("baseline_inventory_sha256"),
        baseline_frontend_revision=document.get("baseline_frontend_revision"),
        baseline_content_hash=document.get("baseline_content_hash"),
        baseline_unresolved_count=document.get("baseline_unresolved_count"),
        baseline_group_count=document.get("baseline_group_count"),
        baseline_source_hashes=source_hashes, final_evidence=final_evidence,
        final_unresolved_groups=tuple(final_groups), entries=tuple(entries),
    )


def _valid_hash(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _safe_relative_path(value: object) -> str | None:
    if not isinstance(value, str) or not value or "\\" in value:
        return None
    path = PurePosixPath(value)
    return None if path.is_absolute() or ".." in path.parts else value


def _git_blob(root: Path, revision: str, source_path: str) -> bytes | None:
    result = subprocess.run(
        ["git", "-C", str(root), "show", f"{revision}:{source_path}"],
        capture_output=True, check=False,
    )
    return result.stdout if result.returncode == 0 else None


def _line_slice(text: str, start: int, end: int) -> str | None:
    lines = text.splitlines(keepends=True)
    if start < 1 or end < start or end > len(lines):
        return None
    return "".join(lines[start - 1:end])


def _anchor_text(
    root: Path,
    anchor: object,
    *,
    web_root: Path | None = None,
) -> str | None:
    if not isinstance(anchor, Mapping) or set(anchor) != {
        "repository", "source_path", "start_line", "end_line", "sha256"
    }:
        return None
    repository = anchor.get("repository")
    source_path = _safe_relative_path(anchor.get("source_path"))
    start, end = anchor.get("start_line"), anchor.get("end_line")
    if (
        repository not in {"backend", "frontend_baseline", "frontend_final"}
        or source_path is None
        or not isinstance(start, int) or isinstance(start, bool)
        or not isinstance(end, int) or isinstance(end, bool)
        or not _valid_hash(anchor.get("sha256"))
    ):
        return None
    if repository == "backend":
        try:
            text = root.joinpath(*PurePosixPath(source_path).parts).read_text(
                encoding="utf-8"
            )
        except (OSError, UnicodeDecodeError):
            return None
    elif web_root is None:
        return "__structurally_valid_unverified_frontend_anchor__"
    elif repository == "frontend_baseline":
        blob = _git_blob(web_root, BASELINE_FRONTEND_REVISION, source_path)
        if blob is None:
            return None
        try:
            text = blob.decode("utf-8")
        except UnicodeDecodeError:
            return None
    else:
        try:
            text = web_root.joinpath(*PurePosixPath(source_path).parts).read_text(
                encoding="utf-8"
            )
        except (OSError, UnicodeDecodeError):
            return None
    selected = _line_slice(text, start, end)
    if selected is None:
        return None
    return selected if hashlib.sha256(selected.encode("utf-8")).hexdigest() == anchor["sha256"] else None


def _anchor_valid(root: Path, anchor: object, *, web_root: Path | None = None) -> bool:
    return _anchor_text(root, anchor, web_root=web_root) is not None


def _normalize_backend_route(value: str) -> str:
    value = re.sub(r"\{[^{}]+\}", "{dynamic}", value)
    value = re.sub(r"/{2,}", "/", value)
    return value.rstrip("/") if len(value) > 1 else value


def _route_definitions(root: Path, source_path: str) -> list[dict[str, Any]]:
    safe = _safe_relative_path(source_path)
    if safe is None:
        return []
    path = root.joinpath(*PurePosixPath(safe).parts)
    try:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
    except (OSError, UnicodeDecodeError, SyntaxError):
        return []
    prefixes: dict[str, str] = {}
    for node in tree.body:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        if not isinstance(value, ast.Call):
            continue
        if not isinstance(value.func, ast.Name) or value.func.id != "APIRouter":
            continue
        prefix = ""
        for keyword in value.keywords:
            if keyword.arg == "prefix" and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                prefix = keyword.value.value
        for target in targets:
            if isinstance(target, ast.Name):
                prefixes[target.id] = prefix
    lines = text.splitlines(keepends=True)
    definitions: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if (
                not isinstance(decorator, ast.Call)
                or not isinstance(decorator.func, ast.Attribute)
                or decorator.func.attr not in HTTP_METHODS
                or not isinstance(decorator.func.value, ast.Name)
                or decorator.func.value.id not in prefixes
                or not decorator.args
                or not isinstance(decorator.args[0], ast.Constant)
                or not isinstance(decorator.args[0].value, str)
            ):
                continue
            prefix = prefixes[decorator.func.value.id].rstrip("/")
            suffix = decorator.args[0].value
            route = suffix if suffix.startswith("/api/") else prefix + "/" + suffix.lstrip("/")
            start, end = decorator.lineno, node.end_lineno or node.lineno
            selected = "".join(lines[start - 1:end])
            definitions.append({
                "source_path": source_path, "start_line": start, "end_line": end,
                "sha256": hashlib.sha256(selected.encode("utf-8")).hexdigest(),
                "method": decorator.func.attr.upper(),
                "normalized_route": _normalize_backend_route(route),
            })
    return definitions


def build_route_definition_evidence(
    root: Path, source_path: str, key: tuple[str, str]
) -> dict[str, Any] | None:
    matches = [
        raw for raw in _route_definitions(root, source_path)
        if (raw["method"], raw["normalized_route"]) == key
    ]
    return matches[0] if len(matches) == 1 else None


def _target(value: object) -> tuple[str, int] | None:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"([a-z][a-z0-9_.-]+)@([1-9][0-9]*)", value)
    return (match.group(1), int(match.group(2))) if match else None


def _catalog_index(root: Path) -> dict[tuple[str, int], tuple[str, str]]:
    capabilities = _load_json(root / "docs/capabilities/catalog.v2.json").get("capabilities")
    if not isinstance(capabilities, list):
        return {}
    return {
        (raw["id"], raw["major_version"]): (raw["lifecycle_status"], raw["owner_domain"])
        for raw in capabilities
        if isinstance(raw, Mapping)
        and isinstance(raw.get("id"), str)
        and isinstance(raw.get("major_version"), int)
        and isinstance(raw.get("lifecycle_status"), str)
        and isinstance(raw.get("owner_domain"), str)
    }


def _pinned_baseline(root: Path) -> tuple[Mapping[str, Any] | None, str | None]:
    blob = _git_blob(root, BASELINE_BACKEND_REVISION, BASELINE_INVENTORY_PATH)
    if blob is None:
        return None, None
    digest = hashlib.sha256(blob).hexdigest()
    try:
        document = json.loads(blob.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, digest
    return document if isinstance(document, Mapping) else None, digest


def _without_source_hash(raw: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in raw.items() if key != "source_sha256"}


def _occurrence_mismatch_count(
    expected: list[Mapping[str, Any]], actual: list[Mapping[str, Any]]
) -> int:
    expected_by_id = {
        raw.get("occurrence_id"): dict(raw)
        for raw in expected if isinstance(raw.get("occurrence_id"), str)
    }
    actual_by_id = {
        raw.get("occurrence_id"): _without_source_hash(raw)
        for raw in actual if isinstance(raw.get("occurrence_id"), str)
    }
    return sum(
        expected_by_id.get(identity) != actual_by_id.get(identity)
        for identity in set(expected_by_id) | set(actual_by_id)
    )


def _final_groups(document: Mapping[str, Any]) -> Counter[tuple[str, str]]:
    routes = document.get("routes")
    if not isinstance(routes, list):
        return Counter()
    return Counter(
        (raw.get("method"), raw.get("normalized_route"))
        for raw in routes
        if isinstance(raw, Mapping) and raw.get("disposition") == "unresolved"
    )


def _retirement_proof_valid(
    root: Path,
    ledger: RouteRootCauseLedger,
    entry: RouteRootCauseLedgerEntry,
    *,
    web_root: Path | None,
) -> bool:
    proof = entry.disposition_details.get("retirement_proof")
    if not isinstance(proof, Mapping) or set(proof) != {
        "kind", "rationale", "anchors", "final_sources"
    }:
        return False
    kind, rationale = proof.get("kind"), proof.get("rationale")
    anchors, final_sources = proof.get("anchors"), proof.get("final_sources")
    if (
        kind not in RETIREMENT_KINDS
        or not isinstance(rationale, str) or len(rationale.strip()) < 20
        or rationale.strip().lower() in {"reviewed", "retired", "removed"}
        or not isinstance(anchors, list) or not anchors
        or not all(_anchor_valid(root, anchor, web_root=web_root) for anchor in anchors)
        or not isinstance(final_sources, list) or not final_sources
    ):
        return False
    expected_by_source: dict[str, set[str]] = {}
    for occurrence in entry.occurrences:
        source, route = occurrence.get("source"), occurrence.get("raw_route")
        if not isinstance(source, str) or not isinstance(route, str):
            return False
        expected_by_source.setdefault(source, set()).add(route)
    actual_by_source: dict[str, set[str]] = {}
    for raw in final_sources:
        if not isinstance(raw, Mapping) or set(raw) != {
            "source_path", "sha256", "removed_raw_routes"
        }:
            return False
        source, routes = _safe_relative_path(raw.get("source_path")), raw.get("removed_raw_routes")
        if source is None or not _valid_hash(raw.get("sha256")) or not isinstance(routes, list):
            return False
        if not routes or not all(isinstance(route, str) and route for route in routes):
            return False
        actual_by_source[source] = set(routes)
        if web_root is not None:
            path = web_root.joinpath(*PurePosixPath(source).parts)
            try:
                blob, text = path.read_bytes(), path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                return False
            if hashlib.sha256(blob).hexdigest() != raw["sha256"] or any(route in text for route in routes):
                return False
    if actual_by_source != expected_by_source:
        return False
    evidence = entry.backend_evidence
    anchor_texts = [
        _anchor_text(root, anchor, web_root=web_root) or "" for anchor in anchors
    ]
    if kind == "http_410":
        return evidence.get("handler_status") == "registered" and any("410" in text for text in anchor_texts)
    if kind == "backend_route_retired":
        return evidence.get("handler_status") == "retired" and any(
            isinstance(anchor, Mapping) and anchor.get("repository") == "backend"
            for anchor in anchors
        )
    if kind == "sample_template_only":
        return all("/template/" in source for source in expected_by_source) and any(
            isinstance(anchor, Mapping) and anchor.get("repository") == "frontend_baseline"
            for anchor in anchors
        )
    if kind == "backend_route_absent":
        source = evidence.get("source_path")
        return evidence.get("handler_status") == "absent" and isinstance(source, str) and build_route_definition_evidence(root, source, entry.key) is None
    if web_root is None:
        return any(
            isinstance(anchor, Mapping)
            and anchor.get("repository") == "frontend_final"
            for anchor in anchors
        )
    return any("retir" in text.lower() or "停用" in text for text in anchor_texts)


def audit_route_root_cause_ledger(
    root: Path,
    ledger: RouteRootCauseLedger,
    *,
    web_root: Path | None = None,
) -> tuple[str, ...]:
    issues: list[str] = []
    if ledger.artifact_id != LEDGER_ARTIFACT_ID:
        issues.append("ledger_artifact_id_invalid:1")
    if (
        ledger.baseline_backend_revision != BASELINE_BACKEND_REVISION
        or ledger.baseline_inventory_path != BASELINE_INVENTORY_PATH
        or ledger.baseline_inventory_sha256 != BASELINE_INVENTORY_SHA256
        or ledger.baseline_frontend_revision != BASELINE_FRONTEND_REVISION
        or ledger.baseline_content_hash != BASELINE_CONTENT_HASH
        or ledger.baseline_unresolved_count != BASELINE_UNRESOLVED_COUNT
        or ledger.baseline_group_count != BASELINE_GROUP_COUNT
    ):
        issues.append("ledger_baseline_metadata_invalid:1")

    baseline_document, baseline_digest = _pinned_baseline(root)
    if baseline_document is None or baseline_digest != BASELINE_INVENTORY_SHA256:
        issues.append("ledger_pinned_baseline_unavailable:1")
        baseline_routes: list[Mapping[str, Any]] = []
    else:
        raw_routes = baseline_document.get("routes")
        baseline_routes = [
            raw for raw in raw_routes
            if isinstance(raw, Mapping) and raw.get("disposition") == "unresolved"
        ] if isinstance(raw_routes, list) else []

    keys = [entry.key for entry in ledger.entries]
    if len(keys) != len(set(keys)):
        issues.append(f"ledger_duplicate_keys:{len(keys) - len(set(keys))}")
    if len(keys) != CLASSIFIED_GROUP_COUNT:
        issues.append(f"ledger_classified_group_count:{len(keys)}")
    baseline_entries = [entry for entry in ledger.entries if entry.occurrence_scope == "baseline"]
    derived_entries = [entry for entry in ledger.entries if entry.occurrence_scope == "post_normalization"]
    if len(baseline_entries) != BASELINE_GROUP_COUNT:
        issues.append(f"ledger_baseline_group_count:{len(baseline_entries)}")
    if any(entry.occurrence_scope not in {"baseline", "post_normalization"} for entry in ledger.entries):
        issues.append("ledger_occurrence_scope_invalid:1")
    actual_baseline = [raw for entry in baseline_entries for raw in entry.occurrences if isinstance(raw, Mapping)]
    baseline_mismatches = _occurrence_mismatch_count(baseline_routes, actual_baseline)
    if baseline_mismatches:
        issues.append(f"ledger_baseline_occurrence_mismatch:{baseline_mismatches}")

    occurrence_ids: list[str] = []
    baseline_sources: dict[str, str] = {}
    verified_baseline_hashes: dict[str, str | None] = {}
    catalog = _catalog_index(root)
    entry_by_key = {entry.key: entry for entry in ledger.entries}
    for entry in ledger.entries:
        context = f"{entry.method}:{entry.normalized_route}"
        if (
            not isinstance(entry.method, str) or entry.method != entry.method.upper()
            or not isinstance(entry.normalized_route, str) or not entry.normalized_route.startswith("/api/")
            or not isinstance(entry.occurrence_count, int) or isinstance(entry.occurrence_count, bool)
            or entry.occurrence_count != len(entry.occurrences)
        ):
            issues.append(f"ledger_entry_invalid:{context}")
            continue
        if (
            not isinstance(entry.owner_domain, str) or not entry.owner_domain
            or not isinstance(entry.backend_evidence, Mapping)
            or not isinstance(entry.lifecycle_conclusion, str) or not entry.lifecycle_conclusion.strip()
            or entry.disposition not in DISPOSITIONS
            or not isinstance(entry.disposition_details, Mapping)
        ):
            issues.append(f"ledger_classification_invalid:{context}")
            continue
        for raw in entry.occurrences:
            source = raw.get("source") if isinstance(raw, Mapping) else None
            source_hash = raw.get("source_sha256") if isinstance(raw, Mapping) else None
            identity = raw.get("occurrence_id") if isinstance(raw, Mapping) else None
            if (
                not isinstance(raw, Mapping) or not isinstance(identity, str)
                or raw.get("method") != entry.method
                or raw.get("normalized_route") != entry.normalized_route
                or not isinstance(source, str) or not _valid_hash(source_hash)
            ):
                issues.append(f"ledger_occurrence_invalid:{context}")
                continue
            occurrence_ids.append(identity)
            if entry.occurrence_scope == "baseline":
                if source in baseline_sources and baseline_sources[source] != source_hash:
                    issues.append(f"ledger_source_hash_conflict:{source}")
                baseline_sources[source] = source_hash
                if web_root is not None:
                    if source not in verified_baseline_hashes:
                        blob = _git_blob(web_root, BASELINE_FRONTEND_REVISION, source)
                        verified_baseline_hashes[source] = (
                            hashlib.sha256(blob).hexdigest() if blob is not None else None
                        )
                    if verified_baseline_hashes[source] != source_hash:
                        issues.append(f"ledger_baseline_source_hash_invalid:{context}")
            elif web_root is not None:
                path = web_root.joinpath(*PurePosixPath(source).parts)
                try:
                    actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
                except OSError:
                    actual_hash = None
                if actual_hash != source_hash:
                    issues.append(f"ledger_post_normalization_source_hash_invalid:{context}")

        evidence = entry.backend_evidence
        source_path = _safe_relative_path(evidence.get("source_path"))
        handler_status = evidence.get("handler_status")
        route_definition = evidence.get("route_definition")
        anchors = evidence.get("anchors")
        if source_path is None or not root.joinpath(*PurePosixPath(source_path).parts).is_file():
            issues.append(f"ledger_handler_path_missing:{context}")
        if not isinstance(anchors, list) or not all(_anchor_valid(root, anchor, web_root=web_root) for anchor in anchors):
            issues.append(f"ledger_backend_anchor_invalid:{context}")
        if handler_status == "registered":
            actual_definition = build_route_definition_evidence(root, source_path, entry.key) if source_path is not None else None
            if actual_definition is None or route_definition != actual_definition:
                issues.append(f"ledger_handler_route_mismatch:{context}")
        elif handler_status not in {"absent", "retired", "not_applicable"}:
            issues.append(f"ledger_handler_status_invalid:{context}")
        elif route_definition is not None:
            issues.append(f"ledger_handler_route_mismatch:{context}")

        details = entry.disposition_details
        if entry.disposition == "existing_stable_capability":
            target = _target(details.get("target_capability"))
            if target is None or catalog.get(target) != ("stable", entry.owner_domain):
                issues.append(f"ledger_existing_target_invalid:{context}")
            if handler_status != "registered" or not anchors:
                issues.append(f"ledger_existing_anchor_missing:{context}")
        elif entry.disposition == "existing_capability_migration_required":
            target = _target(details.get("target_capability"))
            if (
                target is None or catalog.get(target) != ("stable", entry.owner_domain)
                or details.get("provider_equivalence") != "not_proven"
                or not isinstance(details.get("required_action"), str)
                or not details.get("required_action", "").strip()
            ):
                issues.append(f"ledger_migration_target_invalid:{context}")
        elif entry.disposition == "existing_capability_migrated":
            target = _target(details.get("target_capability"))
            equivalence = details.get("equivalence_evidence")
            if (
                target is None or catalog.get(target) != ("stable", entry.owner_domain)
                or details.get("provider_equivalence") != "proven"
                or not isinstance(details.get("request_transform"), str)
                or not details.get("request_transform", "").strip()
                or not isinstance(details.get("response_transform"), str)
                or not details.get("response_transform", "").strip()
                or not isinstance(equivalence, Mapping)
                or equivalence.get("proof_kind") != "provider_equivalent_adapter"
                or not isinstance(equivalence.get("provider_contract"), Mapping)
            ):
                issues.append(f"ledger_migrated_target_invalid:{context}")
        elif entry.disposition == "existing_capability_reclassified":
            target = _target(details.get("candidate_target_capability"))
            legacy_contract = details.get("legacy_contract")
            candidate_contracts = details.get("candidate_contracts")
            contract_mismatch = details.get("contract_mismatch")
            if (
                target is None or catalog.get(target) != ("stable", entry.owner_domain)
                or details.get("reason_code") not in {
                    "adapter_side_effect_missing", "contract_shape_mismatch", "outcome_mismatch",
                    "projection_mismatch", "provider_equivalence_missing", "state_model_mismatch",
                }
                or details.get("followup") not in {
                    "atomic_capability_review", "provider_adapter_review", "bff_review",
                }
                or not isinstance(details.get("finding"), str)
                or len(details.get("finding", "").strip()) < 20
                or not isinstance(legacy_contract, Mapping)
                or not isinstance(candidate_contracts, list) or not candidate_contracts
                or not isinstance(contract_mismatch, Mapping)
                or set(contract_mismatch) != {"input", "output", "side_effects"}
            ):
                issues.append(f"ledger_reclassification_invalid:{context}")
        elif entry.disposition in {"truthful_bff_required", "truthful_bff_registered"}:
            constituents = details.get("constituent_capabilities")
            parsed = [_target(value) for value in constituents] if isinstance(constituents, list) else []
            if len(parsed) < 2 or len(set(parsed)) < 2:
                issues.append(f"ledger_bff_constituent_count_invalid:{context}")
            if any(value is None or catalog.get(value, (None,))[0] != "stable" for value in parsed):
                issues.append(f"ledger_bff_constituent_invalid:{context}")
            aggregation = details.get("aggregation_evidence")
            valid_aggregation = (
                isinstance(aggregation, Mapping)
                and aggregation.get("kind") == "multi_result_merge"
                and isinstance(aggregation.get("anchors"), list) and bool(aggregation.get("anchors"))
                and all(_anchor_valid(root, anchor) for anchor in aggregation.get("anchors", []))
                and isinstance(aggregation.get("combined_outcomes"), list)
                and len(aggregation.get("combined_outcomes", [])) >= 2
                and handler_status == "registered"
            )
            if not valid_aggregation:
                issues.append(f"ledger_bff_aggregation_invalid:{context}")
        elif entry.disposition in {"conditional_dispatch_required", "conditional_dispatch_migrated", "conditional_dispatch_partially_migrated"}:
            branches = details.get("branch_capabilities")
            parsed = [_target(value) for value in branches] if isinstance(branches, list) else []
            dispatch = details.get("dispatch_evidence")
            if (
                len(parsed) < (1 if entry.disposition == "conditional_dispatch_partially_migrated" else 2)
                or any(value is None or catalog.get(value, (None,))[0] != "stable" for value in parsed)
                or not isinstance(details.get("selector"), str) or not details.get("selector", "").strip()
                or not isinstance(dispatch, Mapping) or dispatch.get("aggregation") is not False
                or not isinstance(dispatch.get("anchors"), list) or not dispatch.get("anchors")
                or not all(_anchor_valid(root, anchor) for anchor in dispatch.get("anchors", []))
                or handler_status != "registered"
            ):
                issues.append(f"ledger_conditional_dispatch_invalid:{context}")
            if entry.disposition == "conditional_dispatch_partially_migrated":
                rest = details.get("reclassified_rest_branches")
                if not isinstance(rest, list) or not rest or any(
                    not isinstance(item, Mapping)
                    or set(item) != {"selector_value", "transport"}
                    or not all(isinstance(item.get(field), str) and item[field] for field in item)
                    for item in rest
                ):
                    issues.append(f"ledger_conditional_rest_reclassification_invalid:{context}")
        elif entry.disposition == "new_atomic_capability_required":
            required = {
                "proposed_owner_domain", "atomic_outcome", "provider_or_handler",
                "bounded_input", "bounded_output", "no_stable_target_reason",
            }
            if set(details) != required or any(
                not isinstance(details.get(field), str) or not details[field].strip()
                for field in required
            ) or details.get("proposed_owner_domain") != entry.owner_domain:
                issues.append(f"ledger_atomic_proposal_invalid:{context}")
        elif entry.disposition == "frontend_retire":
            if (
                details.get("removed_in_frontend_revision") != ledger.final_evidence.get("frontend_revision")
                or not _retirement_proof_valid(root, ledger, entry, web_root=web_root)
            ):
                issues.append(f"ledger_retirement_proof_invalid:{context}")
        elif entry.disposition == "frontend_route_normalize":
            finite = details.get("finite_routes")
            if (
                set(details) != {"finite_routes", "runtime_target_preserved", "normalization_basis"}
                or not isinstance(finite, list) or not finite
                or not all(isinstance(value, str) and re.fullmatch(r"[A-Z]+ /api/.+", value) for value in finite)
                or details.get("runtime_target_preserved") is not True
            ):
                issues.append(f"ledger_normalization_invalid:{context}")
        elif entry.disposition == "operations_candidate":
            if (
                entry.key != ("GET", "/api/file-store/config")
                or entry.owner_domain != "platform-runtime"
                or source_path != "backend/routers/file_store.py"
                or handler_status != "registered"
                or details.get("approval_status") != "not_approved"
                or details.get("approval_needed") is not True
                or details.get("non_business_operation") != "runtime storage configuration read"
            ):
                issues.append(f"ledger_operations_candidate_invalid:{context}")
        elif entry.disposition == "file_store_capability_migrated":
            target = _target(details.get("target_capability"))
            if (
                entry.key != ("GET", "/api/file-store/config")
                or target is None or catalog.get(target) != ("stable", "base")
                or details.get("public_projection") != "secret_filtered_closed_schema"
                or details.get("manifest") != "docs/governance/special-web-residual-contracts.json"
            ):
                issues.append(f"ledger_file_store_capability_invalid:{context}")

    if len(occurrence_ids) != CLASSIFIED_OCCURRENCE_COUNT:
        issues.append(f"ledger_classified_occurrence_count:{len(occurrence_ids)}")
    duplicate_occurrences = len(occurrence_ids) - len(set(occurrence_ids))
    if duplicate_occurrences:
        issues.append(f"ledger_duplicate_occurrences:{duplicate_occurrences}")
    if dict(sorted(baseline_sources.items())) != dict(sorted(ledger.baseline_source_hashes.items())):
        issues.append("ledger_source_hash_index_mismatch:1")

    final_document = _load_json(root / BASELINE_INVENTORY_PATH)
    expected_final = ledger.final_evidence
    for field in ("frontend_revision", "content_hash"):
        if final_document.get(field) != expected_final.get(field):
            issues.append(f"ledger_final_{field}_mismatch:1")
    final_counts = final_document.get("counts", {})
    if not isinstance(final_counts, Mapping) or final_counts.get("unresolved") != expected_final.get("unresolved_count"):
        issues.append("ledger_final_unresolved_count_mismatch:1")
    actual_groups = _final_groups(final_document)
    for entry in ledger.entries:
        if entry.disposition in {
            "existing_capability_migrated", "conditional_dispatch_migrated",
            "file_store_capability_migrated",
        } and entry.key in actual_groups:
            issues.append(f"ledger_migrated_frontend_call_remains:{entry.method}:{entry.normalized_route}")
    expected_groups = Counter()
    for raw in ledger.final_unresolved_groups:
        if not isinstance(raw, Mapping) or set(raw) != {
            "method", "normalized_route", "occurrence_count", "disposition"
        }:
            issues.append("ledger_final_group_invalid:1")
            continue
        key = (raw.get("method"), raw.get("normalized_route"))
        expected_groups[key] = raw.get("occurrence_count")
        entry = entry_by_key.get(key)
        if entry is None or raw.get("disposition") != entry.disposition:
            issues.append("ledger_final_group_classification_mismatch:1")
    if actual_groups != expected_groups:
        issues.append("ledger_final_reconciliation_mismatch:1")
    if len(actual_groups) != expected_final.get("unresolved_group_count"):
        issues.append("ledger_final_group_count_mismatch:1")

    final_routes = final_document.get("routes")
    final_unresolved = [
        raw for raw in final_routes
        if isinstance(raw, Mapping) and raw.get("disposition") == "unresolved"
    ] if isinstance(final_routes, list) else []
    baseline_keys = {(raw.get("method"), raw.get("normalized_route")) for raw in baseline_routes}
    expected_derived = [
        raw for raw in final_unresolved
        if (raw.get("method"), raw.get("normalized_route")) not in baseline_keys
    ]
    expected_derived_keys = {
        (raw.get("method"), raw.get("normalized_route")) for raw in expected_derived
    }
    actual_derived = [
        raw
        for entry in derived_entries
        if entry.key in expected_derived_keys
        for raw in entry.occurrences
        if isinstance(raw, Mapping)
    ]
    derived_mismatches = _occurrence_mismatch_count(expected_derived, actual_derived)
    if derived_mismatches:
        issues.append(f"ledger_post_normalization_occurrence_mismatch:{derived_mismatches}")
    return tuple(sorted(set(issues)))


__all__ = [
    "BASELINE_BACKEND_REVISION", "BASELINE_CONTENT_HASH",
    "BASELINE_FRONTEND_REVISION", "BASELINE_GROUP_COUNT",
    "BASELINE_INVENTORY_PATH", "BASELINE_INVENTORY_SHA256",
    "BASELINE_UNRESOLVED_COUNT", "CLASSIFIED_GROUP_COUNT",
    "CLASSIFIED_OCCURRENCE_COUNT", "RouteRootCauseLedger",
    "RouteRootCauseLedgerConfigurationError", "RouteRootCauseLedgerEntry",
    "audit_route_root_cause_ledger", "build_route_definition_evidence",
    "load_route_root_cause_ledger",
]
