from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.capability_v2.provider_loader import ProviderTrustError, hash_domain_artifact
from backend.scripts.audit_official_domain_artifacts import audit_official_domain_artifacts, main


ROOT = Path(__file__).resolve().parents[2]


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    document = json.loads((ROOT / "backend/capability_v2/official_domains.json").read_text(encoding="utf-8"))
    document["domains"] = [domain for domain in document["domains"]
                           if domain["domain_id"] in {"base", "craft", "simulation"}]
    for domain in document["domains"]:
        domain_id = domain["domain_id"]
        relative = f"providers/{domain_id}"
        provider = tmp_path / relative
        provider.mkdir(parents=True)
        (provider / "provider.py").write_text(f"DOMAIN = {domain_id!r}\n", encoding="utf-8")
        domain["artifact_path"] = relative
        domain["artifact"]["artifact_hash"] = hash_domain_artifact(tmp_path, relative)
    path = tmp_path / "official_domains.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return tmp_path, path


def test_audit_reports_every_drift_without_changing_manifest(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root, manifest = _fixture(tmp_path)
    before = manifest.read_bytes()
    (root / "providers/craft/provider.py").write_text("changed\n", encoding="utf-8")
    (root / "providers/simulation/provider.py").write_text("also changed\n", encoding="utf-8")

    report = audit_official_domain_artifacts(root, manifest)

    assert report["clean"] is False
    assert [(entry["domain"], entry["status"]) for entry in report["domains"]] == [
        ("base", "match"), ("craft", "mismatch"), ("simulation", "mismatch")]
    assert report["domains"][1]["expectedHash"] != report["domains"][1]["actualHash"]
    assert manifest.read_bytes() == before
    assert main(["--root", str(root), "--manifest", str(manifest)]) == 2
    assert json.loads(capsys.readouterr().out)["clean"] is False


def test_audit_reports_all_matching_artifacts(tmp_path: Path) -> None:
    root, manifest = _fixture(tmp_path)
    report = audit_official_domain_artifacts(root, manifest)
    assert report["clean"] is True
    assert all(entry["status"] == "match" for entry in report["domains"])


def test_audit_does_not_suppress_provider_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, manifest = _fixture(tmp_path)
    from backend.scripts import audit_official_domain_artifacts as audit_module

    actual_hash = audit_module.hash_domain_artifact

    def failed_hash(repository: Path, relative: str) -> str:
        if relative.endswith("craft"):
            raise ProviderTrustError("provider_path_symlink: untrusted path")
        if relative.endswith("simulation"):
            raise ProviderTrustError("secret local path must not be emitted")
        return actual_hash(repository, relative)

    monkeypatch.setattr(audit_module, "hash_domain_artifact", failed_hash)
    report = audit_official_domain_artifacts(root, manifest)
    assert [(entry["domain"], entry["status"]) for entry in report["domains"]] == [
        ("base", "match"), ("craft", "error"), ("simulation", "error")]
    assert report["domains"][1]["error"] == "provider_path_symlink"
    assert report["domains"][2]["error"] == "provider_artifact_invalid"
    assert "secret local path" not in json.dumps(report)
    assert report["clean"] is False

    def unreadable_hash(repository: Path, relative: str) -> str:
        if relative.endswith("simulation"):
            raise OSError("secret local path must not be emitted")
        return actual_hash(repository, relative)

    monkeypatch.setattr(audit_module, "hash_domain_artifact", unreadable_hash)
    unreadable = audit_official_domain_artifacts(root, manifest)
    assert unreadable["domains"][2]["error"] == "artifact_unreadable"
    assert "secret local path" not in json.dumps(unreadable)


def test_audit_rejects_symlinked_manifest_and_invalid_document(tmp_path: Path) -> None:
    root, manifest = _fixture(tmp_path)
    manifest.write_text("{}", encoding="utf-8")
    assert audit_official_domain_artifacts(root, manifest) == {
        "schemaVersion": 1, "clean": False, "error": "manifest_invalid", "domains": []}
    manifest.write_text('{"schema_version": 1, "domains": []}', encoding="utf-8")
    assert audit_official_domain_artifacts(root, manifest)["clean"] is False
    alias = tmp_path / "alias.json"
    try:
        alias.symlink_to(manifest)
    except OSError:
        pytest.skip("Windows symlink privilege unavailable")
    assert audit_official_domain_artifacts(root, alias)["error"] == "manifest_invalid"
