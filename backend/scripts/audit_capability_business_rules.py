"""Generate the read-only seven-layer Capability business baseline."""
from __future__ import annotations

import argparse
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


def _revision(root: Path, *, relevant_paths: tuple[str, ...] = (".",)) -> str:
    try:
        revision = subprocess.run(
            ("git", "rev-parse", "HEAD"), cwd=root, check=True, capture_output=True, text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("business_audit_revision_unavailable") from exc
    if len(revision) != 40 or any(character not in "0123456789abcdef" for character in revision):
        raise RuntimeError("business_audit_revision_invalid")
    try:
        dirty = subprocess.run(
            ("git", "status", "--porcelain=v1", "--untracked-files=no", "--", *relevant_paths),
            cwd=root, check=True, capture_output=True, text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("business_audit_revision_unavailable") from exc
    if dirty:
        raise RuntimeError("business_audit_relevant_tree_dirty")
    return revision


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
    backend_revision = _revision(REPOSITORY_ROOT, relevant_paths=("backend", "plugins", "docs/governance"))
    web_revision = _revision(web_root)
    document = _snapshot(backend_revision)
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
