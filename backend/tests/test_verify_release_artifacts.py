import json

import pytest

from backend.scripts.verify_release_artifacts import DESKTOP_CSP, artifact_sha256, verify_release_artifacts


def write_desktop_renderer(desktop, backend_url):
    (desktop / "assets").mkdir(parents=True, exist_ok=True)
    assets = ["about.html", "assets/about-abcdef12.js", "assets/floatBall-abcdef12.js",
              "assets/index-12345678.js", "assets/index-abcdef12.css", "assets/settings-abcdef12.js", "assets/sidebar-abcdef12.js",
              "float-ball.html", "index.html", "settings.html", "sidebar.html"]
    (desktop / "asset-manifest.json").write_text(
        json.dumps({"schemaVersion": 1, "assets": assets}), encoding="utf-8")
    (desktop / "assets/index-12345678.js").write_text(backend_url + ' "1.1.0"', encoding="utf-8")
    for entry in ("about", "settings", "sidebar", "floatBall"):
        (desktop / f"assets/{entry}-abcdef12.js").write_text("local", encoding="utf-8")
    (desktop / "assets/index-abcdef12.css").write_text("body{}", encoding="utf-8")
    for page, entry in (("index.html", "index-12345678"), ("about.html", "about-abcdef12"),
                        ("settings.html", "settings-abcdef12"), ("sidebar.html", "sidebar-abcdef12"),
                        ("float-ball.html", "floatBall-abcdef12")):
        (desktop / page).write_text(
            '<meta name="app-version" content="1.1.0">'
            f'<meta http-equiv="Content-Security-Policy" content="{DESKTOP_CSP}">'
            f'<script src="./assets/{entry}.js"></script>', encoding="utf-8")


def release_fixture(tmp_path):
    browser = tmp_path / "browser"
    (browser / "web").mkdir(parents=True)
    (browser / "assets").mkdir()
    (browser / "assets/index-12345678.js").write_text('bundle "1.0.3"', encoding="utf-8")
    (browser / "assets/issues-abcdef12.js").write_text("issue detail", encoding="utf-8")
    (browser / "assets/index-abcdef12.css").write_text("style", encoding="utf-8")
    (browser / "share/issues").mkdir(parents=True)
    (browser / "share/issues/index.html").write_text(
        '<meta name="app-version" content="1.0.3">'
        '<script src="/assets/issues-abcdef12.js"></script><link href="/assets/index-abcdef12.css">',
        encoding="utf-8",
    )
    (browser / "index.html").write_text(
        '<meta name="app-version" content="1.0.3">'
        '<script src="/assets/index-12345678.js"></script><link href="/assets/index-abcdef12.css">'
        '<a href="/workbench">工作台</a>',
        encoding="utf-8",
    )
    (browser / "browser-static-policy.json").write_text(json.dumps({
        "schemaVersion": 1, "document": "index.html", "detailDocuments": ["share/issues/index.html"],
        "cacheControl": {"document": "no-store", "immutableAssets": "public, max-age=31536000, immutable"},
        "immutableAssets": ["assets/index-12345678.js", "assets/index-abcdef12.css",
                            "assets/issues-abcdef12.js"],
        "privateFiles": ["browser-static-policy.json", "release-blocked.json",
                         "runtime-profile.json", "web/frontend-version.json"],
    }), encoding="utf-8")
    (browser / "web/frontend-version.json").write_text('{"version":"1.0.3"}', encoding="utf-8")
    (browser / "runtime-profile.json").write_text(
        json.dumps({"client": "browser", "environment": "test", "backendUrl": ""}), encoding="utf-8")
    desktop = tmp_path / "desktop"
    desktop.mkdir()
    write_desktop_renderer(desktop, "http://127.0.0.1:8080")
    (desktop / "frontend-version.json").write_text('{"version":"1.1.0"}', encoding="utf-8")
    (desktop / "runtime-profile.json").write_text(
        json.dumps({"client": "desktop", "environment": "test", "backendUrl": "http://127.0.0.1:8080"}), encoding="utf-8")
    backend = tmp_path / "backend-artifact"
    (backend / "backend").mkdir(parents=True)
    (backend / "backend/main.py").write_bytes(b"backend")
    for relative in ("backend/config.py", "backend/frontend_static.py", "backend/release_version.py", "backend/db/table_prefix.py",
                     "backend/scripts/runtime_preflight.py", "backend/scripts/check_deployment_candidate.py",
                     "backend/scripts/check_deployment_target.py",
                     "backend/scripts/check_four_scenario_candidate.py", "backend/scripts/verify_release_artifacts.py",
                     "backend/db/prefixed_cursor.py", "backend/platform_sdk/prefixed_connection.py",
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
        file.write_text("# release fixture\n", encoding="utf-8")
    backend_version = backend / "backend/VERSION"
    backend_version.write_text("1.4.0\n", encoding="utf-8")
    manifest = {
        "schemaVersion": 1,
        "environment": "test",
        "programVersion": "2.0.0",
        "frontendVersions": {"browser": "1.0.3", "desktop": "1.1.0"},
        "backendVersion": "1.4.0",
        "artifactSha256": {
            "browser": artifact_sha256(browser),
            "desktop": artifact_sha256(desktop),
            "backend": artifact_sha256(backend),
        },
    }
    path = tmp_path / "release-manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path, browser, desktop, backend


def test_release_verifier_binds_real_artifact_bytes_and_backend_version(tmp_path):
    args = release_fixture(tmp_path)
    verify_release_artifacts(args[0], "test", *args[1:])
    (args[1] / "index.html").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="browser artifact hash mismatch"):
        verify_release_artifacts(args[0], "test", *args[1:])


@pytest.mark.parametrize("module_source", [
    'import "./missing-12345678.js"',
    'import("https://other.example/app.js")',
    'import(getRuntimePath())',
])
def test_release_verifier_rejects_undeclared_browser_module_even_with_matching_hash(tmp_path, module_source):
    args = release_fixture(tmp_path)
    (args[1] / "assets/index-12345678.js").write_text('bundle "1.0.3";' + module_source, encoding="utf-8")
    manifest = json.loads(args[0].read_text(encoding="utf-8"))
    manifest["artifactSha256"]["browser"] = artifact_sha256(args[1])
    args[0].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="browser static policy mismatch"):
        verify_release_artifacts(args[0], "test", *args[1:])


@pytest.mark.parametrize("stylesheet", [
    "background:url(./missing-12345678.svg)",
    "background:url(https://other.example/icon.svg)",
    '@import "./other-12345678.css";',
    "background:url(var(--asset))",
])
def test_release_verifier_rejects_undeclared_browser_style_even_with_matching_hash(tmp_path, stylesheet):
    args = release_fixture(tmp_path)
    (args[1] / "assets/index-abcdef12.css").write_text(stylesheet, encoding="utf-8")
    manifest = json.loads(args[0].read_text(encoding="utf-8"))
    manifest["artifactSha256"]["browser"] = artifact_sha256(args[1])
    args[0].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="browser static policy mismatch"):
        verify_release_artifacts(args[0], "test", *args[1:])


def test_release_verifier_accepts_declared_browser_module_and_style_assets(tmp_path):
    args = release_fixture(tmp_path)
    browser = args[1]
    (browser / "assets/index-12345678.js").write_text(
        'bundle "1.0.3";import "./issues-abcdef12.js"', encoding="utf-8")
    (browser / "assets/icon-12345678.svg").write_text("<svg/>", encoding="utf-8")
    (browser / "assets/index-abcdef12.css").write_text(
        "background:url(/assets/icon-12345678.svg)", encoding="utf-8")
    policy_path = browser / "browser-static-policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["immutableAssets"].append("assets/icon-12345678.svg")
    policy["immutableAssets"].sort()
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    manifest = json.loads(args[0].read_text(encoding="utf-8"))
    manifest["artifactSha256"]["browser"] = artifact_sha256(browser)
    args[0].write_text(json.dumps(manifest), encoding="utf-8")
    verify_release_artifacts(args[0], "test", *args[1:])


@pytest.mark.parametrize("extra", ["web/index.html", "share/legacy.html", "unlisted.txt", "other/asset.txt"])
def test_release_verifier_rejects_extra_browser_files_even_with_matching_hash(tmp_path, extra):
    args = release_fixture(tmp_path)
    unwanted = args[1] / extra
    unwanted.parent.mkdir(parents=True, exist_ok=True)
    unwanted.write_text("legacy Browser content", encoding="utf-8")
    manifest = json.loads(args[0].read_text(encoding="utf-8"))
    manifest["artifactSha256"]["browser"] = artifact_sha256(args[1])
    args[0].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="browser static policy mismatch"):
        verify_release_artifacts(args[0], "test", *args[1:])


def test_release_verifier_rejects_unlisted_empty_browser_directory(tmp_path):
    args = release_fixture(tmp_path)
    (args[1] / "legacy").mkdir()
    manifest = json.loads(args[0].read_text(encoding="utf-8"))
    manifest["artifactSha256"]["browser"] = artifact_sha256(args[1])
    args[0].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="browser static policy mismatch"):
        verify_release_artifacts(args[0], "test", *args[1:])


@pytest.mark.parametrize("field", ["programVersion", "frontendVersions", "artifactSha256"])
def test_release_verifier_rejects_duplicate_manifest_keys(tmp_path, field):
    args = release_fixture(tmp_path)
    source = args[0].read_text(encoding="utf-8")
    value = json.loads(source)[field]
    entry = json.dumps(field) + ": " + json.dumps(value)
    args[0].write_text(source.replace(entry, entry + ", " + entry, 1), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid release manifest schema"):
        verify_release_artifacts(args[0], "test", *args[1:])


def test_release_verifier_rejects_old_three_page_desktop_even_with_matching_hash(tmp_path):
    args = release_fixture(tmp_path)
    desktop = args[2]
    (desktop / "sidebar.html").unlink(missing_ok=True)
    manifest_path = desktop / "asset-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["assets"] = [name for name in manifest["assets"] if name != "sidebar.html"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    release = json.loads(args[0].read_text(encoding="utf-8"))
    release["artifactSha256"]["desktop"] = artifact_sha256(desktop)
    args[0].write_text(json.dumps(release), encoding="utf-8")
    with pytest.raises(ValueError, match="desktop renderer artifact invalid") as error:
        verify_release_artifacts(args[0], "test", *args[1:])
    assert "Desktop assets do not match manifest" in str(error.value.__cause__)


def test_release_verifier_rejects_old_four_page_desktop_even_with_matching_hash(tmp_path):
    args = release_fixture(tmp_path)
    desktop = args[2]
    (desktop / "float-ball.html").unlink()
    manifest_path = desktop / "asset-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["assets"].remove("float-ball.html")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    release = json.loads(args[0].read_text(encoding="utf-8"))
    release["artifactSha256"]["desktop"] = artifact_sha256(desktop)
    args[0].write_text(json.dumps(release), encoding="utf-8")
    with pytest.raises(ValueError, match="desktop renderer artifact invalid") as error:
        verify_release_artifacts(args[0], "test", *args[1:])
    assert "Desktop assets do not match manifest" in str(error.value.__cause__)


@pytest.mark.parametrize("component,page", [
    ("browser", "index.html"), ("browser", "share/issues/index.html"),
    ("desktop", "index.html"), ("desktop", "about.html"), ("desktop", "settings.html"),
    ("desktop", "sidebar.html"), ("desktop", "float-ball.html"),
])
@pytest.mark.parametrize("change", ["missing", "wrong", "duplicate"])
def test_release_verifier_rejects_page_version_drift_even_with_matching_hash(tmp_path, component, page, change):
    args = release_fixture(tmp_path)
    artifact = args[1 if component == "browser" else 2]
    page_path = artifact / page
    version = "1.0.3" if component == "browser" else "1.1.0"
    marker = f'<meta name="app-version" content="{version}">'
    html = page_path.read_text(encoding="utf-8")
    if change == "missing":
        html = html.replace(marker, "")
    elif change == "wrong":
        html = html.replace(marker, '<meta name="app-version" content="9.9.9">')
    else:
        html = html.replace(marker, marker + marker)
    page_path.write_text(html, encoding="utf-8")
    manifest = json.loads(args[0].read_text(encoding="utf-8"))
    manifest["artifactSha256"][component] = artifact_sha256(artifact)
    args[0].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match=f"{component} frontend page version mismatch"):
        verify_release_artifacts(args[0], "test", *args[1:])


@pytest.mark.parametrize("invalid_field", ["boolean_schema", "extra_root", "extra_frontend", "extra_artifact"])
def test_release_verifier_rejects_manifest_that_runtime_would_not_claim(tmp_path, invalid_field):
    args = release_fixture(tmp_path)
    manifest = json.loads(args[0].read_text(encoding="utf-8"))
    if invalid_field == "boolean_schema":
        manifest["schemaVersion"] = True
    elif invalid_field == "extra_root":
        manifest["frontendVersion"] = "1.0.3"
    elif invalid_field == "extra_frontend":
        manifest["frontendVersions"]["legacy"] = "1.0.3"
    else:
        manifest["artifactSha256"]["installer"] = "b" * 64
    args[0].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid release manifest schema"):
        verify_release_artifacts(args[0], "test", *args[1:])


def test_release_verifier_refuses_oversized_or_linked_manifest(tmp_path):
    args = release_fixture(tmp_path)
    args[0].write_text(" " * 65537, encoding="utf-8")
    with pytest.raises(ValueError, match="release manifest must be a regular bounded file"):
        verify_release_artifacts(args[0], "test", *args[1:])
    target = tmp_path / "other-manifest.json"
    target.write_text("{}", encoding="utf-8")
    args[0].unlink()
    try:
        args[0].symlink_to(target)
    except OSError as error:
        if getattr(error, "winerror", None) == 1314:
            return
        raise
    with pytest.raises(ValueError, match="release manifest must be a regular bounded file"):
        verify_release_artifacts(args[0], "test", *args[1:])


@pytest.mark.parametrize("change", ["missing", "public_cache", "old_page", "missing_asset",
                                    "missing_detail", "foreign_detail_asset", "single_quote_detail_asset",
                                    "missing_detail_js", "wrong_detail_policy"])
def test_release_verifier_rejects_invalid_browser_static_policy_even_with_matching_hash(tmp_path, change):
    args = release_fixture(tmp_path)
    browser = args[1]
    policy_path = browser / "browser-static-policy.json"
    if change == "missing":
        policy_path.unlink()
    elif change == "public_cache":
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy["cacheControl"]["document"] = "public, max-age=31536000"
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
    elif change == "old_page":
        (browser / "index.html").write_text('<script src="/web/old.js"></script>', encoding="utf-8")
    elif change == "missing_asset":
        (browser / "assets/index-12345678.js").unlink()
    elif change == "missing_detail":
        (browser / "share/issues/index.html").unlink()
    elif change == "foreign_detail_asset":
        (browser / "share/issues/index.html").write_text(
            '<script src="/web/old.js"></script>', encoding="utf-8")
    elif change == "single_quote_detail_asset":
        (browser / "share/issues/index.html").write_text(
            "<script src='/web/old.js'></script>", encoding="utf-8")
    elif change == "missing_detail_js":
        (browser / "share/issues/index.html").write_text(
            '<script src="/assets/index-12345678.js"></script>', encoding="utf-8")
    else:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy["detailDocuments"] = []
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
    manifest = json.loads(args[0].read_text(encoding="utf-8"))
    manifest["artifactSha256"]["browser"] = artifact_sha256(browser)
    args[0].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="browser static policy mismatch"):
        verify_release_artifacts(args[0], "test", *args[1:])


def test_release_verifier_rejects_wrong_environment_and_backend_version(tmp_path):
    args = release_fixture(tmp_path)
    with pytest.raises(ValueError, match="environment mismatch"):
        verify_release_artifacts(args[0], "production", *args[1:])
    (args[3] / "backend/VERSION").write_text("1.4.1", encoding="utf-8")
    with pytest.raises(ValueError, match="version binding mismatch"):
        verify_release_artifacts(args[0], "test", *args[1:])


def test_release_verifier_rejects_backend_version_file_runtime_would_not_read(tmp_path):
    args = release_fixture(tmp_path)
    (args[3] / "backend/VERSION").write_text("1.4.0" + " " * 256, encoding="utf-8")
    manifest = json.loads(args[0].read_text(encoding="utf-8"))
    manifest["artifactSha256"]["backend"] = artifact_sha256(args[3])
    args[0].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="backend version metadata must be a regular bounded file"):
        verify_release_artifacts(args[0], "test", *args[1:])


def test_release_verifier_rejects_replaced_desktop_package(tmp_path):
    args = release_fixture(tmp_path)
    (args[2] / "assets/index-12345678.js").write_bytes(b"other desktop")
    with pytest.raises(ValueError, match="desktop artifact hash mismatch"):
        verify_release_artifacts(args[0], "test", *args[1:])


def test_release_verifier_rejects_a_fake_desktop_directory_with_matching_hash(tmp_path):
    args = release_fixture(tmp_path)
    (args[2] / "asset-manifest.json").unlink()
    manifest = json.loads(args[0].read_text(encoding="utf-8"))
    manifest["artifactSha256"]["desktop"] = artifact_sha256(args[2])
    args[0].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="desktop renderer artifact invalid"):
        verify_release_artifacts(args[0], "test", *args[1:])


@pytest.mark.parametrize("change", ["missing_page", "missing_asset", "foreign_asset", "single_quote_asset",
                                    "unquoted_asset", "css_remote", "js_missing_import", "js_dynamic_nonliteral",
                                    "inline_script", "script_without_src", "weak_csp", "wrong_backend", "undeclared_file"])
def test_release_verifier_rejects_invalid_desktop_renderer_even_with_matching_hash(tmp_path, change):
    args = release_fixture(tmp_path)
    desktop = args[2]
    page = desktop / "settings.html"
    if change == "missing_page":
        page.unlink()
    elif change == "missing_asset":
        (desktop / "assets/settings-abcdef12.js").unlink()
    elif change == "foreign_asset":
        page.write_text(page.read_text(encoding="utf-8") + '<img src="https://example.com/a.png">', encoding="utf-8")
    elif change == "single_quote_asset":
        page.write_text(page.read_text(encoding="utf-8") + "<img src='https://example.com/a.png'>", encoding="utf-8")
    elif change == "unquoted_asset":
        page.write_text(page.read_text(encoding="utf-8") + "<img src=https://example.com/a.png>", encoding="utf-8")
    elif change == "css_remote":
        (desktop / "assets/index-abcdef12.css").write_text(
            "body{background:url(https://example.com/a.png)}", encoding="utf-8")
    elif change == "js_missing_import":
        (desktop / "assets/index-12345678.js").write_text(
            "import './missing.js';http://127.0.0.1:8080", encoding="utf-8")
    elif change == "js_dynamic_nonliteral":
        (desktop / "assets/index-12345678.js").write_text(
            "import(name);http://127.0.0.1:8080", encoding="utf-8")
    elif change == "inline_script":
        page.write_text(page.read_text(encoding="utf-8") + '<script>alert(1)</script>', encoding="utf-8")
    elif change == "script_without_src":
        page.write_text(page.read_text(encoding="utf-8").replace(
            '<script src="./assets/settings-abcdef12.js"></script>',
            '<script></script><link href="./assets/settings-abcdef12.js">'), encoding="utf-8")
    elif change == "weak_csp":
        page.write_text(page.read_text(encoding="utf-8").replace("connect-src 'none'", "connect-src *"), encoding="utf-8")
    elif change == "wrong_backend":
        (desktop / "assets/index-12345678.js").write_text("https://workmanship-backend.chehejia.com", encoding="utf-8")
    else:
        (desktop / "web").mkdir()
        (desktop / "web/legacy.html").write_text("legacy", encoding="utf-8")
    manifest = json.loads(args[0].read_text(encoding="utf-8"))
    manifest["artifactSha256"]["desktop"] = artifact_sha256(desktop)
    args[0].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="desktop renderer artifact invalid"):
        verify_release_artifacts(args[0], "test", *args[1:])


@pytest.mark.parametrize("relative", [
    "backend/scripts/runtime_preflight.py",
    "backend/scripts/check_deployment_candidate.py",
    "backend/scripts/check_deployment_target.py",
    "backend/scripts/check_four_scenario_candidate.py",
    "backend/scripts/verify_release_artifacts.py",
    "plugins/craft/craft_backend/data/connection.py",
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
    "plugins/ontology/ontology_backend/provider.py",
])
def test_release_verifier_rejects_backend_missing_required_domain_source_even_with_matching_hash(tmp_path, relative):
    args = release_fixture(tmp_path)
    (args[3] / relative).unlink()
    manifest = json.loads(args[0].read_text(encoding="utf-8"))
    manifest["artifactSha256"]["backend"] = artifact_sha256(args[3])
    args[0].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="backend runtime file missing"):
        verify_release_artifacts(args[0], "test", *args[1:])


def test_release_verifier_rejects_legacy_browser_bundled_in_backend_even_with_matching_hash(tmp_path):
    args = release_fixture(tmp_path)
    old_page = args[3] / "dist/web/index.html"
    old_page.parent.mkdir(parents=True)
    old_page.write_text("legacy browser", encoding="utf-8")
    manifest = json.loads(args[0].read_text(encoding="utf-8"))
    manifest["artifactSha256"]["backend"] = artifact_sha256(args[3])
    args[0].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="legacy Browser assets in backend artifact"):
        verify_release_artifacts(args[0], "test", *args[1:])


@pytest.mark.parametrize("component,relative", [
    ("backend", "backend/.env"), ("backend", "backend/runtime.env"),
    ("backend", "plugins/craft/.env.local"),
    ("backend", "backend/.env.production.template"),
    ("browser", "assets/runtime.env.local"), ("desktop", ".ENV"),
])
def test_release_verifier_rejects_environment_files_even_with_matching_hash(tmp_path, component, relative):
    args = release_fixture(tmp_path)
    index = {"browser": 1, "desktop": 2, "backend": 3}[component]
    file = args[index] / relative
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text("DUMMY_SECRET=not-a-real-secret\n", encoding="utf-8")
    manifest = json.loads(args[0].read_text(encoding="utf-8"))
    manifest["artifactSha256"][component] = artifact_sha256(args[index])
    args[0].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="environment file forbidden"):
        verify_release_artifacts(args[0], "test", *args[1:])


def test_release_verifier_rejects_frontend_version_mismatch(tmp_path):
    args = release_fixture(tmp_path)
    (args[2] / "frontend-version.json").write_text('{"version":"1.1.1"}', encoding="utf-8")
    with pytest.raises(ValueError, match="version binding mismatch"):
        verify_release_artifacts(args[0], "test", *args[1:])


@pytest.mark.parametrize("component,index,metadata", [
    ("browser", 1, "web/frontend-version.json"),
    ("desktop", 2, "frontend-version.json"),
])
def test_release_verifier_rejects_metadata_relabel_without_matching_bundle(tmp_path, component, index, metadata):
    args = release_fixture(tmp_path)
    (args[index] / metadata).write_text('{"version":"9.9.9"}', encoding="utf-8")
    pages = ("index.html", "share/issues/index.html") if component == "browser" else (
        "index.html", "about.html", "settings.html", "sidebar.html", "float-ball.html")
    old_version = "1.0.3" if component == "browser" else "1.1.0"
    for page in pages:
        path = args[index] / page
        path.write_text(path.read_text(encoding="utf-8").replace(
            f'<meta name="app-version" content="{old_version}">',
            '<meta name="app-version" content="9.9.9">'), encoding="utf-8")
    manifest = json.loads(args[0].read_text(encoding="utf-8"))
    manifest["frontendVersions"][component] = "9.9.9"
    manifest["artifactSha256"][component] = artifact_sha256(args[index])
    args[0].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match=f"{component} frontend bundle version mismatch"):
        verify_release_artifacts(args[0], "test", *args[1:])


@pytest.mark.parametrize("foreign_url", [
    "https://workmanship-backend.chehejia.com", "http://127.0.0.1:8080",
    "http://pc-pc2l7vve:8082",
])
def test_browser_test_bundle_rejects_crossed_backend_with_matching_hash(tmp_path, foreign_url):
    args = release_fixture(tmp_path)
    bundle = args[1] / "assets/index-12345678.js"
    bundle.write_text(bundle.read_text(encoding="utf-8") + f' "{foreign_url}"', encoding="utf-8")
    manifest = json.loads(args[0].read_text(encoding="utf-8"))
    manifest["artifactSha256"]["browser"] = artifact_sha256(args[1])
    args[0].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="browser backend URL mismatch"):
        verify_release_artifacts(args[0], "test", *args[1:])


def test_browser_production_bundle_rejects_test_backend_with_matching_hash(tmp_path):
    args = release_fixture(tmp_path)
    manifest = json.loads(args[0].read_text(encoding="utf-8"))
    manifest["environment"] = "production"
    for component, artifact in (("browser", args[1]), ("desktop", args[2])):
        (artifact / "runtime-profile.json").write_text(json.dumps({
            "client": component, "environment": "production",
            "backendUrl": "https://workmanship-backend.chehejia.com",
        }), encoding="utf-8")
    browser_bundle = args[1] / "assets/index-12345678.js"
    browser_bundle.write_text(browser_bundle.read_text(encoding="utf-8") +
                              ' "https://workmanship-backend.chehejia.com" "http://127.0.0.1:8080"', encoding="utf-8")
    (args[2] / "assets/index-12345678.js").write_text(
        'https://workmanship-backend.chehejia.com "1.1.0"', encoding="utf-8")
    for component, artifact in (("browser", args[1]), ("desktop", args[2])):
        manifest["artifactSha256"][component] = artifact_sha256(artifact)
    args[0].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="browser backend URL mismatch"):
        verify_release_artifacts(args[0], "production", *args[1:])


def test_browser_production_bundle_requires_embedded_production_backend(tmp_path):
    args = release_fixture(tmp_path)
    manifest = json.loads(args[0].read_text(encoding="utf-8"))
    manifest["environment"] = "production"
    for component, artifact in (("browser", args[1]), ("desktop", args[2])):
        (artifact / "runtime-profile.json").write_text(json.dumps({
            "client": component, "environment": "production",
            "backendUrl": "https://workmanship-backend.chehejia.com",
        }), encoding="utf-8")
    (args[2] / "assets/index-12345678.js").write_text(
        'https://workmanship-backend.chehejia.com "1.1.0"', encoding="utf-8")
    for component, artifact in (("browser", args[1]), ("desktop", args[2])):
        manifest["artifactSha256"][component] = artifact_sha256(artifact)
    args[0].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="browser backend URL mismatch"):
        verify_release_artifacts(args[0], "production", *args[1:])


def test_release_verifier_rejects_missing_frontend_metadata(tmp_path):
    args = release_fixture(tmp_path)
    (args[1] / "web/frontend-version.json").unlink()
    with pytest.raises(ValueError, match="browser frontend version metadata missing"):
        verify_release_artifacts(args[0], "test", *args[1:])


def test_release_verifier_rejects_a_scaffold_even_with_matching_hashes(tmp_path):
    args = release_fixture(tmp_path)
    (args[1] / "release-blocked.json").write_text('{"reason":"not migrated"}', encoding="utf-8")
    manifest = json.loads(args[0].read_text(encoding="utf-8"))
    manifest["artifactSha256"]["browser"] = artifact_sha256(args[1])
    args[0].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="not releasable"):
        verify_release_artifacts(args[0], "test", *args[1:])


@pytest.mark.parametrize("component,member", [
    ("browser", "assets/release-blocked.json"),
    ("desktop", "desktop/release-blocked.json"),
    ("backend", "dist/release-blocked.json"),
])
def test_release_verifier_rejects_nested_blocked_content_even_with_matching_hashes(tmp_path, component, member):
    args = release_fixture(tmp_path)
    artifact = {"browser": args[1], "desktop": args[2], "backend": args[3]}[component]
    marker = artifact / member
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text('{"reason":"not migrated"}', encoding="utf-8")
    manifest = json.loads(args[0].read_text(encoding="utf-8"))
    manifest["artifactSha256"][component] = artifact_sha256(artifact)
    args[0].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="not releasable"):
        verify_release_artifacts(args[0], "test", *args[1:])


def production_release_fixture(tmp_path):
    args = release_fixture(tmp_path)
    manifest = json.loads(args[0].read_text(encoding="utf-8"))
    manifest["environment"] = "production"
    for component, artifact in (("browser", args[1]), ("desktop", args[2])):
        (artifact / "runtime-profile.json").write_text(json.dumps({
            "client": component, "environment": "production",
            "backendUrl": "https://workmanship-backend.chehejia.com",
        }), encoding="utf-8")
        if component == "desktop":
            (artifact / "assets/index-12345678.js").write_text(
                'https://workmanship-backend.chehejia.com "1.1.0"', encoding="utf-8")
        else:
            (artifact / "assets/index-12345678.js").write_text(
                'bundle "1.0.3" "https://workmanship-backend.chehejia.com"', encoding="utf-8")
        manifest["artifactSha256"][component] = artifact_sha256(artifact)
    args[0].write_text(json.dumps(manifest), encoding="utf-8")
    return args, manifest


def test_production_release_rejects_development_backend_version(tmp_path):
    args, manifest = production_release_fixture(tmp_path)
    (args[3] / "backend/VERSION").write_text("1.4.0-dev", encoding="utf-8")
    manifest["backendVersion"] = "1.4.0-dev"
    manifest["artifactSha256"]["backend"] = artifact_sha256(args[3])
    args[0].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="stable release"):
        verify_release_artifacts(args[0], "production", *args[1:])


def test_production_release_accepts_matching_embedded_profiles(tmp_path):
    args, _ = production_release_fixture(tmp_path)
    verify_release_artifacts(args[0], "production", *args[1:])


@pytest.mark.parametrize("component", ["program", "browser", "desktop"])
def test_production_release_rejects_matching_prerelease_versions(tmp_path, component):
    args, manifest = production_release_fixture(tmp_path)
    if component == "program":
        manifest["programVersion"] = "2.0.0-dev"
    else:
        artifact = args[1 if component == "browser" else 2]
        old_version = manifest["frontendVersions"][component]
        new_version = old_version + "-dev"
        metadata_path = artifact / ("web/frontend-version.json" if component == "browser" else "frontend-version.json")
        metadata_path.write_text(json.dumps({"version": new_version}), encoding="utf-8")
        pages = ("index.html", "share/issues/index.html") if component == "browser" else (
            "index.html", "about.html", "settings.html", "sidebar.html", "float-ball.html")
        for page in pages:
            page_path = artifact / page
            page_path.write_text(page_path.read_text(encoding="utf-8").replace(
                f'<meta name="app-version" content="{old_version}">',
                f'<meta name="app-version" content="{new_version}">'), encoding="utf-8")
        bundle_path = artifact / "assets/index-12345678.js"
        bundle_path.write_text(bundle_path.read_text(encoding="utf-8").replace(
            f'"{old_version}"', f'"{new_version}"'), encoding="utf-8")
        manifest["frontendVersions"][component] = new_version
        manifest["artifactSha256"][component] = artifact_sha256(artifact)
    args[0].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="stable release"):
        verify_release_artifacts(args[0], "production", *args[1:])


@pytest.mark.parametrize("client,profile", [
    ("browser", {"client": "desktop", "environment": "test", "backendUrl": ""}),
    ("browser", {"client": "browser", "environment": "test", "backendUrl": "https://workmanship-backend.chehejia.com"}),
    ("desktop", {"client": "desktop", "environment": "production", "backendUrl": "https://workmanship-backend.chehejia.com"}),
    ("desktop", {"client": "desktop", "environment": "test", "backendUrl": "http://127.0.0.1:8082"}),
])
def test_release_verifier_rejects_wrong_embedded_profile_even_with_matching_hash(tmp_path, client, profile):
    args = release_fixture(tmp_path)
    (args[1 if client == "browser" else 2] / "runtime-profile.json").write_text(
        json.dumps(profile), encoding="utf-8")
    manifest = json.loads(args[0].read_text(encoding="utf-8"))
    manifest["artifactSha256"][client] = artifact_sha256(args[1 if client == "browser" else 2])
    args[0].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match=f"{client} runtime profile mismatch"):
        verify_release_artifacts(args[0], "test", *args[1:])


def test_release_verifier_rejects_missing_runtime_profile(tmp_path):
    args = release_fixture(tmp_path)
    (args[2] / "runtime-profile.json").unlink()
    with pytest.raises(ValueError, match="desktop runtime profile mismatch"):
        verify_release_artifacts(args[0], "test", *args[1:])
