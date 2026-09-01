"""Single release gate combining completion, Web path, and catalog audits."""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re

from .atomicity import AtomicityAudit, audit_generic_operations, load_atomicity_dispositions
from .catalog_targets import CatalogTargetIndex
from .orchestration_audit import OrchestrationAudit, audit_orchestration_registry
from .catalog_audit import CatalogAuditReport, audit_catalog
from .completion import CompletionReport, evaluate_completion


class BusinessGovernanceConfigurationError(RuntimeError):
    """Raised when the immutable cutover baseline is missing or invalid."""


@dataclass(frozen=True)
class LegacyBusinessGovernanceBaseline:
    source_revision: str
    catalog_release_id: str
    catalog_hash: str
    capabilities: Mapping[str, str]
    baseline_hash: str


@dataclass(frozen=True)
class BusinessGateCapability:
    capability_key: str
    change_kind: str
    capability_version_gid: str = ""
    definition_hash: str = ""
    approved_definition_hash: str | None = None
    human_approved: bool = False
    runtime_verified: bool = False
    deterministic_blockers: tuple[str, ...] = ()


@dataclass(frozen=True)
class CapabilityGovernanceResult:
    capability_key: str
    capability_version_gid: str
    definition_hash: str
    approved_definition_hash: str | None
    change_kind: str
    governance_status: str
    machine_passed: bool
    human_approved: bool
    runtime_verified: bool
    blockers: tuple[str, ...]

    def serialized(self) -> dict[str, object]:
        return {
            "capability_key": self.capability_key,
            "capability_version_gid": self.capability_version_gid,
            "definition_hash": self.definition_hash,
            "approved_definition_hash": self.approved_definition_hash,
            "change_kind": self.change_kind,
            "governance_status": self.governance_status,
            "machine_passed": self.machine_passed,
            "human_approved": self.human_approved,
            "runtime_verified": self.runtime_verified,
            "blockers": list(self.blockers),
        }


@dataclass(frozen=True)
class BusinessGateResult:
    status: str
    machine_passed: bool
    human_approved: bool
    runtime_verified: bool
    legacy_pending_review_count: int
    blockers: tuple[str, ...]
    capabilities: tuple[CapabilityGovernanceResult, ...]

    def serialized(self) -> dict[str, object]:
        return {
            "status": self.status,
            "machine_passed": self.machine_passed,
            "human_approved": self.human_approved,
            "runtime_verified": self.runtime_verified,
            "legacy_pending_review_count": self.legacy_pending_review_count,
            "blockers": list(self.blockers),
            "capabilities": [item.serialized() for item in self.capabilities],
        }


def classify_change(
    capability_key: str,
    current_hash: str,
    previous_hash: str | None,
    legacy_baseline: Mapping[str, str],
) -> str:
    reference = previous_hash or legacy_baseline.get(capability_key)
    if reference is None:
        return "new"
    return "unchanged_legacy" if current_hash == reference else "material_change"


def evaluate_business_governance_gate(
    capabilities: Iterable[BusinessGateCapability],
) -> BusinessGateResult:
    results: list[CapabilityGovernanceResult] = []
    aggregate_blockers: set[str] = set()
    for capability in sorted(capabilities, key=lambda item: item.capability_key):
        if capability.change_kind not in {"new", "material_change", "unchanged_legacy"}:
            raise ValueError("business_governance_change_kind_invalid")
        blockers = set(str(value) for value in capability.deterministic_blockers if str(value))
        machine_passed = not blockers
        human_approved = bool(
            capability.human_approved
            and capability.approved_definition_hash == capability.definition_hash
        )
        if capability.change_kind in {"new", "material_change"} and not human_approved:
            blockers.add(f"business_definition_approval_missing:{capability.capability_key}")
        if blockers:
            governance_status = "blocked"
        elif capability.change_kind == "unchanged_legacy" and not human_approved:
            governance_status = "legacy_pending_review"
        else:
            governance_status = "passed"
        ordered_blockers = tuple(sorted(blockers))
        aggregate_blockers.update(ordered_blockers)
        results.append(CapabilityGovernanceResult(
            capability_key=capability.capability_key,
            capability_version_gid=capability.capability_version_gid,
            definition_hash=capability.definition_hash,
            approved_definition_hash=(capability.definition_hash if human_approved else None),
            change_kind=capability.change_kind,
            governance_status=governance_status,
            machine_passed=machine_passed,
            human_approved=human_approved,
            runtime_verified=bool(capability.runtime_verified),
            blockers=ordered_blockers,
        ))
    rows = tuple(results)
    legacy_pending = sum(item.governance_status == "legacy_pending_review" for item in rows)
    status = "blocked" if aggregate_blockers else (
        "passed_with_legacy_backlog" if legacy_pending else "passed"
    )
    return BusinessGateResult(
        status=status,
        machine_passed=all(item.machine_passed for item in rows),
        human_approved=bool(rows) and all(item.human_approved for item in rows),
        runtime_verified=bool(rows) and all(item.runtime_verified for item in rows),
        legacy_pending_review_count=legacy_pending,
        blockers=tuple(sorted(aggregate_blockers)),
        capabilities=rows,
    )


_CAPABILITY_KEY = re.compile(r"[a-z0-9][a-z0-9_.-]*@[1-9][0-9]*")
_CAPABILITY_VERSION_GID = re.compile(r"(?:cv2_[0-9a-f]{24}|[1-9][0-9]*)")
_SHA256 = re.compile(r"sha256:[0-9a-f]{64}")


def parse_business_governance_result(value: object) -> BusinessGateResult:
    """Validate and rederive one governance result at every trust boundary."""
    document = value.serialized() if isinstance(value, BusinessGateResult) else (
        dict(value) if isinstance(value, Mapping) else None
    )
    required = {
        "status", "machine_passed", "human_approved", "runtime_verified",
        "legacy_pending_review_count", "blockers", "capabilities",
    }
    if not isinstance(document, dict) or set(document) != required:
        raise BusinessGovernanceConfigurationError("business_governance_invalid")
    rows = document.get("capabilities")
    if not isinstance(rows, (list, tuple)) or not rows:
        raise BusinessGovernanceConfigurationError("business_governance_invalid")
    capabilities: list[BusinessGateCapability] = []
    seen: set[tuple[str, str]] = set()
    row_keys = {
        "capability_key", "capability_version_gid", "definition_hash",
        "approved_definition_hash", "change_kind", "governance_status",
        "machine_passed", "human_approved", "runtime_verified", "blockers",
    }
    for raw in rows:
        if not isinstance(raw, Mapping) or set(raw) != row_keys:
            raise BusinessGovernanceConfigurationError("business_governance_invalid")
        row = dict(raw)
        capability_key = row.get("capability_key")
        version_gid = row.get("capability_version_gid")
        definition_hash = row.get("definition_hash")
        approved_hash = row.get("approved_definition_hash")
        blockers = row.get("blockers")
        if (
            not isinstance(capability_key, str) or _CAPABILITY_KEY.fullmatch(capability_key) is None
            or not isinstance(version_gid, str) or _CAPABILITY_VERSION_GID.fullmatch(version_gid) is None
            or not isinstance(definition_hash, str) or _SHA256.fullmatch(definition_hash) is None
            or approved_hash is not None and (
                not isinstance(approved_hash, str) or _SHA256.fullmatch(approved_hash) is None
            )
            or type(row.get("machine_passed")) is not bool
            or type(row.get("human_approved")) is not bool
            or type(row.get("runtime_verified")) is not bool
            or not isinstance(blockers, (list, tuple))
            or any(not isinstance(item, str) or not item for item in blockers)
            or len(blockers) != len(set(blockers))
        ):
            raise BusinessGovernanceConfigurationError("business_governance_invalid")
        identity = (capability_key, version_gid)
        if identity in seen:
            raise BusinessGovernanceConfigurationError("business_governance_invalid")
        seen.add(identity)
        approval_blocker = f"business_definition_approval_missing:{capability_key}"
        deterministic = tuple(sorted(set(blockers) - {approval_blocker}))
        human_approved = approved_hash == definition_hash
        if bool(row["human_approved"]) != human_approved:
            raise BusinessGovernanceConfigurationError("business_governance_invalid")
        candidate = BusinessGateCapability(
            capability_key=capability_key,
            capability_version_gid=version_gid,
            definition_hash=definition_hash,
            approved_definition_hash=approved_hash,
            change_kind=str(row.get("change_kind")),
            human_approved=human_approved,
            runtime_verified=bool(row["runtime_verified"]),
            deterministic_blockers=deterministic,
        )
        derived = evaluate_business_governance_gate((candidate,)).capabilities[0]
        if derived.serialized() != row:
            raise BusinessGovernanceConfigurationError("business_governance_invalid")
        capabilities.append(candidate)
    derived = evaluate_business_governance_gate(capabilities)
    if derived.serialized() != document:
        raise BusinessGovernanceConfigurationError("business_governance_invalid")
    return derived


def load_business_approval_artifact(
    path: Path, *, catalog_release_id: str,
) -> dict[tuple[str, str], str]:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BusinessGovernanceConfigurationError("business_approval_artifact_invalid") from exc
    if (
        not isinstance(document, dict)
        or set(document) != {"schema_version", "catalog_release_id", "approvals"}
        or document.get("schema_version") != 1
        or document.get("catalog_release_id") != catalog_release_id
    ):
        code = (
            "business_approval_catalog_mismatch"
            if isinstance(document, dict) and document.get("catalog_release_id") != catalog_release_id
            else "business_approval_artifact_invalid"
        )
        raise BusinessGovernanceConfigurationError(code)
    approvals: dict[tuple[str, str], str] = {}
    for raw in document.get("approvals", ()):
        if not isinstance(raw, Mapping) or set(raw) != {
            "capability_key", "capability_version_gid", "definition_hash", "decision",
        }:
            raise BusinessGovernanceConfigurationError("business_approval_artifact_invalid")
        key, gid, digest = raw["capability_key"], raw["capability_version_gid"], raw["definition_hash"]
        if (
            not isinstance(key, str) or _CAPABILITY_KEY.fullmatch(key) is None
            or not isinstance(gid, str) or _CAPABILITY_VERSION_GID.fullmatch(gid) is None
            or not isinstance(digest, str) or _SHA256.fullmatch(digest) is None
            or raw["decision"] != "approved"
            or (gid, digest) in approvals
        ):
            raise BusinessGovernanceConfigurationError("business_approval_artifact_invalid")
        approvals[(gid, digest)] = digest
    return approvals


def _baseline_payload(document: Mapping[str, object]) -> dict[str, object]:
    return {
        "schema_version": document.get("schema_version"),
        "source_revision": document.get("source_revision"),
        "catalog_release_id": document.get("catalog_release_id"),
        "catalog_hash": document.get("catalog_hash"),
        "capabilities": document.get("capabilities"),
    }


def _baseline_digest(document: Mapping[str, object]) -> str:
    canonical = json.dumps(
        _baseline_payload(document), ensure_ascii=True, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def load_legacy_baseline(
    path: Path, *, catalog_path: Path | None = None,
) -> LegacyBusinessGovernanceBaseline:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BusinessGovernanceConfigurationError("legacy_baseline_invalid") from exc
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise BusinessGovernanceConfigurationError("legacy_baseline_invalid")
    capabilities = document.get("capabilities")
    required = ("source_revision", "catalog_release_id", "catalog_hash", "baseline_hash")
    if not isinstance(capabilities, dict) or any(not str(document.get(key, "")).strip() for key in required):
        raise BusinessGovernanceConfigurationError("legacy_baseline_invalid")
    if document["baseline_hash"] != _baseline_digest(document):
        raise BusinessGovernanceConfigurationError("legacy_baseline_hash_invalid")
    if any(
        not isinstance(key, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", str(value))
        for key, value in capabilities.items()
    ):
        raise BusinessGovernanceConfigurationError("legacy_baseline_invalid")
    baseline = LegacyBusinessGovernanceBaseline(
        source_revision=str(document["source_revision"]),
        catalog_release_id=str(document["catalog_release_id"]),
        catalog_hash=str(document["catalog_hash"]),
        capabilities=dict(sorted((str(key), str(value)) for key, value in capabilities.items())),
        baseline_hash=str(document["baseline_hash"]),
    )
    if catalog_path is not None:
        try:
            catalog = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
            from .catalog import load_catalog_release
            load_catalog_release(catalog)
        except (OSError, json.JSONDecodeError) as exc:
            raise BusinessGovernanceConfigurationError("legacy_baseline_catalog_invalid") from exc
        except Exception as exc:
            raise BusinessGovernanceConfigurationError("legacy_baseline_catalog_invalid") from exc
        expected: dict[str, str] = {}
        for item in catalog.get("descriptors", catalog.get("capabilities", ())):
            key = f"{item.get('id')}@{item.get('major_version')}"
            digest = str(item.get("business_definition_hash", ""))
            if _CAPABILITY_KEY.fullmatch(key) is None or _SHA256.fullmatch(digest) is None or key in expected:
                raise BusinessGovernanceConfigurationError("legacy_baseline_catalog_invalid")
            expected[key] = digest
        if (
            baseline.catalog_release_id != str(catalog.get("release_id", ""))
            or baseline.catalog_hash != str(catalog.get("catalog_hash", ""))
            or dict(baseline.capabilities) != dict(sorted(expected.items()))
        ):
            raise BusinessGovernanceConfigurationError("legacy_baseline_catalog_mismatch")
    return baseline


def create_legacy_baseline(
    catalog_path: Path, baseline_path: Path, *, source_revision: str,
) -> LegacyBusinessGovernanceBaseline:
    destination = Path(baseline_path)
    if destination.exists():
        raise BusinessGovernanceConfigurationError("legacy_baseline_already_exists")
    try:
        catalog = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
        from .catalog import load_catalog_release
        load_catalog_release(catalog)
    except (OSError, json.JSONDecodeError) as exc:
        raise BusinessGovernanceConfigurationError("legacy_baseline_catalog_invalid") from exc
    except Exception as exc:
        raise BusinessGovernanceConfigurationError("legacy_baseline_catalog_invalid") from exc
    capabilities: dict[str, str] = {}
    for item in catalog.get("descriptors", catalog.get("capabilities", ())):
        key = f"{item.get('id')}@{item.get('major_version')}"
        definition_hash = str(item.get("business_definition_hash", ""))
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", definition_hash):
            raise BusinessGovernanceConfigurationError("legacy_baseline_catalog_invalid")
        capabilities[key] = definition_hash
    document: dict[str, object] = {
        "schema_version": 1,
        "source_revision": str(source_revision).strip(),
        "catalog_release_id": str(catalog.get("release_id", "")).strip(),
        "catalog_hash": str(catalog.get("catalog_hash", "")).strip(),
        "capabilities": dict(sorted(capabilities.items())),
    }
    if not document["source_revision"] or not document["catalog_release_id"] or not document["catalog_hash"]:
        raise BusinessGovernanceConfigurationError("legacy_baseline_catalog_invalid")
    document["baseline_hash"] = _baseline_digest(document)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return load_legacy_baseline(destination, catalog_path=catalog_path)


def evaluate_catalog_business_governance(
    business_catalog: Mapping[str, object],
    legacy_baseline: Mapping[str, str],
    *,
    previous_hashes: Mapping[str, str] | None = None,
    business_review_lookup: Mapping[tuple[str, str], object] | Callable[[str, str], object] | None = None,
    runtime_verification: Mapping[str, bool] | None = None,
    deterministic_blockers: Mapping[str, Iterable[str]] | None = None,
) -> BusinessGateResult:
    previous = previous_hashes or {}
    runtime = runtime_verification or {}
    blocker_map = deterministic_blockers or {}
    governed = tuple(
        item for item in business_catalog.get("descriptors", business_catalog.get("capabilities", ()))
        if isinstance(item, Mapping) and "business_definition_hash" in item
    )

    def approved_hash(version_gid: str, definition_hash: str) -> str | None:
        value = (
            business_review_lookup(version_gid, definition_hash)
            if callable(business_review_lookup)
            else business_review_lookup.get((version_gid, definition_hash))
            if business_review_lookup is not None
            else None
        )
        if value is True:
            return definition_hash
        if isinstance(value, str) and value == definition_hash:
            return definition_hash
        return None

    capabilities: list[BusinessGateCapability] = []
    for item in governed:
        key = f"{item.get('id')}@{item.get('major_version')}"
        version_gid = str(item.get("capability_version_gid", ""))
        definition_hash = str(item.get("business_definition_hash", ""))
        if (
            _CAPABILITY_KEY.fullmatch(key) is None
            or _CAPABILITY_VERSION_GID.fullmatch(version_gid) is None
            or _SHA256.fullmatch(definition_hash) is None
        ):
            raise BusinessGovernanceConfigurationError("business_catalog_invalid")
        approval = approved_hash(version_gid, definition_hash)
        capabilities.append(BusinessGateCapability(
            capability_key=key,
            capability_version_gid=version_gid,
            definition_hash=definition_hash,
            approved_definition_hash=approval,
            change_kind=classify_change(key, definition_hash, previous.get(key), legacy_baseline),
            human_approved=approval == definition_hash,
            runtime_verified=bool(runtime.get(key, False)),
            deterministic_blockers=tuple(blocker_map.get(key, ())),
        ))
    return evaluate_business_governance_gate(capabilities)


@dataclass(frozen=True)
class ReleaseGateReport:
    completion: CompletionReport
    audit: CatalogAuditReport
    atomicity: AtomicityAudit | None = None
    orchestration: tuple[OrchestrationAudit, ...] = ()
    business_governance: BusinessGateResult = field(
        default_factory=lambda: evaluate_business_governance_gate(())
    )

    @property
    def passed(self) -> bool:
        required_fields_complete = all(
            value == 0 for value in self.audit.required_field_missing_counts.values()
        )
        return (
            self.completion.complete
            and self.completion.web_consumer_bypasses == 0
            and self.audit.open_arguments_count == 0
            and self.audit.default_all_exposure_count == 0
            and required_fields_complete
            and self.audit.invalid_error_schema_count == 0
            and self.audit.test_evidence_not_run_count == 0
            and self.audit.invalid_test_ref_count == 0
            and self.atomicity is not None
            and self.atomicity.passed
            and len(self.orchestration) == 3
            and all(item.passed for item in self.orchestration)
            and self.business_governance.status != "blocked"
        )

    def serialized(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "completion": self.completion.serialized(),
            "catalog_audit": self.audit.serialized(),
            "atomicity": (
                {
                    "passed": self.atomicity.passed,
                    "generic_ids": list(self.atomicity.generic_ids),
                    "unclassified_ids": list(self.atomicity.unclassified_ids),
                    "invalid_ids": list(self.atomicity.invalid_ids),
                    "expired_ids": list(self.atomicity.expired_ids),
                    "missing_replacement_ids": list(self.atomicity.missing_replacement_ids),
                }
                if self.atomicity is not None
                else None
            ),
            "orchestration": [item.serialized() for item in self.orchestration],
            "business_governance": self.business_governance.serialized(),
        }


def evaluate_release_gate(
    root: Path,
    *,
    web_root: Path,
    catalog_path: Path | None = None,
    atomicity_path: Path | None = None,
    legacy_baseline_path: Path | None = None,
    business_catalog_path: Path | None = None,
    previous_hashes: Mapping[str, str] | None = None,
    business_review_lookup: Mapping[tuple[str, str], object] | Callable[[str, str], object] | None = None,
    runtime_verification: Mapping[str, bool] | None = None,
    deterministic_blockers: Mapping[str, Iterable[str]] | None = None,
) -> ReleaseGateReport:
    resolved_catalog = catalog_path or root / "docs/capabilities/catalog.v2.json"
    resolved_atomicity = atomicity_path or root / "docs/governance/capability-atomicity-dispositions.json"
    catalog = json.loads(resolved_catalog.read_text(encoding="utf-8"))
    resolved_business_catalog = business_catalog_path or (
        catalog_path if catalog_path is not None
        else root / "docs/governance/capability-catalog-release.json"
    )
    try:
        business_catalog = json.loads(resolved_business_catalog.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BusinessGovernanceConfigurationError("business_catalog_invalid") from exc
    has_governed = any(
        isinstance(item, Mapping) and "business_definition_hash" in item
        for item in business_catalog.get("descriptors", business_catalog.get("capabilities", ()))
    )
    baseline = load_legacy_baseline(
        legacy_baseline_path or root / "docs/governance/capability-business-governance-legacy-baseline.json",
        catalog_path=resolved_business_catalog,
    ) if has_governed else LegacyBusinessGovernanceBaseline("", "", "", {}, "")
    business_governance = evaluate_catalog_business_governance(
        business_catalog,
        baseline.capabilities,
        previous_hashes=previous_hashes,
        business_review_lookup=business_review_lookup,
        runtime_verification=runtime_verification,
        deterministic_blockers=deterministic_blockers,
    )
    dispositions = load_atomicity_dispositions(resolved_atomicity)
    catalog_index = CatalogTargetIndex.from_catalog(
        catalog,
        replacements={
            (item.capability_id, item.major_version): item.replacement_capabilities[0]
            for item in dispositions.dispositions
            if item.replacement_capabilities
        },
    )
    orchestration = tuple(
        audit_orchestration_registry(root / "docs/governance" / name, catalog_index)
        for name in ("task_tool_registry.json", "bff_capability_registry.json", "business_capability_ledger.json")
    )
    return ReleaseGateReport(
        completion=evaluate_completion(root, mode="strict", web_root=web_root),
        audit=audit_catalog(resolved_catalog, source_root=root),
        atomicity=audit_generic_operations(catalog, dispositions),
        orchestration=orchestration,
        business_governance=business_governance,
    )


__all__ = [
    "BusinessGateCapability", "BusinessGateResult",
    "BusinessGovernanceConfigurationError", "CapabilityGovernanceResult",
    "LegacyBusinessGovernanceBaseline", "ReleaseGateReport", "classify_change",
    "create_legacy_baseline", "evaluate_business_governance_gate",
    "evaluate_catalog_business_governance", "evaluate_release_gate",
    "load_business_approval_artifact", "load_legacy_baseline",
    "parse_business_governance_result",
]
