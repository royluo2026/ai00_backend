import json
import shutil

import pytest

import backend.scripts.check_deployment_candidate as candidate_gate

from backend.capability_v2.provider_loader import hash_domain_artifact
from backend.scripts.check_deployment_candidate import check_candidate
from backend.scripts.verify_release_artifacts import DESKTOP_CSP, artifact_sha256


@pytest.fixture(autouse=True)
def trusted_governance(tmp_path, monkeypatch):
    monkeypatch.setattr(candidate_gate, "TRUSTED_REPO_ROOT", tmp_path / "trusted-checker")


def candidate(tmp_path):
    browser = tmp_path / "browser"
    (browser / "web").mkdir(parents=True)
    (browser / "web/frontend-version.json").write_text('{"version":"1.0.3"}', encoding="utf-8")
    (browser / "assets").mkdir()
    (browser / "assets/index-12345678.js").write_text('bundle "1.0.3"', encoding="utf-8")
    (browser / "assets/issues-abcdef12.js").write_text("issue detail", encoding="utf-8")
    (browser / "share/issues").mkdir(parents=True)
    (browser / "share/issues/index.html").write_text(
        '<meta name="app-version" content="1.0.3"><script src="/assets/issues-abcdef12.js"></script>', encoding="utf-8")
    (browser / "index.html").write_text(
        '<meta name="app-version" content="1.0.3"><script src="/assets/index-12345678.js"></script>', encoding="utf-8")
    (browser / "browser-static-policy.json").write_text(json.dumps({
        "schemaVersion": 1, "document": "index.html", "detailDocuments": ["share/issues/index.html"],
        "cacheControl": {"document": "no-store", "immutableAssets": "public, max-age=31536000, immutable"},
        "immutableAssets": ["assets/index-12345678.js", "assets/issues-abcdef12.js"],
        "privateFiles": ["browser-static-policy.json", "release-blocked.json",
                         "runtime-profile.json", "web/frontend-version.json"],
    }), encoding="utf-8")
    (browser / "runtime-profile.json").write_text(
        json.dumps({"client": "browser", "environment": "test", "backendUrl": ""}), encoding="utf-8")
    desktop = tmp_path / "desktop"
    desktop.mkdir()
    (desktop / "assets").mkdir()
    assets = ["about.html", "assets/about-abcdef12.js", "assets/floatBall-abcdef12.js",
              "assets/index-12345678.js", "assets/settings-abcdef12.js", "assets/sidebar-abcdef12.js",
              "float-ball.html", "index.html", "settings.html", "sidebar.html"]
    (desktop / "asset-manifest.json").write_text(
        json.dumps({"schemaVersion": 1, "assets": assets}), encoding="utf-8")
    (desktop / "assets/index-12345678.js").write_text('http://127.0.0.1:8080 "1.0.4"', encoding="utf-8")
    for entry in ("about", "settings", "sidebar", "floatBall"):
        (desktop / f"assets/{entry}-abcdef12.js").write_text("local", encoding="utf-8")
    for page, entry in (("index.html", "index-12345678"), ("about.html", "about-abcdef12"),
                        ("settings.html", "settings-abcdef12"), ("sidebar.html", "sidebar-abcdef12"),
                        ("float-ball.html", "floatBall-abcdef12")):
        (desktop / page).write_text(
            '<meta name="app-version" content="1.0.4">'
            f'<meta http-equiv="Content-Security-Policy" content="{DESKTOP_CSP}">'
            f'<script src="./assets/{entry}.js"></script>', encoding="utf-8")
    (desktop / "frontend-version.json").write_text('{"version":"1.0.4"}', encoding="utf-8")
    (desktop / "runtime-profile.json").write_text(
        json.dumps({"client": "desktop", "environment": "test", "backendUrl": "http://127.0.0.1:8080"}), encoding="utf-8")
    backend = tmp_path / "backend-build"
    (backend / "backend").mkdir(parents=True)
    (backend / "backend/VERSION").write_text("1.2.3", encoding="utf-8")
    for relative in ("backend/main.py", "backend/config.py", "backend/frontend_static.py", "backend/release_version.py",
                     "backend/scripts/runtime_preflight.py", "backend/scripts/check_deployment_candidate.py",
                     "backend/scripts/check_deployment_target.py",
                     "backend/scripts/check_four_scenario_candidate.py", "backend/scripts/verify_release_artifacts.py",
                     "backend/db/table_prefix.py", "backend/db/prefixed_cursor.py",
                     "backend/platform_sdk/prefixed_connection.py",
                     *(f"plugins/{domain}/{domain}_backend/data/connection.py" for domain in
                       ("craft", "agent", "simulation", "device")),
                     "plugins/project_management/project_management_backend/data/connection.py",
                     "plugins/project_management/project_management_backend/capabilities/reviewed.py",
                     "plugins/project_management/project_management_backend/capabilities/provider.py",
                     "plugins/knowledge/knowledge_backend/data/connection.py",
                     "plugins/knowledge/knowledge_backend/capabilities/reviewed.py",
                     "plugins/knowledge/knowledge_backend/provider.py",
                     "plugins/digital_model/digital_model_backend/data/connection.py",
                     "plugins/digital_model/digital_model_backend/capabilities/provider.py",
                     "plugins/integration/integration_backend/data/connection.py",
                     "plugins/integration/integration_backend/capabilities/provider.py",
                     "plugins/factory/factory_backend/infrastructure/connection.py",
                     "plugins/factory/factory_backend/capabilities/provider.py",
                     "plugins/ontology/ontology_backend/infrastructure/connection.py",
                     "plugins/ontology/ontology_backend/capabilities/reviewed.py",
                     "plugins/ontology/ontology_backend/provider.py"):
        file = backend / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("# candidate fixture\n", encoding="utf-8")
    governance = backend / "backend/governance"
    governance.mkdir()
    (governance / "domain_boundaries.json").write_text(json.dumps({
        "version": 1, "product_domains": ["base", "simulation"],
        "data_owners": {
            "base": {"runtime_domain": "base", "new_table_prefix": "workmanship_base_"},
            "simulation": {"runtime_domain": "simulation", "new_table_prefix": "workmanship_sim_"},
        },
        "source_roots": [{"path": "backend", "domain": "base"},
                         {"path": "plugins/simulation", "domain": "simulation"}],
    }), encoding="utf-8")
    (governance / "domain_table_ownership.json").write_text(json.dumps({
        "schema_version": 1, "registry_version": 1, "table_count": 0, "tables": [],
    }), encoding="utf-8")
    (governance / "table_inventory.json").write_text(json.dumps({
        "registry_version": 1, "table_count": 0, "tables": [],
    }), encoding="utf-8")
    (governance / "boundary_baseline.json").write_text(json.dumps({
        "registry_version": 1, "violations": [],
    }), encoding="utf-8")
    reviews = backend / "docs/governance/capability-coverage-review"
    reviews.mkdir(parents=True)
    (reviews / "manifest.json").write_text("{}", encoding="utf-8")
    from backend.scripts.audit_official_domain_artifacts import ROOT

    official = json.loads((ROOT / "backend/capability_v2/official_domains.json").read_text(encoding="utf-8"))
    official["domains"] = [entry for entry in official["domains"] if entry["domain_id"] == "simulation"]
    official["domains"][0]["artifact"]["artifact_hash"] = hash_domain_artifact(
        backend, "plugins/simulation/simulation_backend")
    official_path = backend / "backend/capability_v2/official_domains.json"
    official_path.parent.mkdir(parents=True)
    official_path.write_text(json.dumps(official), encoding="utf-8")
    for relative in (
        "backend/governance/domain_boundaries.json",
        "backend/governance/domain_table_ownership.json",
        "backend/governance/table_inventory.json",
        "backend/governance/boundary_baseline.json",
        "docs/governance/capability-coverage-review/manifest.json",
        "backend/capability_v2/official_domains.json",
    ):
        trusted = candidate_gate.TRUSTED_REPO_ROOT / relative
        trusted.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(backend / relative, trusted)
    manifest = tmp_path / "release-manifest.json"
    manifest.write_text(json.dumps({
        "schemaVersion": 1, "environment": "test", "programVersion": "2.0.0",
        "frontendVersions": {"browser": "1.0.3", "desktop": "1.0.4"},
        "backendVersion": "1.2.3",
        "artifactSha256": {"browser": artifact_sha256(browser),
                           "desktop": artifact_sha256(desktop),
                           "backend": artifact_sha256(backend)},
    }), encoding="utf-8")
    env_file = tmp_path / "runtime.env"
    env_file.write_text("\n".join([
        "AI00_DEPLOY_PROFILE=test", "TABLE_PREFIX=test_", "PUBLIC_URL=http://127.0.0.1:8080",
        "PORT=8080", "BACKEND_BASE_URL=http://127.0.0.1:8080",
        "FEISHU_REDIRECT_URI=http://127.0.0.1:8080/auth/feishu/callback",
        "FEISHU_APP_ID=test-app", "FEISHU_APP_SECRET=test-secret", "JWT_SECRET=test-jwt-secret",
        *(f"{name}=mysql://user_{index}:pass@db:2881/workmanship" for index, name in enumerate((
            "USERS_DB_URL", "AI00_CRAFT_DB_URL", "AI00_AGENT_DB_URL",
            "AI00_SIMULATION_DB_URL", "AI00_DEVICE_DB_URL",
            "AI00_PROJECT_MANAGEMENT_DB_URL", "AI00_KNOWLEDGE_DB_URL",
            "AI00_DIGITAL_MODEL_DB_URL", "AI00_INTEGRATION_DB_URL",
            "AI00_FACTORY_DB_URL", "AI00_ONTOLOGY_DB_URL"))),
    ]), encoding="utf-8")
    return env_file, manifest, browser, desktop, backend


def refresh_backend_hash(args):
    document = json.loads(args[1].read_text(encoding="utf-8"))
    document["artifactSha256"]["backend"] = artifact_sha256(args[4])
    args[1].write_text(json.dumps(document), encoding="utf-8")


def test_candidate_refuses_unowned_table_in_hashed_backend_artifact(tmp_path):
    args = candidate(tmp_path)
    source = args[4] / "plugins/simulation/simulation_backend/unsafe.py"
    source.write_text('SQL = "SELECT * FROM workmanship_sim_unreviewed"\n', encoding="utf-8")
    refresh_backend_hash(args)
    with pytest.raises(ValueError, match="candidate backend table inventory or ownership drift"):
        check_candidate(args[0], args[1], "test", *args[2:])


def test_candidate_refuses_governance_missing_from_hashed_backend_artifact(tmp_path):
    args = candidate(tmp_path)
    (args[4] / "backend/governance/domain_table_ownership.json").unlink()
    refresh_backend_hash(args)
    with pytest.raises(ValueError, match="candidate backend governance evidence missing"):
        check_candidate(args[0], args[1], "test", *args[2:])


def test_candidate_refuses_reviewed_inventory_with_unreviewed_boundary(tmp_path):
    args = candidate(tmp_path)
    source = args[4] / "plugins/simulation/simulation_backend/unsafe.py"
    source.write_text('SQL = "CREATE TABLE scratch (id INT)"\n', encoding="utf-8")
    refresh_backend_hash(args)
    with pytest.raises(ValueError, match="candidate backend boundary audit failed"):
        check_candidate(args[0], args[1], "test", *args[2:])


@pytest.mark.parametrize("relative", [
    "backend/governance/domain_boundaries.json",
    "backend/governance/domain_table_ownership.json",
    "backend/governance/table_inventory.json",
    "backend/governance/boundary_baseline.json",
    "docs/governance/capability-coverage-review/manifest.json",
])
def test_candidate_refuses_self_declared_governance_policy(tmp_path, relative):
    args = candidate(tmp_path)
    (args[4] / relative).write_text((args[4] / relative).read_text(encoding="utf-8") + " ", encoding="utf-8")
    refresh_backend_hash(args)
    with pytest.raises(ValueError, match="candidate backend trusted governance snapshot mismatch"):
        check_candidate(args[0], args[1], "test", *args[2:])


def test_candidate_refuses_extra_self_declared_review(tmp_path):
    args = candidate(tmp_path)
    reviews = args[4] / "docs/governance/capability-coverage-review"
    (reviews / "self-review.json").write_text('{"debt_dispositions": []}', encoding="utf-8")
    refresh_backend_hash(args)
    with pytest.raises(ValueError, match="candidate backend trusted governance snapshot mismatch"):
        check_candidate(args[0], args[1], "test", *args[2:])


def test_candidate_cannot_hide_source_roots_with_its_own_registry(tmp_path):
    args = candidate(tmp_path)
    policy = args[4] / "backend/governance/domain_boundaries.json"
    document = json.loads(policy.read_text(encoding="utf-8"))
    document["source_roots"] = []
    policy.write_text(json.dumps(document), encoding="utf-8")
    refresh_backend_hash(args)
    with pytest.raises(ValueError, match="candidate backend trusted governance snapshot mismatch"):
        check_candidate(args[0], args[1], "test", *args[2:])


def test_candidate_allows_generated_non_review_directory(tmp_path):
    args = candidate(tmp_path)
    (args[4] / "docs/governance/capability-coverage-review/generated").mkdir()
    refresh_backend_hash(args)
    check_candidate(args[0], args[1], "test", *args[2:])


def test_candidate_rejects_provider_source_changed_after_frozen_hash(tmp_path):
    args = candidate(tmp_path)
    source = args[4] / "plugins/simulation/simulation_backend/data/connection.py"
    source.write_text("# changed Provider source\n", encoding="utf-8")
    refresh_backend_hash(args)
    with pytest.raises(ValueError, match="candidate backend Provider artifact mismatch"):
        check_candidate(args[0], args[1], "test", *args[2:])


def test_candidate_rejects_self_rehashed_provider_manifest(tmp_path):
    args = candidate(tmp_path)
    source = args[4] / "plugins/simulation/simulation_backend/data/connection.py"
    source.write_text("# changed Provider source\n", encoding="utf-8")
    official_path = args[4] / "backend/capability_v2/official_domains.json"
    official = json.loads(official_path.read_text(encoding="utf-8"))
    official["domains"][0]["artifact"]["artifact_hash"] = hash_domain_artifact(
        args[4], "plugins/simulation/simulation_backend")
    official_path.write_text(json.dumps(official), encoding="utf-8")
    refresh_backend_hash(args)
    with pytest.raises(ValueError, match="candidate backend trusted Provider manifest mismatch"):
        check_candidate(args[0], args[1], "test", *args[2:])


def test_candidate_refuses_source_change_during_boundary_audit(tmp_path, monkeypatch):
    args = candidate(tmp_path)
    original = candidate_gate.verify_candidate_boundaries

    def change_after_audit(artifact):
        original(artifact)
        (artifact / "backend/main.py").write_text("# changed after audit\n", encoding="utf-8")

    monkeypatch.setattr(candidate_gate, "verify_candidate_boundaries", change_after_audit)
    with pytest.raises(ValueError, match="candidate backend artifact or manifest changed"):
        check_candidate(args[0], args[1], "test", *args[2:])


@pytest.mark.parametrize("artifact_index,relative", [
    (2, "assets/index-12345678.js"),
    (3, "assets/index-12345678.js"),
])
def test_candidate_refuses_frontend_change_during_provider_audit(tmp_path, monkeypatch,
                                                                  artifact_index, relative):
    args = candidate(tmp_path)
    original = candidate_gate.verify_candidate_providers

    def change_after_audit(artifact):
        original(artifact)
        file = args[artifact_index] / relative
        file.write_text(file.read_text(encoding="utf-8") + " changed", encoding="utf-8")

    monkeypatch.setattr(candidate_gate, "verify_candidate_providers", change_after_audit)
    with pytest.raises(ValueError, match="candidate browser or desktop artifact or manifest changed"):
        check_candidate(args[0], args[1], "test", *args[2:])


def test_candidate_combines_profile_and_artifact_checks(tmp_path):
    args = candidate(tmp_path)
    check_candidate(args[0], args[1], "test", *args[2:])
    with pytest.raises(ValueError, match="profile and candidate environment mismatch"):
        check_candidate(args[0], args[1], "production", *args[2:])
    (args[3] / "frontend-version.json").write_text('{"version":"1.0.5"}', encoding="utf-8")
    with pytest.raises(ValueError, match="version binding mismatch"):
        check_candidate(args[0], args[1], "test", *args[2:])


def test_candidate_rejects_bad_runtime_before_artifacts(tmp_path):
    args = candidate(tmp_path)
    args[0].write_text("AI00_DEPLOY_PROFILE=production\nTABLE_PREFIX=test_", encoding="utf-8")
    with pytest.raises(ValueError, match="runtime preflight failed"):
        check_candidate(args[0], args[1], "test", *args[2:])


def test_candidate_refuses_env_file_changed_during_artifact_verification(tmp_path, monkeypatch):
    args = candidate(tmp_path)
    original = candidate_gate.verify_release_artifacts

    def change_after_verification(*arguments):
        original(*arguments)
        args[0].write_text(args[0].read_text(encoding="utf-8") + "\n# changed", encoding="utf-8")

    monkeypatch.setattr(candidate_gate, "verify_release_artifacts", change_after_verification)
    with pytest.raises(ValueError, match="runtime env file changed during candidate checks"):
        check_candidate(args[0], args[1], "test", *args[2:])


def test_candidate_refuses_duplicate_runtime_profile_before_artifact_check(tmp_path):
    args = candidate(tmp_path)
    args[0].write_text(args[0].read_text(encoding="utf-8") + "\nAI00_DEPLOY_PROFILE=production",
                       encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        check_candidate(args[0], args[1], "test", *args[2:])


def test_backend_candidate_stages_verified_manifest_next_to_backend_version(tmp_path):
    from backend.release_version import read_release_version
    from backend.scripts.stage_backend_candidate import stage_backend_candidate

    args = candidate(tmp_path)
    output = tmp_path / "isolated-backend-candidate"
    stage_backend_candidate(args[0], args[1], "test", *args[2:], output)
    assert (output / "release-manifest.json").read_bytes() == args[1].read_bytes()
    assert (output / "backend/VERSION").read_bytes() == (args[4] / "backend/VERSION").read_bytes()
    versions = read_release_version(output / "release-manifest.json", output / "backend/VERSION", "test")
    assert versions == {
        "programVersion": "2.0.0", "frontendVersions": {"browser": "1.0.3", "desktop": "1.0.4"},
        "backendVersion": "1.2.3",
    }


def test_backend_candidate_refuses_existing_target_or_changed_manifest(tmp_path, monkeypatch):
    from backend.scripts import stage_backend_candidate as staging

    args = candidate(tmp_path)
    output = tmp_path / "candidate"
    output.mkdir()
    with pytest.raises(ValueError, match="fresh output"):
        staging.stage_backend_candidate(args[0], args[1], "test", *args[2:], output)
    assert list(output.iterdir()) == []
    output.rmdir()
    original = staging.check_candidate

    def mutate_manifest(*values):
        original(*values)
        args[1].write_text(args[1].read_text(encoding="utf-8") + " ", encoding="utf-8")

    monkeypatch.setattr(staging, "check_candidate", mutate_manifest)
    with pytest.raises(ValueError, match="manifest changed"):
        staging.stage_backend_candidate(args[0], args[1], "test", *args[2:], output)
    assert not output.exists()


def test_backend_candidate_refuses_copy_drift_without_promoting(tmp_path, monkeypatch):
    from backend.scripts import stage_backend_candidate as staging

    args = candidate(tmp_path)
    output = tmp_path / "candidate"
    original = staging.shutil.copytree

    def corrupt_copy(source, target, *copy_args, **options):
        result = original(source, target, *copy_args, **options)
        if source == args[4]:
            (target / "backend/VERSION").write_text("9.9.9", encoding="utf-8")
        return result

    monkeypatch.setattr(staging.shutil, "copytree", corrupt_copy)
    with pytest.raises(ValueError, match="copied backend artifact hash mismatch"):
        staging.stage_backend_candidate(args[0], args[1], "test", *args[2:], output)
    assert not output.exists()
    assert list(tmp_path.glob("candidate.incomplete-*"))


def test_backend_candidate_refuses_nested_output_and_embedded_manifest(tmp_path):
    from backend.scripts.stage_backend_candidate import stage_backend_candidate

    args = candidate(tmp_path)
    nested = args[4] / "candidate"
    with pytest.raises(ValueError, match="fresh output"):
        stage_backend_candidate(args[0], args[1], "test", *args[2:], nested)
    assert not nested.exists()
    (args[4] / "release-manifest.json").write_bytes(args[1].read_bytes())
    with pytest.raises(ValueError, match="must not embed"):
        stage_backend_candidate(args[0], args[1], "test", *args[2:], tmp_path / "candidate")


@pytest.mark.parametrize("artifact_index", [2, 3])
def test_backend_candidate_refuses_output_inside_frontend_artifact(tmp_path, artifact_index):
    from backend.scripts.stage_backend_candidate import stage_backend_candidate

    args = candidate(tmp_path)
    output = args[artifact_index] / "candidate"
    with pytest.raises(ValueError, match="fresh output"):
        stage_backend_candidate(args[0], args[1], "test", *args[2:], output)
    assert not output.exists()
    assert not list(args[artifact_index].glob("candidate.incomplete-*"))
