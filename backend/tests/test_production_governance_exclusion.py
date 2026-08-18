from importlib.util import find_spec
from pathlib import Path
import json
import subprocess
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import backend.scripts.check_production_governance_exclusion as exclusion
import backend.scripts.build_capability_v2_production_artifact as artifact_builder


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


def signed_release_report() -> dict[str, str]:
    private_key = Ed25519PrivateKey.generate()
    report = {"conclusion": "pass", "signing_key_id": "release-test"}
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":")).encode("utf-8")
    report["public_key"] = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    report["signature"] = __import__("base64").b64encode(private_key.sign(canonical)).decode("ascii")
    return report


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
    write(source / "docs/governance/capability-catalog-release.json", "{}")
    write(source / "docs/governance/test-extension/capability-governance-catalog-release.json", "{}")
    write(frontend / "web/index.html")
    write(frontend / "web/admin/capability_governance/index.html", "TEST_GOVERNANCE_START")
    write(
        allowlist,
        json.dumps(
            {
                "schema_version": 1,
                "backend_top_level_packages": ["capabilities"],
                "migrations": ["backend/db/migrations/*.sql"],
                "frontend_prefixes": ["web/**"],
                "catalog_files": ["docs/governance/capability-catalog-release.json"],
                "provider_modules": [],
            }
        ),
    )
    report_path = tmp_path / "release-report.json"
    write(report_path, json.dumps(signed_release_report()))

    report = artifact_builder.build_production_artifact(
        source, frontend, report_path, output, allowlist_path=allowlist
    )

    assert report.status == "passed"
    assert (output / "backend/capabilities/registry_next.py").is_file()
    assert not (output / "backend/capabilities/__pycache__/registry_next.cpython-312.pyc").exists()
    assert (output / "backend/db/migrations/202608010001_base.sql").is_file()
    assert (output / "docs/governance/capability-catalog-release.json").is_file()
    assert (output / "web/index.html").is_file()
    assert not (output / "backend/capability_governance_test/provider.py").exists()
    assert not (output / "backend/db/migrations/test_governance/0001.sql").exists()
    assert not (output / "docs/governance/test-extension").exists()
    assert not (output / "web/admin/capability_governance").exists()


def test_production_artifact_builder_rejects_unsigned_or_secret_report(tmp_path):
    report_path = tmp_path / "release-report.json"
    report = signed_release_report()
    report["signature"] = ""
    report["secret"] = "leak"
    write(report_path, json.dumps(report))

    errors = artifact_builder.validate_release_report(report_path)

    assert {"release_report_signature_missing", "release_report_secret_present"} <= set(errors)


def test_production_artifact_builder_rejects_tampered_signed_report(tmp_path):
    report_path = tmp_path / "release-report.json"
    report = signed_release_report()
    report["conclusion"] = "fail"
    write(report_path, json.dumps(report))

    errors = artifact_builder.validate_release_report(report_path)

    assert "release_report_signature_invalid" in errors


def test_production_artifact_builder_runs_as_a_direct_script():
    completed = subprocess.run(
        [sys.executable, str(ROOT / "backend/scripts/build_capability_v2_production_artifact.py"), "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
