import json

import pytest

from backend.release_version import read_backend_source_version, read_release_version


def test_openapi_backend_version_uses_bounded_source_version(tmp_path):
    version_path = tmp_path / "VERSION"
    version_path.write_text("1.4.2\n", encoding="utf-8")
    assert read_backend_source_version(version_path) == "1.4.2"
    version_path.write_text("not-a-version", encoding="utf-8")
    assert read_backend_source_version(version_path) == "unmarked"


def test_main_openapi_metadata_uses_backend_version_source():
    from pathlib import Path

    main = Path(__file__).resolve().parents[1] / "main.py"
    source = main.read_text(encoding="utf-8")
    assert "version=read_backend_source_version()" in source
    assert 'version="1.0.0"' not in source


def test_missing_release_manifest_is_not_inferred_from_api_version(tmp_path):
    version_path = tmp_path / "VERSION"
    version_path.write_text("0.1.0-dev\n", encoding="utf-8")
    assert read_release_version(tmp_path / "missing.json", version_path) == {
        "programVersion": None,
        "frontendVersions": {"browser": None, "desktop": None},
        "backendVersion": "0.1.0-dev",
    }


def test_release_manifest_keeps_three_distinct_versions(tmp_path):
    version_path = tmp_path / "VERSION"
    version_path.write_text("1.4.0\n", encoding="utf-8")
    manifest_path = tmp_path / "release-manifest.json"
    manifest_path.write_text(json.dumps({
        "schemaVersion": 1,
        "environment": "test",
        "programVersion": "2.0.0",
        "frontendVersions": {"browser": "1.0.3", "desktop": "1.1.0"},
        "backendVersion": "1.4.0",
        "artifactSha256": {component: "a" * 64 for component in ("browser", "desktop", "backend")},
    }), encoding="utf-8")
    assert read_release_version(manifest_path, version_path, runtime_environment="test") == {
        "programVersion": "2.0.0",
        "frontendVersions": {"browser": "1.0.3", "desktop": "1.1.0"},
        "backendVersion": "1.4.0",
    }


@pytest.mark.parametrize("field", ["root", "frontend", "artifact"])
def test_runtime_rejects_duplicate_release_manifest_keys(tmp_path, field):
    version_path = tmp_path / "VERSION"
    version_path.write_text("1.4.0", encoding="utf-8")
    manifest_path = tmp_path / "release-manifest.json"
    manifest = {
        "schemaVersion": 1, "environment": "test", "programVersion": "2.0.0",
        "frontendVersions": {"browser": "1.0.3", "desktop": "1.1.0"},
        "backendVersion": "1.4.0",
        "artifactSha256": {name: "a" * 64 for name in ("browser", "desktop", "backend")},
    }
    source = json.dumps(manifest)
    key = {"root": '"programVersion": "2.0.0"',
           "frontend": '"browser": "1.0.3"',
           "artifact": '"backend": "' + "a" * 64 + '"'}[field]
    manifest_path.write_text(source.replace(key, key + ", " + key, 1), encoding="utf-8")
    result = read_release_version(manifest_path, version_path, runtime_environment="test")
    assert result["programVersion"] is None
    assert result["frontendVersions"] == {"browser": None, "desktop": None}


@pytest.mark.parametrize("field", ["program", "browser", "desktop"])
def test_runtime_does_not_trim_manifest_version_claims(tmp_path, field):
    version_path = tmp_path / "VERSION"
    version_path.write_text("1.4.0\n", encoding="utf-8")
    manifest_path = tmp_path / "release-manifest.json"
    manifest = {
        "schemaVersion": 1, "environment": "test", "programVersion": "2.0.0",
        "frontendVersions": {"browser": "1.0.3", "desktop": "1.1.0"},
        "backendVersion": "1.4.0",
        "artifactSha256": {name: "a" * 64 for name in ("browser", "desktop", "backend")},
    }
    if field == "program":
        manifest["programVersion"] = " 2.0.0"
    else:
        manifest["frontendVersions"][field] += " "
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    result = read_release_version(manifest_path, version_path, runtime_environment="test")
    assert result["programVersion"] is None
    if field != "program":
        assert result["frontendVersions"][field] is None


def test_manifest_cannot_claim_other_environment_or_unconfigured_runtime(tmp_path):
    version_path = tmp_path / "VERSION"
    version_path.write_text("1.4.0", encoding="utf-8")
    manifest_path = tmp_path / "release-manifest.json"
    manifest_path.write_text(json.dumps({
        "schemaVersion": 1, "environment": "production", "programVersion": "2.0.0",
        "frontendVersions": {"browser": "1.0.3", "desktop": "1.1.0"},
        "backendVersion": "1.4.0",
        "artifactSha256": {component: "a" * 64 for component in ("browser", "desktop", "backend")},
    }), encoding="utf-8")
    assert read_release_version(manifest_path, version_path, runtime_environment="test")["programVersion"] is None
    assert read_release_version(manifest_path, version_path, runtime_environment="")["programVersion"] is None
    assert read_release_version(manifest_path, version_path, runtime_environment="production")["programVersion"] == "2.0.0"


def test_production_runtime_cannot_claim_program_version_with_dev_backend(tmp_path):
    version_path = tmp_path / "VERSION"
    version_path.write_text("1.4.0-dev", encoding="utf-8")
    manifest_path = tmp_path / "release-manifest.json"
    manifest_path.write_text(json.dumps({
        "schemaVersion": 1, "environment": "production", "programVersion": "2.0.0",
        "frontendVersions": {"browser": "1.0.3", "desktop": "1.1.0"},
        "backendVersion": "1.4.0-dev",
        "artifactSha256": {component: "a" * 64 for component in ("browser", "desktop", "backend")},
    }), encoding="utf-8")
    result = read_release_version(manifest_path, version_path, runtime_environment="production")
    assert result["backendVersion"] == "1.4.0-dev"
    assert result["programVersion"] is None


@pytest.mark.parametrize("component", ["program", "browser", "desktop"])
def test_production_runtime_cannot_claim_program_version_with_prerelease_component(tmp_path, component):
    version_path = tmp_path / "VERSION"
    version_path.write_text("1.4.0", encoding="utf-8")
    manifest_path = tmp_path / "release-manifest.json"
    manifest = {
        "schemaVersion": 1, "environment": "production", "programVersion": "2.0.0",
        "frontendVersions": {"browser": "1.0.3", "desktop": "1.1.0"},
        "backendVersion": "1.4.0",
        "artifactSha256": {name: "a" * 64 for name in ("browser", "desktop", "backend")},
    }
    if component == "program":
        manifest["programVersion"] = "2.0.0-dev"
    else:
        manifest["frontendVersions"][component] += "-dev"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert read_release_version(manifest_path, version_path, runtime_environment="production")["programVersion"] is None


def test_invalid_release_manifest_does_not_claim_a_version(tmp_path):
    version_path = tmp_path / "VERSION"
    version_path.write_text("0.1.0-dev", encoding="utf-8")
    manifest_path = tmp_path / "release-manifest.json"
    manifest_path.write_text('{"programVersion": 123, "backendVersion": " "}', encoding="utf-8")
    assert read_release_version(manifest_path, version_path)["programVersion"] is None
    assert read_release_version(manifest_path, version_path)["backendVersion"] == "0.1.0-dev"


def test_mismatched_backend_release_cannot_claim_program_version(tmp_path):
    version_path = tmp_path / "VERSION"
    version_path.write_text("1.4.1", encoding="utf-8")
    manifest_path = tmp_path / "release-manifest.json"
    manifest_path.write_text(json.dumps({
        "schemaVersion": 1, "environment": "test",
        "programVersion": "2.0.0", "frontendVersions": {"browser": "1.0.3", "desktop": "1.1.0"}, "backendVersion": "1.4.0",
        "artifactSha256": {component: "a" * 64 for component in ("browser", "desktop", "backend")},
    }), encoding="utf-8")
    assert read_release_version(manifest_path, version_path) == {
        "programVersion": None, "frontendVersions": {"browser": "1.0.3", "desktop": "1.1.0"}, "backendVersion": "1.4.1",
    }


def test_invalid_source_version_cannot_claim_a_release(tmp_path):
    version_path = tmp_path / "VERSION"
    version_path.write_text("api-1.0.0", encoding="utf-8")
    manifest_path = tmp_path / "release-manifest.json"
    manifest_path.write_text(json.dumps({
        "schemaVersion": 1, "environment": "test",
        "programVersion": "2.0.0", "frontendVersions": {"browser": "1.0.3", "desktop": "1.1.0"}, "backendVersion": "api-1.0.0",
        "artifactSha256": {component: "a" * 64 for component in ("browser", "desktop", "backend")},
    }), encoding="utf-8")
    assert read_release_version(manifest_path, version_path) == {
        "programVersion": None, "frontendVersions": {"browser": "1.0.3", "desktop": "1.1.0"}, "backendVersion": None,
    }


def test_version_endpoint_reports_development_combination_without_claiming_a_release(monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import app
    monkeypatch.delenv('AI00_DEPLOY_PROFILE', raising=False)

    response = TestClient(app).get('/api/system/version')
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    assert response.json()['backendVersion'] == '0.1.0-dev'
    assert response.json()['programVersion'] == '1.0.7'
    assert response.json()['versionSource'] == 'development'


def test_both_frontends_must_be_bound_before_claiming_program_version(tmp_path):
    version_path = tmp_path / "VERSION"
    version_path.write_text("1.4.0", encoding="utf-8")
    manifest_path = tmp_path / "release-manifest.json"
    manifest_path.write_text(json.dumps({
        "schemaVersion": 1, "environment": "test",
        "programVersion": "2.0.0", "frontendVersions": {"browser": "1.0.3"}, "backendVersion": "1.4.0",
        "artifactSha256": {component: "a" * 64 for component in ("browser", "desktop", "backend")},
    }), encoding="utf-8")
    result = read_release_version(manifest_path, version_path)
    assert result["programVersion"] is None
    assert result["frontendVersions"] == {"browser": "1.0.3", "desktop": None}


@pytest.mark.parametrize("invalid_field", ["schema", "environment", "artifact", "legacy_frontend"])
def test_incomplete_or_legacy_manifest_cannot_claim_program_version(tmp_path, invalid_field):
    version_path = tmp_path / "VERSION"
    version_path.write_text("1.4.0", encoding="utf-8")
    manifest = {
        "schemaVersion": 1,
        "environment": "test",
        "programVersion": "2.0.0",
        "frontendVersions": {"browser": "1.0.3", "desktop": "1.1.0"},
        "backendVersion": "1.4.0",
        "artifactSha256": {component: "a" * 64 for component in ("browser", "desktop", "backend")},
    }
    if invalid_field == "schema":
        manifest["schemaVersion"] = 2
    elif invalid_field == "environment":
        manifest["environment"] = "staging"
    elif invalid_field == "artifact":
        manifest["artifactSha256"]["desktop"] = "not-a-sha256"
    else:
        manifest["frontendVersion"] = "1.0.3"
        del manifest["frontendVersions"]
    manifest_path = tmp_path / "release-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert read_release_version(manifest_path, version_path)["programVersion"] is None


@pytest.mark.parametrize("invalid_field", ["boolean_schema", "extra_root", "extra_frontend", "extra_artifact"])
def test_manifest_requires_exact_release_schema(tmp_path, invalid_field):
    version_path = tmp_path / "VERSION"
    version_path.write_text("1.4.0", encoding="utf-8")
    manifest = {
        "schemaVersion": 1, "environment": "test", "programVersion": "2.0.0",
        "frontendVersions": {"browser": "1.0.3", "desktop": "1.1.0"},
        "backendVersion": "1.4.0",
        "artifactSha256": {component: "a" * 64 for component in ("browser", "desktop", "backend")},
    }
    if invalid_field == "boolean_schema":
        manifest["schemaVersion"] = True
    elif invalid_field == "extra_root":
        manifest["frontendVersion"] = "1.0.3"
    elif invalid_field == "extra_frontend":
        manifest["frontendVersions"]["legacy"] = "1.0.3"
    else:
        manifest["artifactSha256"]["installer"] = "b" * 64
    manifest_path = tmp_path / "release-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert read_release_version(manifest_path, version_path, runtime_environment="test")["programVersion"] is None


@pytest.mark.parametrize("invalid_file", ["oversized_manifest", "oversized_version", "directory_manifest",
                                          "directory_version", "linked_manifest", "linked_version"])
def test_runtime_refuses_non_regular_or_unbounded_version_metadata(tmp_path, invalid_file):
    version_path = tmp_path / "VERSION"
    version_path.write_text("1.4.0", encoding="utf-8")
    manifest_path = tmp_path / "release-manifest.json"
    manifest = {
        "schemaVersion": 1, "environment": "test", "programVersion": "2.0.0",
        "frontendVersions": {"browser": "1.0.3", "desktop": "1.1.0"},
        "backendVersion": "1.4.0",
        "artifactSha256": {component: "a" * 64 for component in ("browser", "desktop", "backend")},
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    if invalid_file == "oversized_manifest":
        manifest_path.write_text(json.dumps(manifest) + " " * 65536, encoding="utf-8")
    elif invalid_file == "oversized_version":
        version_path.write_text("1.4.0" + " " * 256, encoding="utf-8")
    elif invalid_file in ("directory_manifest", "directory_version"):
        target = manifest_path if invalid_file == "directory_manifest" else version_path
        target.unlink()
        target.mkdir()
    else:
        target = manifest_path if invalid_file == "linked_manifest" else version_path
        source = tmp_path / f"real-{target.name}"
        target.rename(source)
        try:
            target.symlink_to(source)
        except OSError as error:
            pytest.skip(f"file symlink unavailable: {error}")
    result = read_release_version(manifest_path, version_path, runtime_environment="test")
    assert result["programVersion"] is None
    if invalid_file in ("oversized_version", "directory_version", "linked_version"):
        assert result["backendVersion"] is None
