"""Atomic construction and publication of the official Capability registry."""
from __future__ import annotations

import json
import sys
import threading
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from backend.capabilities.registry_next import CapabilityRegistry

from .domain_manifest import load_domain_manifests
from .provider_loader import DomainProviderLoader


_registry: CapabilityRegistry | None = None
_registry_lock = threading.Lock()
_test_governance_store_factory: Callable[[], Any] | None = None
_test_governance_service_factory: Callable[[Any], Any] | None = None


def _plain_catalog_value(value: Any) -> Any:
    """Copy an immutable snapshot value into a Catalog-loader-safe tree."""
    if isinstance(value, Mapping):
        return {str(key): _plain_catalog_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_catalog_value(item) for item in value]
    return value


def build_capability_registry(
    root: Path | None = None,
    manifest_path: Path | None = None,
    *,
    include_test_governance: bool = False,
) -> CapabilityRegistry:
    if include_test_governance:
        return build_test_governance_capability_registry(root, manifest_path)
    return _build_official_capability_registry(root, manifest_path)


def build_test_governance_capability_registry(
    root: Path | None = None,
    manifest_path: Path | None = None,
    *,
    service_port: Any | None = None,
    store: Any | None = None,
    seed_document: Any | None = None,
    store_factory: Callable[[], Any] | None = None,
    service_factory: Callable[[Any], Any] | None = None,
) -> CapabilityRegistry:
    """Build the explicit test-only governance profile with injectable authority.

    The official registry never imports this extension.  Tests, local tooling,
    and the explicitly selected ``test-governance`` profile may inject a
    service, an in-memory store, and an immutable seed document.  Keeping those
    ports explicit prevents a test bootstrap from silently using production
    persistence while still making the profile useful for end-to-end tests.
    """
    registry = _build_official_capability_registry(root, manifest_path)
    from backend.capability_governance_test.provider import register_governance_capabilities
    from backend.capability_governance_test.service import CapabilityGovernanceService
    from backend.capability_governance_test.store import MemoryGovernanceStore

    governance_store = store or (store_factory() if store_factory is not None else MemoryGovernanceStore())
    if seed_document is not None:
        importer = getattr(governance_store, "import_snapshot", None)
        if not callable(importer):
            raise TypeError("test_governance_store_requires_import_snapshot")
        importer(seed_document)
    service = service_port or (
        service_factory(governance_store) if service_factory is not None
        else CapabilityGovernanceService(store=governance_store)
    )
    register_governance_capabilities(registry, service_port=service)
    binder = getattr(service, "bind_registry_snapshot", None)
    if callable(binder):
        binder(registry.snapshot())
    return registry


def _build_official_capability_registry(
    root: Path | None = None,
    manifest_path: Path | None = None,
) -> CapabilityRegistry:
    repository_root = (root or Path(__file__).resolve().parents[2]).resolve()
    path = manifest_path or Path(__file__).with_name("official_domains.json")
    registry = CapabilityRegistry()
    DomainProviderLoader(
        repository_root,
        load_domain_manifests(path),
    ).register_all(registry)
    return registry


def get_capability_registry() -> CapabilityRegistry:
    global _registry
    if _registry is not None:
        return _registry
    with _registry_lock:
        if _registry is None:
            # Production and ordinary development bootstraps remain strictly
            # official.  Loading the extension requires an explicit profile;
            # an accidental environment variable cannot alter the artifact
            # because the extension itself is test-only and separately built.
            profile = os.environ.get("AI00_DEPLOYMENT_PROFILE", "").strip()
            if profile == "test-governance" and _test_governance_store_factory is None:
                _install_default_test_governance_runtime()
            complete_registry = (
                build_test_governance_capability_registry(
                    store_factory=_test_governance_store_factory,
                    service_factory=_test_governance_service_factory,
                )
                if profile == "test-governance" else build_capability_registry()
            )
            _registry = complete_registry
    return _registry


def _install_default_test_governance_runtime() -> None:
    """Install bounded scanner/worker ports for the explicit test profile."""
    from backend.capability_governance_test.analysis import AnalysisRequest, run_deterministic_analysis
    from backend.capability_governance_test.audit import AuditSink
    from backend.capability_governance_test.business_audit import audit
    from backend.capability_governance_test.scanner import GovernanceScanner
    from backend.capability_governance_test.service import CapabilityGovernanceService
    from backend.capability_governance_test.store import MemoryGovernanceStore, SqlGovernanceStore
    from backend.capability_governance_test.worker import InMemoryRunLeaseStore, LeasedGovernanceWorker, SqlRunLeaseStore
    from backend.domain_ports.capability_governance_config import GovernanceSettings
    from backend.capability_v2.catalog import load_catalog_release
    from backend.capability_v2.catalog_store import SqlCatalogStore
    from backend.capability_v2.release_gate import evaluate_catalog_business_governance, load_legacy_baseline
    from backend.utils.gid import next_gid

    repository_root = Path(__file__).resolve().parents[2]
    product_document = json.loads(
        (repository_root / "docs/governance/capability-catalog-release.json").read_text(encoding="utf-8")
    )
    product = load_catalog_release(product_document)
    extension = load_catalog_release(
        (repository_root / "docs/governance/test-extension/capability-governance-catalog-release.json").read_text(encoding="utf-8")
    )
    manifests = load_domain_manifests(repository_root / "backend/capability_v2/official_domains.json")
    acceptance_manifest = json.loads(
        (repository_root / "backend/tests/acceptance/fixtures/case-manifest.json").read_text(encoding="utf-8")
    )
    legacy_baseline = load_legacy_baseline(
        repository_root / "docs/governance/capability-business-governance-legacy-baseline.json",
        repository_root=repository_root,
    )

    def store_factory() -> Any:
        try:
            from backend.db.connection import acquire_connection
            return SqlGovernanceStore(acquire_connection())
        except Exception:
            return MemoryGovernanceStore()

    def service_factory(store: Any) -> Any:
        scanner = GovernanceScanner(
            GovernanceSettings("test-governance", repository_root),
            product_catalog=product_document,
            extension_catalog=extension,
            domain_manifests=manifests,
            acceptance_manifest=acceptance_manifest,
        )
        if getattr(store, "persistent", False):
            from backend.db.connection import acquire_connection
            leases = SqlRunLeaseStore(acquire_connection)
            catalog_store = SqlCatalogStore(acquire_connection)
        else:
            leases = InMemoryRunLeaseStore()
            catalog_store = None
        worker = LeasedGovernanceWorker(leases, worker_id="capability-governance")
        audit_sink = AuditSink(next_gid=next_gid)

        def web_revision_provider() -> str | None:
            value = os.environ.get("AI00_TEST_GOVERNANCE_WEB_REVISION", "").strip()
            return value if len(value) == 40 and all(character in "0123456789abcdef" for character in value) else None

        def business_review_lookup(version_gid: str, definition_hash: str) -> str | None:
            lookup = getattr(store, "current_business_review", None)
            review = lookup(int(version_gid), definition_hash) if callable(lookup) else None
            return definition_hash if review is not None else None

        def business_gate_provider(snapshot: Any) -> Any:
            document = getattr(snapshot, "document", snapshot)
            release_id = str(getattr(document, "product_release_id", ""))
            release = product if product.release_id == release_id else (
                catalog_store.get(release_id) if catalog_store is not None else None
            )
            if release is None or release.catalog_hash != str(getattr(document, "catalog_hash", "")):
                raise ValueError("snapshot_catalog_release_unavailable")
            catalog = _plain_catalog_value(
                product_document if release is product else release.model_dump(mode="json")
            )
            list_reviews = getattr(store, "list_current_business_reviews", None)
            if callable(list_reviews):
                approved = {
                    (str(getattr(review, "capability_version_gid")), str(getattr(review, "definition_hash")))
                    for review in list_reviews()
                }
                review_lookup = lambda version_gid, definition_hash: (
                    definition_hash if (str(version_gid), str(definition_hash)) in approved else None
                )
            else:
                review_lookup = business_review_lookup
            return evaluate_catalog_business_governance(
                catalog,
                legacy_baseline.capabilities,
                business_review_lookup=review_lookup,
                runtime_verification={},
                report_definition_blockers=True,
            )

        service_holder: dict[str, Any] = {}

        def analysis_runner(snapshot_record: Any, request: Any) -> Any:
            document = getattr(snapshot_record, "document", snapshot_record)
            source_revision = str(getattr(document, "code_revision", ""))
            web_revision = web_revision_provider() or source_revision
            revisions = {"backend": source_revision, "web": web_revision, "source": source_revision}
            service = service_holder["service"]
            base = service.collect_business_audit_base(
                snapshot_gid=str(getattr(snapshot_record, "snapshot_gid", "")),
                source_revisions=revisions,
            )
            return audit(
                base.findings,
                capabilities=base.audit_capabilities,
                snapshot_gid=base.snapshot_gid,
                source_revisions=base.source_revisions,
                relations=base.relations,
                unbound_entries=base.unbound_entries,
                gate_result=business_gate_provider(snapshot_record),
            )

        def test_runner(snapshot: Any, payload: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
            result = run_deterministic_analysis(snapshot, AnalysisRequest())
            return {"status": "passed" if result.status == "ok" else "failed", "findings": result.findings}

        service = CapabilityGovernanceService(
            store=store,
            scanner=scanner,
            analysis_runner=analysis_runner,
            test_runner=test_runner,
            worker=worker,
            audit_sink=audit_sink,
            web_revision_provider=web_revision_provider,
            business_gate_provider=business_gate_provider,
            next_ids=next_gid,
        )
        service_holder["service"] = service
        return service

    global _test_governance_store_factory, _test_governance_service_factory
    _test_governance_store_factory = store_factory
    _test_governance_service_factory = service_factory


def reset_capability_registry_for_tests() -> None:
    if "pytest" not in sys.modules:
        raise RuntimeError("capability registry reset is test-only")
    global _registry, _test_governance_store_factory, _test_governance_service_factory
    with _registry_lock:
        _registry = None
        _test_governance_store_factory = None
        _test_governance_service_factory = None


def configure_test_governance_runtime(
    *,
    store_factory: Callable[[], Any] | None = None,
    service_factory: Callable[[Any], Any] | None = None,
) -> None:
    """Inject persistent test-profile ports before the HTTP app is imported.

    The production bootstrap has no call site for this hook.  A test-governance
    launcher can provide ``SqlGovernanceStore`` (and a workflow-aware service)
    without changing the official registry or placing credentials in module
    globals.  The hook is intentionally test-profile-only and may be reset
    between isolated acceptance runs.
    """
    if str(os.environ.get("AI00_DEPLOYMENT_PROFILE", "")).strip() != "test-governance":
        raise RuntimeError("AI00_DEPLOYMENT_PROFILE=test-governance is required")
    global _test_governance_store_factory, _test_governance_service_factory
    with _registry_lock:
        _test_governance_store_factory = store_factory
        _test_governance_service_factory = service_factory
    with _registry_lock:
        global _registry
        _registry = None


__all__ = [
    "build_capability_registry",
    "build_test_governance_capability_registry",
    "get_capability_registry",
    "reset_capability_registry_for_tests",
    "configure_test_governance_runtime",
]
