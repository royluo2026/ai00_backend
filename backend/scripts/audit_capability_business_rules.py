"""Generate the read-only seven-layer Capability business baseline."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
from itertools import count
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.capability_governance_test.business_audit import collect_business_audit
from backend.capability_governance_test.business_relations import analyze_relationships
from backend.capability_governance_test.config import GovernanceSettings
from backend.capability_governance_test.scanner import GovernanceScanner
from backend.capability_governance_test.service import CapabilityGovernanceService
from backend.capability_governance_test.store import MemoryGovernanceStore
from backend.capability_v2.catalog import load_catalog_release
from backend.capability_v2.domain_manifest import load_domain_manifests
from backend.capability_v2.release_gate import evaluate_catalog_business_governance, load_legacy_baseline


PRODUCT_CATALOG = REPOSITORY_ROOT / "docs/governance/capability-catalog-release.json"
EXTENSION_CATALOG = REPOSITORY_ROOT / "docs/governance/test-extension/capability-governance-catalog-release.json"
OFFICIAL_DOMAINS = REPOSITORY_ROOT / "backend/capability_v2/official_domains.json"
ACCEPTANCE_MANIFEST = REPOSITORY_ROOT / "backend/tests/acceptance/fixtures/case-manifest.json"
LEGACY_BASELINE = REPOSITORY_ROOT / "docs/governance/capability-business-governance-legacy-baseline.json"
DEFAULT_WEB_ROOT = Path(r"E:/Projects/ai00/workmanship-web")
OFFLINE_INTEGRATION_FACTORY = "backend.tests.support.integration_catalog_factory:build"


@dataclass(frozen=True)
class _InputProvenance:
    revision: str
    input_fingerprint: str
    input_paths: tuple[str, ...]


def _git_revision(root: Path) -> str:
    try:
        revision = subprocess.run(
            ("git", "rev-parse", "HEAD"), cwd=root, check=True, capture_output=True, text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("business_audit_revision_unavailable") from exc
    if len(revision) != 40 or any(character not in "0123456789abcdef" for character in revision):
        raise RuntimeError("business_audit_revision_invalid")
    return revision


def _under_roots(path: str, roots: tuple[str, ...]) -> bool:
    normalized = path.replace("\\", "/").strip("/")
    return any(normalized == root.strip("/") or normalized.startswith(root.strip("/") + "/") for root in roots)


def _status_paths(root: Path, pathspecs: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    try:
        result = subprocess.run(
            ("git", "status", "--porcelain=v1", "-z", "--untracked-files=all", "--", *(pathspecs or (".",))),
            cwd=root, check=True, capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("business_audit_revision_unavailable") from exc
    tokens = result.stdout.decode("utf-8", errors="surrogateescape").split("\0")
    rows: list[tuple[str, str]] = []
    index = 0
    while index < len(tokens):
        raw = tokens[index]
        index += 1
        if not raw:
            continue
        status, path = raw[:2], raw[3:]
        rows.append((status, path))
        if "R" in status or "C" in status:
            if index < len(tokens) and tokens[index]:
                rows.append((status, tokens[index]))
                index += 1
    return tuple(rows)


def _tracked_paths(root: Path) -> tuple[str, ...]:
    try:
        result = subprocess.run(("git", "ls-files", "-z"), cwd=root, check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("business_audit_revision_unavailable") from exc
    return tuple(sorted(
        value for value in result.stdout.decode("utf-8", errors="surrogateescape").split("\0") if value
    ))


def _capture_provenance(
    root: Path, *, source_roots: tuple[str, ...] = (), input_paths: tuple[str, ...] = (),
    all_tracked: bool = False,
) -> _InputProvenance:
    revision = _git_revision(root)
    exact = tuple(sorted({path.replace("\\", "/") for path in input_paths}))
    tracked = _tracked_paths(root)
    fingerprint_paths = tracked if all_tracked else exact
    if not all_tracked and any(path not in set(tracked) for path in exact):
        raise RuntimeError("business_audit_relevant_tree_dirty")
    external_exact = tuple(path for path in exact if not _under_roots(path, source_roots))
    pathspecs = (".",) if all_tracked else tuple(sorted(set(source_roots) | set(external_exact)))
    for status, path in _status_paths(root, pathspecs):
        source_candidate = (
            _under_roots(path, source_roots)
            and GovernanceScanner.is_source_candidate_path(path)
            and (
                status != "??"
                or GovernanceScanner.is_source_input_file(root / Path(path), root)
            )
        )
        relevant = (
            (all_tracked and status != "??")
            or path.replace("\\", "/") in exact
            or source_candidate
        )
        if relevant:
            raise RuntimeError("business_audit_relevant_tree_dirty")
    digest = hashlib.sha256()
    for relative in fingerprint_paths:
        path = root / Path(relative)
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise RuntimeError("business_audit_input_unavailable") from exc
        digest.update(relative.encode("utf-8", errors="surrogateescape"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(content).digest())
    return _InputProvenance(
        revision, "sha256:" + digest.hexdigest(), tuple(fingerprint_paths),
    )


def _revision(root: Path, *, relevant_paths: tuple[str, ...] = (".",)) -> str:
    return _capture_provenance(root, source_roots=relevant_paths).revision


def _stable_scan(scan, backend_probe, web_probe):
    backend_before = backend_probe()
    web_before = web_probe()
    document = scan(backend_before.revision)
    backend_after = backend_probe()
    web_after = web_probe()
    if backend_before != backend_after or web_before != web_after:
        raise RuntimeError("business_audit_inputs_changed_during_scan")
    return document, backend_before.revision, web_before.revision


def _backend_provenance() -> _InputProvenance:
    manifests = load_domain_manifests(OFFICIAL_DOMAINS)
    discovery = GovernanceScanner(
        GovernanceSettings("test-governance", REPOSITORY_ROOT), domain_manifests=manifests,
    )
    fixed = tuple(path.relative_to(REPOSITORY_ROOT).as_posix() for path in (
        PRODUCT_CATALOG, EXTENSION_CATALOG, OFFICIAL_DOMAINS, ACCEPTANCE_MANIFEST, LEGACY_BASELINE,
    ))
    return _capture_provenance(
        REPOSITORY_ROOT, source_roots=discovery.source_roots(),
        input_paths=tuple(sorted(set(discovery.source_input_paths()) | set(fixed))),
    )


def _snapshot(source_revision: str):
    """Use the Task 4 scanner once, in memory, without persistence side effects."""
    from backend.capability_v2.bootstrap import build_capability_registry

    product = load_catalog_release(PRODUCT_CATALOG.read_text(encoding="utf-8"))
    extension = load_catalog_release(EXTENSION_CATALOG.read_text(encoding="utf-8"))
    manifests = load_domain_manifests(OFFICIAL_DOMAINS)
    acceptance_manifest = json.loads(ACCEPTANCE_MANIFEST.read_text(encoding="utf-8"))
    previous_factory = os.environ.get("AI00_INTEGRATION_ADAPTER_FACTORY")
    if previous_factory is None:
        os.environ["AI00_INTEGRATION_ADAPTER_FACTORY"] = OFFLINE_INTEGRATION_FACTORY
    try:
        registry = build_capability_registry(REPOSITORY_ROOT)
    finally:
        if previous_factory is None:
            os.environ.pop("AI00_INTEGRATION_ADAPTER_FACTORY", None)
    return GovernanceScanner(
        GovernanceSettings("test-governance", REPOSITORY_ROOT),
        registry_snapshot=registry.snapshot(), product_catalog=product, extension_catalog=extension,
        domain_manifests=manifests, acceptance_manifest=acceptance_manifest,
        acceptance_manifest_path=ACCEPTANCE_MANIFEST.relative_to(REPOSITORY_ROOT).as_posix(),
    ).scan(code_revision=source_revision)


def build_local_report(*, web_root: Path = DEFAULT_WEB_ROOT, page_limit: int = 200) -> dict[str, Any]:
    document, backend_revision, web_revision = _stable_scan(
        _snapshot, _backend_provenance,
        lambda: _capture_provenance(web_root, all_tracked=True),
    )
    ids = count(1)
    store = MemoryGovernanceStore(next_ids=lambda: next(ids))
    snapshot = store.import_snapshot(document)
    relations = analyze_relationships(document.capabilities, snapshot_gid=snapshot.snapshot_gid)
    store.save_relation_candidates(relations)
    service = CapabilityGovernanceService(store)

    business_catalog = json.loads(PRODUCT_CATALOG.read_text(encoding="utf-8"))
    baseline = load_legacy_baseline(LEGACY_BASELINE, repository_root=REPOSITORY_ROOT)
    deterministic_blockers: dict[str, list[str]] = {}
    for relation in relations:
        if relation.source == "deterministic" and relation.relation_type == "conflict":
            for capability_key in relation.capability_keys:
                deterministic_blockers.setdefault(capability_key, []).append("cross_domain_conflict")
    gate = evaluate_catalog_business_governance(
        business_catalog, baseline.capabilities, business_review_lookup={}, runtime_verification={},
        deterministic_blockers=deterministic_blockers,
    )
    report = collect_business_audit(
        service, snapshot_gid=str(snapshot.snapshot_gid),
        source_revisions={"backend": backend_revision, "web": web_revision, "source": backend_revision},
        gate_result=gate, page_limit=page_limit, business_catalog=business_catalog,
        legacy_baseline=baseline.capabilities, business_review_lookup={},
    )
    return report.to_dict()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("json",), default="json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--web-root", type=Path, default=DEFAULT_WEB_ROOT)
    parser.add_argument("--page-limit", type=int, default=200)
    args = parser.parse_args(argv)
    document = build_local_report(web_root=args.web_root, page_limit=args.page_limit)
    rendered = json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
