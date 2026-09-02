from importlib.util import find_spec
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import base64
from datetime import UTC, datetime

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import backend.scripts.check_production_governance_exclusion as exclusion
import backend.scripts.build_capability_v2_production_artifact as artifact_builder
from backend.capability_v2.catalog import build_catalog_entry, build_release, load_catalog_release
from backend.capability_v2.release_gate import (
    create_legacy_baseline,
    evaluate_catalog_business_governance,
)


ROOT = Path(__file__).resolve().parents[2]


def test_production_governance_exclusion_checker_is_available():
    assert find_spec("backend.scripts.check_production_governance_exclusion") is not None


def test_checker_exposes_production_artifact_interface():
    assert callable(getattr(exclusion, "check_production_artifact", None))


def test_production_artifact_builder_is_available():
    assert find_spec("backend.scripts.build_capability_v2_production_artifact") is not None


def write(path: Path, content: str = "safe production content") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def signing_material() -> tuple[Ed25519PrivateKey, str]:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return private_key, public_key


def trusted_catalog() -> dict[str, object]:
    source = json.loads(
        (ROOT / "docs/governance/capability-catalog-release.json").read_text(encoding="utf-8")
    )
    descriptor = load_catalog_release(source).descriptors[0]
    release = build_release((descriptor,), created_at=datetime(2026, 9, 1, tzinfo=UTC))
    document = release.model_dump(mode="json")
    document["descriptors"] = [build_catalog_entry(descriptor)]
    return document


TEST_CATALOG = trusted_catalog()
TEST_ROW = TEST_CATALOG["descriptors"][0]
TEST_KEY = f"{TEST_ROW['id']}@{TEST_ROW['major_version']}"
TEST_APPROVALS = {
    (TEST_ROW["capability_version_gid"], TEST_ROW["business_definition_hash"]):
        TEST_ROW["business_definition_hash"]
}


def signed_release_report(private_key: Ed25519PrivateKey, signing_key_id: str = "release-test") -> dict[str, object]:
    governance = evaluate_catalog_business_governance(
        TEST_CATALOG, {TEST_KEY: TEST_ROW["business_definition_hash"]},
        business_review_lookup=TEST_APPROVALS,
        runtime_verification={TEST_KEY: True},
    ).serialized()
    report = {
        "report_gid": "501",
        "code_revision": "rev-a",
        "product_catalog_release_id": TEST_CATALOG["release_id"],
        "snapshot_gid": "101",
        "test_run_gid": "201",
        "conclusion": "pass",
        "blockers": [],
        "evidence_hash": "sha256:evidence",
        "static_gate_hash": "sha256:static-gate",
        "business_governance": governance,
        "signing_key_id": signing_key_id,
    }
    canonical = artifact_builder._canonical_release_report(report)
    report["report_hash"] = "sha256:" + hashlib.sha256(canonical).hexdigest()
    report["signature"] = base64.b64encode(private_key.sign(canonical)).decode("ascii")
    return report


def governance_source(source: Path) -> Path:
    catalog_path = source / "docs/governance/capability-catalog-release.json"
    write(catalog_path, json.dumps(TEST_CATALOG))
    subprocess.run(("git", "init"), cwd=source, check=True, capture_output=True)
    subprocess.run(("git", "config", "user.email", "test@example.invalid"), cwd=source, check=True)
    subprocess.run(("git", "config", "user.name", "Test"), cwd=source, check=True)
    subprocess.run(("git", "add", "."), cwd=source, check=True)
    subprocess.run(("git", "commit", "-m", "catalog"), cwd=source, check=True, capture_output=True)
    create_legacy_baseline(
        catalog_path,
        source / "docs/governance/capability-business-governance-legacy-baseline.json",
        source_revision="HEAD", repository_root=source,
    )
    approvals = source / "approvals.json"
    write(approvals, json.dumps({
        "schema_version": 1,
        "catalog_release_id": TEST_CATALOG["release_id"],
        "approvals": [{
            "capability_key": TEST_KEY,
            "capability_version_gid": TEST_ROW["capability_version_gid"],
            "definition_hash": TEST_ROW["business_definition_hash"],
            "decision": "approved",
        }],
    }))
    return approvals


def test_production_artifact_rejects_governance_provider(tmp_path):
    write(tmp_path / "backend/capability_governance_test/provider.py")

    report = exclusion.check_production_artifact(tmp_path)

    assert report.status == "failed"
    assert "governance_backend_present" in report.errors


def test_production_artifact_rejects_governance_paths_and_markers(tmp_path):
    forbidden = {
        "backend/db/migrations/test_governance/0001.sql": "governance_migrations_present",
        "backend/routers/capability_governance.py": "governance_routes_present",
        "docs/governance/test-extension/catalog.json": "governance_catalog_extension_present",
        "backend/tests/fixtures/capability_governance/data.json": "governance_fixtures_present",
        "web/admin/capability_governance/index.html": "governance_ui_present",
        "backend/domain_ports/capability_governance_ai.py": "governance_provider_present",
    }
    for path in forbidden:
        write(tmp_path / path)
    write(tmp_path / "backend/capability_v2/bootstrap.py", "TEST_GOVERNANCE_START")
    write(tmp_path / "backend/capability_v2/identities.py", "test.governance")

    report = exclusion.check_production_artifact(tmp_path)

    assert report.status == "failed"
    assert set(forbidden.values()) <= set(report.errors)
    assert "governance_marker_present" in report.errors
    assert "governance_temporary_identity_present" in report.errors


def test_production_artifact_builder_copies_only_allowlisted_files(tmp_path):
    source = tmp_path / "source"
    frontend = tmp_path / "frontend"
    output = tmp_path / "artifact"
    allowlist = source / "docs/governance/test-extension/production-artifact-allowlist.json"
    write(source / "backend/capabilities/registry_next.py")
    write(source / "backend/capabilities/__pycache__/registry_next.cpython-312.pyc")
    write(source / "backend/capability_governance_test/provider.py", "TEST_GOVERNANCE_START")
    write(source / "backend/db/migrations/202608010001_base.sql")
    write(source / "backend/db/migrations/test_governance/0001.sql")
    write(source / "docs/governance/test-extension/capability-governance-catalog-release.json", "{}")
    write(frontend / "web/index.html")
    write(frontend / "web/tests/run_tests.js", "load('/web/admin/capability_governance/index.html')")
    write(frontend / "web/admin/capability_governance/index.html", "TEST_GOVERNANCE_START")
    private_key, public_key = signing_material()
    write(
        allowlist,
        json.dumps(
            {
                "schema_version": 1,
                "backend_top_level_packages": ["capabilities"],
                "migrations": ["backend/db/migrations/*.sql"],
                "frontend_prefixes": ["web/**"],
                "frontend_excluded_prefixes": ["web/tests/**"],
                "catalog_files": ["docs/governance/capability-catalog-release.json"],
                "provider_modules": [],
                "trusted_release_keys": {"release-test": public_key},
            }
        ),
    )
    report_path = tmp_path / "release-report.json"
    write(report_path, json.dumps(signed_release_report(private_key)))
    approvals = governance_source(source)

    report = artifact_builder.build_production_artifact(
        source, frontend, report_path, output, allowlist_path=allowlist,
        business_approvals_path=approvals,
    )

    assert report.status == "passed"
    assert (output / "backend/capabilities/registry_next.py").is_file()
    assert not (output / "backend/capabilities/__pycache__/registry_next.cpython-312.pyc").exists()
    assert (output / "backend/db/migrations/202608010001_base.sql").is_file()
    assert (output / "docs/governance/capability-catalog-release.json").is_file()
    assert (output / "web/index.html").is_file()
    assert not (output / "web/tests/run_tests.js").exists()
    assert not (output / "backend/capability_governance_test/provider.py").exists()
    assert not (output / "backend/db/migrations/test_governance/0001.sql").exists()
    assert not (output / "docs/governance/test-extension").exists()
    assert not (output / "web/admin/capability_governance").exists()
    assert not any(
        "capability_governance" in path.read_text(encoding="utf-8", errors="ignore")
        for path in output.rglob("*") if path.is_file()
    )


def test_production_artifact_checker_rejects_residual_governance_ui_reference(tmp_path):
    write(
        tmp_path / "web/tests/run_tests.js",
        "load('/web/admin/capability_governance/index.html')",
    )

    report = exclusion.check_production_artifact(tmp_path)

    assert report.status == "failed"
    assert "governance_ui_reference_present" in report.errors


def test_production_artifact_builder_rejects_unsigned_or_secret_report(tmp_path):
    report_path = tmp_path / "release-report.json"
    private_key, _public_key = signing_material()
    report = signed_release_report(private_key)
    report["signature"] = ""
    report["secret"] = "leak"
    write(report_path, json.dumps(report))

    errors = artifact_builder.validate_release_report(report_path, {})

    assert {"release_report_signature_missing", "release_report_unknown_fields"} <= set(errors)


def test_production_artifact_builder_rejects_missing_pinned_field_before_signature_verification(tmp_path):
    private_key, public_key = signing_material()
    report = signed_release_report(private_key)
    del report["code_revision"]
    report_path = tmp_path / "release-report.json"
    write(report_path, json.dumps(report))

    errors = artifact_builder.validate_release_report(report_path, {"release-test": public_key})

    assert "release_report_missing_fields" in errors


def test_production_artifact_builder_rejects_tampered_signed_report(tmp_path):
    report_path = tmp_path / "release-report.json"
    private_key, public_key = signing_material()
    report = signed_release_report(private_key)
    report["conclusion"] = "fail"
    write(report_path, json.dumps(report))

    errors = artifact_builder.validate_release_report(report_path, {"release-test": public_key})

    assert "release_report_signature_invalid" in errors


def test_production_artifact_builder_rejects_self_signed_replacement_key(tmp_path):
    report_path = tmp_path / "release-report.json"
    trusted_key, trusted_public_key = signing_material()
    attacker_key, _attacker_public_key = signing_material()
    write(report_path, json.dumps(signed_release_report(attacker_key, "attacker")))

    errors = artifact_builder.validate_release_report(report_path, {"release-test": trusted_public_key})

    assert "release_report_untrusted_signing_key" in errors


def test_production_artifact_builder_discards_failed_temp_output_and_allows_retry(tmp_path):
    source = tmp_path / "source"
    frontend = tmp_path / "frontend"
    output = tmp_path / "artifact"
    private_key, public_key = signing_material()
    allowlist = source / "docs/governance/test-extension/production-artifact-allowlist.json"
    write(source / "backend/capabilities/registry_next.py", "capability_governance")
    write(frontend / "web/index.html")
    write(
        allowlist,
        json.dumps(
            {
                "schema_version": 1,
                "backend_top_level_packages": ["capabilities"],
                "migrations": [],
                "frontend_prefixes": ["web/**"],
                "frontend_excluded_prefixes": ["web/tests/**"],
                "catalog_files": ["docs/governance/capability-catalog-release.json"],
                "provider_modules": [],
                "trusted_release_keys": {"release-test": public_key},
            }
        ),
    )
    release_report = tmp_path / "release-report.json"
    write(release_report, json.dumps(signed_release_report(private_key)))
    approvals = governance_source(source)

    failed = artifact_builder.build_production_artifact(
        source, frontend, release_report, output, allowlist_path=allowlist,
        business_approvals_path=approvals,
    )

    assert failed.status == "failed"
    assert not output.exists()
    assert not list(tmp_path.glob(".artifact.tmp-*"))

    write(source / "backend/capabilities/registry_next.py")
    retried = artifact_builder.build_production_artifact(
        source, frontend, release_report, output, allowlist_path=allowlist,
        business_approvals_path=approvals,
    )

    assert retried.status == "passed"
    assert (output / "backend/capabilities/registry_next.py").is_file()


def test_production_artifact_builder_rejects_unapproved_release_report_fields(tmp_path):
    private_key, public_key = signing_material()
    report = signed_release_report(private_key)
    report["api_key"] = "not-allowed"
    report_path = tmp_path / "release-report.json"
    write(report_path, json.dumps(report))

    errors = artifact_builder.validate_release_report(report_path, {"release-test": public_key})

    assert "release_report_unknown_fields" in errors


def test_production_artifact_builder_runs_as_a_direct_script():
    completed = subprocess.run(
        [sys.executable, str(ROOT / "backend/scripts/build_capability_v2_production_artifact.py"), "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
