"""Verify a release manifest against immutable build artifacts before deployment."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.release_version import (ARTIFACT_FIELDS, MANIFEST_FIELDS, MAX_BACKEND_VERSION_BYTES,
                                     MAX_MANIFEST_BYTES, SHA256_PATTERN, STABLE_VERSION_PATTERN,
                                     VERSION_PATTERN, _read_regular_text, parse_release_manifest)

PRODUCTION_BACKEND = "https://workmanship-backend.chehejia.com"
LOCAL_BACKEND = "http://127.0.0.1:8080"
REQUIRED_BACKEND_FILES = (
    "backend/main.py",
    "backend/config.py",
    "backend/frontend_static.py",
    "backend/release_version.py",
    "backend/scripts/runtime_preflight.py",
    "backend/scripts/check_deployment_candidate.py",
    "backend/scripts/check_deployment_target.py",
    "backend/scripts/check_four_scenario_candidate.py",
    "backend/scripts/verify_release_artifacts.py",
    "backend/db/table_prefix.py",
    "backend/db/prefixed_cursor.py",
    "backend/platform_sdk/prefixed_connection.py",
    *(f"plugins/{domain}/{domain}_backend/data/connection.py"
      for domain in ("craft", "agent", "simulation", "device")),
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
)
BROWSER_ASSET_NAME = re.compile(r"[A-Za-z0-9_-]+-[0-9a-f]{8,}\.(?:js|css|svg|png|webp|woff2?)\Z")
BROWSER_DOCUMENTS = {"index.html": "index", "share/issues/index.html": "issues"}
DESKTOP_PAGES = {"index.html": "index", "about.html": "about", "settings.html": "settings",
                 "sidebar.html": "sidebar", "float-ball.html": "floatBall"}
DESKTOP_CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
               "font-src 'self'; connect-src 'none'; frame-src 'none'; object-src 'none'; "
               "base-uri 'none'; form-action 'none'")
DESKTOP_ASSET_NAME = re.compile(r"assets/[A-Za-z0-9][A-Za-z0-9._-]*-[0-9a-f]{8,}\.(?:js|css|svg|png|webp|woff2)\Z")


def _html_references(html: str, all_tags: bool = False) -> list[str]:
    references = []
    for tag, attributes in re.findall(r"<([a-z][a-z0-9:-]*)\b([^>]*?)>", html, re.I):
        if not all_tags and tag.lower() not in {"script", "link", "img"}:
            continue
        declared = re.findall(r"\b(?:src|href)\s*=", attributes, re.I)
        quoted = re.findall(r"\b(?:src|href)\s*=\s*(['\"])(.*?)\1", attributes, re.I | re.S)
        if len(declared) != len(quoted):
            raise ValueError("unquoted HTML resource")
        references.extend(value for _, value in quoted)
    return references


def verify_browser_asset_references(artifact: Path, assets: list[str]) -> None:
    allowed = set(assets)
    for name in assets:
        if not name.endswith((".js", ".css")):
            continue
        file = artifact / name
        if file.stat().st_size > (64 if name.endswith(".js") else 8) * 1024 * 1024:
            raise ValueError("oversized Browser asset")
        source = file.read_text(encoding="utf-8")
        if name.endswith(".js"):
            static = re.findall(r"\b(?:from\s*|import\s*)(['\"])([^'\"\\]+)\1", source)
            dynamic = re.findall(r"\bimport\s*\(\s*(['\"])([^'\"\\]+)\1\s*\)", source)
            if (len(static) != len(re.findall(r"\b(?:from\s*|import\s*)['\"]", source))
                    or len(dynamic) != len(re.findall(r"\bimport\s*\(", source))):
                raise ValueError("invalid Browser module reference")
            for _, reference in (*static, *dynamic):
                if (not re.fullmatch(r"\./[A-Za-z0-9_-]+-[0-9a-f]{8,}\.js", reference)
                        or f"assets/{reference[2:]}" not in allowed):
                    raise ValueError("undeclared Browser module")
        else:
            stripped = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
            if re.search(r"@import\b", stripped, re.I) or "\\" in stripped:
                raise ValueError("invalid Browser stylesheet import")
            references = re.findall(r"\burl\s*\(\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s)'\"(]+))\s*\)", stripped, re.I)
            if len(references) != len(re.findall(r"\burl\s*\(", stripped, re.I)):
                raise ValueError("invalid Browser stylesheet URL")
            for double_quoted, single_quoted, unquoted in references:
                reference = double_quoted or single_quoted or unquoted
                if (not re.fullmatch(r"(?:\./|/assets/)[A-Za-z0-9_-]+-[0-9a-f]{8,}\.(?:svg|png|webp|woff2?)", reference)
                        or f"assets/{reference.removeprefix('./').removeprefix('/assets/')}" not in allowed):
                    raise ValueError("undeclared Browser stylesheet asset")


def verify_browser_static_policy(artifact: Path) -> None:
    policy_path = artifact / "browser-static-policy.json"
    index_path = artifact / "index.html"
    assets_path = artifact / "assets"
    try:
        if (policy_path.is_symlink() or not policy_path.is_file() or policy_path.stat().st_size > 16384
                or index_path.is_symlink() or not index_path.is_file() or index_path.stat().st_size > 2 * 1024 * 1024
                or assets_path.is_symlink() or not assets_path.is_dir()):
            raise ValueError("missing or oversized Browser static files")
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        assets = sorted(f"assets/{item.name}" for item in assets_path.iterdir()
                        if item.is_file() and not item.is_symlink())
        if any(not item.is_file() or item.is_symlink() or not BROWSER_ASSET_NAME.fullmatch(item.name)
               for item in assets_path.iterdir()):
            raise ValueError("invalid Browser asset")
        for document, entry in BROWSER_DOCUMENTS.items():
            document_path = artifact / document
            parts = Path(document).parts
            if (any(artifact.joinpath(*parts[:depth]).is_symlink()
                    for depth in range(1, len(parts) + 1))
                    or not document_path.is_file() or document_path.stat().st_size > 2 * 1024 * 1024):
                raise ValueError("missing or oversized Browser document")
            references = _html_references(document_path.read_text(encoding="utf-8"))
            if (not any(re.fullmatch(rf"/assets/{entry}-[0-9a-f]+\.js", reference) for reference in references)
                    or any(not reference.startswith("/assets/") or reference[1:] not in assets
                           for reference in references)):
                raise ValueError("undeclared Browser resource")
        expected = {
            "schemaVersion": 1, "document": "index.html", "detailDocuments": ["share/issues/index.html"],
            "cacheControl": {"document": "no-store", "immutableAssets": "public, max-age=31536000, immutable"},
            "immutableAssets": assets,
            "privateFiles": ["browser-static-policy.json", "release-blocked.json",
                             "runtime-profile.json", "web/frontend-version.json"],
        }
        if policy != expected:
            raise ValueError("Browser static policy does not match artifact")
        allowed_files = set(assets) | {
            "index.html", "share/issues/index.html", "browser-static-policy.json",
            "runtime-profile.json", "web/frontend-version.json", "release-blocked.json",
        }
        allowed_directories = {"assets", "share", "share/issues", "web"}
        for member in artifact.rglob("*"):
            relative = member.relative_to(artifact).as_posix()
            if (member.is_symlink() or
                    (member.is_dir() and relative not in allowed_directories) or
                    (member.is_file() and relative not in allowed_files) or
                    (not member.is_file() and not member.is_dir())):
                raise ValueError("undeclared Browser artifact member")
        verify_browser_asset_references(artifact, assets)
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError("browser static policy mismatch") from exc


def verify_frontend_profile(artifact: Path, client: str, environment: str) -> None:
    profile_path = artifact / "runtime-profile.json"
    try:
        if profile_path.is_symlink() or not profile_path.is_file() or profile_path.stat().st_size > 4096:
            raise ValueError("invalid profile file")
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError(f"{client} runtime profile mismatch") from exc
    expected = {
        "client": client,
        "environment": environment,
        "backendUrl": PRODUCTION_BACKEND if environment == "production"
        else "" if client == "browser" else LOCAL_BACKEND,
    }
    if profile != expected or not isinstance(profile, dict) or set(profile) != set(expected):
        raise ValueError(f"{client} runtime profile mismatch")


def verify_desktop_renderer(artifact: Path, environment: str) -> None:
    try:
        manifest_path = artifact / "asset-manifest.json"
        if (manifest_path.is_symlink() or not manifest_path.is_file()
                or manifest_path.stat().st_size > 65536):
            raise ValueError("missing Desktop asset manifest")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        declared = manifest.get("assets") if isinstance(manifest, dict) else None
        if (not isinstance(manifest, dict) or set(manifest) != {"schemaVersion", "assets"}
                or manifest["schemaVersion"] != 1 or not isinstance(declared, list)
                or len(declared) > 1000 or declared != sorted(set(declared))
                or any(not isinstance(name, str) or
                       (name not in DESKTOP_PAGES and not DESKTOP_ASSET_NAME.fullmatch(name))
                       for name in declared)):
            raise ValueError("invalid Desktop asset manifest")
        assets_dir = artifact / "assets"
        if assets_dir.is_symlink() or not assets_dir.is_dir():
            raise ValueError("missing Desktop assets")
        actual = []
        for member in artifact.iterdir():
            if member.is_symlink():
                raise ValueError("Desktop symlink forbidden")
            if member == assets_dir:
                for asset in assets_dir.iterdir():
                    if asset.is_symlink() or not asset.is_file() or not DESKTOP_ASSET_NAME.fullmatch(f"assets/{asset.name}"):
                        raise ValueError("invalid Desktop asset")
                    actual.append(f"assets/{asset.name}")
            elif member.name in DESKTOP_PAGES:
                if not member.is_file():
                    raise ValueError("invalid Desktop page")
                actual.append(member.name)
            elif member.name not in {"asset-manifest.json", "frontend-version.json",
                                    "runtime-profile.json", "release-blocked.json"}:
                raise ValueError("undeclared Desktop file")
        if sorted(actual) != declared or not set(DESKTOP_PAGES).issubset(actual):
            raise ValueError("Desktop assets do not match manifest")
        for page, entry in DESKTOP_PAGES.items():
            file = artifact / page
            if file.stat().st_size > 1024 * 1024:
                raise ValueError("oversized Desktop page")
            html = file.read_text(encoding="utf-8")
            policy = f'<meta http-equiv="Content-Security-Policy" content="{DESKTOP_CSP}">'
            scripts = re.findall(r"<script\b([^>]*)>(.*?)</script>", html, re.I | re.S)
            if (html.count(policy) != 1 or html.index(policy) > html.lower().find("<script")
                    or re.search(r"\son[a-z]+\s*=|<style\b|\sstyle\s*=|<base\b|\bsrcset\s*=|\bsrcdoc\s*=", html, re.I)
                    or len(scripts) != len(re.findall(r"<script\b", html, re.I))
                    or any(body.strip() or not re.search(r"""\bsrc\s*=\s*(['"]).+?\1""", attributes)
                           for attributes, body in scripts)
                    or not any(re.search(rf"""\bsrc\s*=\s*(['"])\./assets/{entry}-[0-9a-f]+\.js\1""", attributes)
                               for attributes, _ in scripts)):
                raise ValueError("unsafe Desktop page")
            references = _html_references(html, all_tags=True)
            if (not any(re.fullmatch(rf"\./assets/{entry}-[0-9a-f]+\.js", ref) for ref in references)
                    or any(not ref.startswith("./assets/") or ref[2:] not in declared for ref in references)):
                raise ValueError("undeclared Desktop resource")
        expected_backend = PRODUCTION_BACKEND if environment == "production" else LOCAL_BACKEND
        other_backend = LOCAL_BACKEND if environment == "production" else PRODUCTION_BACKEND
        scripts = [artifact / name for name in declared if name.endswith(".js")]
        found_backend = False
        for script in scripts:
            if script.stat().st_size > 64 * 1024 * 1024:
                raise ValueError("oversized Desktop script")
            source = script.read_text(encoding="utf-8")
            found_backend |= expected_backend in source
            if other_backend in source or "pc-pc2l7vve:8082" in source:
                raise ValueError("Desktop backend URL crossed")
            static_imports = re.findall(r"\b(?:from\s*|import\s*)(['\"])([^'\"\\]+)\1", source)
            dynamic_imports = re.findall(r"\bimport\s*\(\s*(['\"])([^'\"\\]+)\1\s*\)", source)
            if (len(static_imports) != len(re.findall(r"\b(?:from\s*|import\s*)['\"]", source))
                    or len(dynamic_imports) != len(re.findall(r"\bimport\s*\(", source))):
                raise ValueError("dynamic Desktop module reference")
            for _, reference in [*static_imports, *dynamic_imports]:
                if (not re.fullmatch(r"\./[A-Za-z0-9][A-Za-z0-9._-]*\.js", reference)
                        or f"assets/{reference[2:]}" not in declared):
                    raise ValueError("undeclared Desktop module")
        if not found_backend:
            raise ValueError("Desktop backend URL missing")
        for stylesheet in (artifact / name for name in declared if name.endswith(".css")):
            if stylesheet.stat().st_size > 8 * 1024 * 1024:
                raise ValueError("oversized Desktop stylesheet")
            source = re.sub(r"/\*.*?\*/", "", stylesheet.read_text(encoding="utf-8"), flags=re.S)
            if re.search(r"@import\b", source, re.I) or "\\" in source:
                raise ValueError("Desktop stylesheet import forbidden")
            urls = re.findall(r"\burl\s*\(\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s)'\"(]+))\s*\)", source, re.I)
            if len(urls) != len(re.findall(r"\burl\s*\(", source, re.I)):
                raise ValueError("invalid Desktop stylesheet URL")
            for groups in urls:
                reference = next(value for value in groups if value)
                if (not re.fullmatch(r"(?:\./)?[A-Za-z0-9][A-Za-z0-9._-]*\.(?:svg|png|webp|woff2)", reference)
                        or f"assets/{reference.removeprefix('./')}" not in declared):
                    raise ValueError("undeclared Desktop stylesheet resource")
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        raise ValueError("desktop renderer artifact invalid") from exc


def verify_frontend_bundle_version(artifact: Path, component: str, version: str) -> None:
    try:
        scripts = (item for item in (artifact / "assets").iterdir() if item.suffix == ".js")
        quoted_version = json.dumps(version)
        for script in scripts:
            if script.is_symlink() or not script.is_file() or script.stat().st_size > 64 * 1024 * 1024:
                raise ValueError("invalid frontend script")
            if quoted_version in script.read_text(encoding="utf-8"):
                return
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError(f"{component} frontend bundle version mismatch") from exc
    raise ValueError(f"{component} frontend bundle version mismatch")


def verify_frontend_page_versions(artifact: Path, component: str, version: str) -> None:
    pages = BROWSER_DOCUMENTS if component == "browser" else DESKTOP_PAGES
    for page in pages:
        try:
            html = (artifact / page).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ValueError(f"{component} frontend page version mismatch") from exc
        declarations = [tag for tag in re.findall(r"<meta\b[^>]*>", html, re.I)
                        if re.search(r"\bname\s*=\s*(['\"])app-version\1", tag, re.I)]
        match = re.fullmatch(r'<meta\s+name="app-version"\s+content="([^"]+)"\s*/?>',
                             declarations[0], re.I) if len(declarations) == 1 else None
        if match is None or match.group(1) != version:
            raise ValueError(f"{component} frontend page version mismatch")


def verify_browser_bundle_backend(artifact: Path, environment: str) -> None:
    try:
        found_production = False
        for script in (artifact / "assets").iterdir():
            if script.suffix != ".js":
                continue
            if script.is_symlink() or not script.is_file() or script.stat().st_size > 64 * 1024 * 1024:
                raise ValueError("invalid Browser script")
            source = script.read_text(encoding="utf-8")
            found_production |= PRODUCTION_BACKEND in source
            if (LOCAL_BACKEND in source or "pc-pc2l7vve:8082" in source
                    or (environment == "test" and PRODUCTION_BACKEND in source)):
                raise ValueError("Browser backend URL crossed")
        if environment == "production" and not found_production:
            raise ValueError("Browser production backend URL missing")
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError("browser backend URL mismatch") from exc


def artifact_sha256(path: Path) -> str:
    if path.is_symlink() or not path.exists():
        raise ValueError(f"artifact unavailable or symlinked: {path}")
    digest = hashlib.sha256()
    if path.is_file():
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
    if not path.is_dir():
        raise ValueError(f"artifact is not a file or directory: {path}")
    files = sorted(path.rglob("*"), key=lambda item: item.relative_to(path).as_posix())
    for item in files:
        if item.is_symlink():
            raise ValueError(f"symlinked artifact member: {item}")
        if not item.is_file():
            continue
        relative_name = item.relative_to(path).as_posix().encode("utf-8")
        digest.update(len(relative_name).to_bytes(8, "big"))
        digest.update(relative_name)
        digest.update(item.stat().st_size.to_bytes(8, "big"))
        with item.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def verify_release_artifacts(
    manifest_path: Path,
    environment: str,
    browser_artifact: Path,
    desktop_artifact: Path,
    backend_artifact: Path,
) -> None:
    if environment not in ("test", "production"):
        raise ValueError("invalid release environment")
    if (manifest_path.is_symlink() or not manifest_path.is_file()
            or manifest_path.stat().st_size > 65536):
        raise ValueError("release manifest must be a regular bounded file")
    manifest_text = _read_regular_text(manifest_path, MAX_MANIFEST_BYTES)
    try:
        manifest = parse_release_manifest(manifest_text)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid release manifest schema") from exc
    if (not isinstance(manifest, dict) or set(manifest) != MANIFEST_FIELDS
            or type(manifest.get("schemaVersion")) is not int or manifest["schemaVersion"] != 1
            or not isinstance(manifest.get("frontendVersions"), dict)
            or set(manifest["frontendVersions"]) != {"browser", "desktop"}
            or not isinstance(manifest.get("artifactSha256"), dict)
            or set(manifest["artifactSha256"]) != ARTIFACT_FIELDS):
        raise ValueError("invalid release manifest schema")
    if manifest.get("environment") != environment:
        raise ValueError("release environment mismatch")
    artifact_paths = {
        "browser": browser_artifact,
        "desktop": desktop_artifact,
        "backend": backend_artifact,
    }
    if any(not artifact_path.is_dir() or artifact_path.is_symlink() for artifact_path in artifact_paths.values()):
        raise ValueError("release artifacts must be directories with embedded version metadata")
    if any(any(artifact_path.rglob("release-blocked.json")) for artifact_path in artifact_paths.values()):
        raise ValueError("scaffold artifact is not releasable")
    if (backend_artifact / "dist").exists() or (backend_artifact / "dist").is_symlink():
        raise ValueError("legacy Browser assets in backend artifact")
    if any(member.name.lower() == ".env" or member.name.lower().startswith(".env.")
           or member.name.lower().endswith(".env") or ".env." in member.name.lower()
           for artifact_path in artifact_paths.values() for member in artifact_path.rglob("*")):
        raise ValueError("environment file forbidden in release artifact")
    if any(not (backend_artifact / name).is_file() or (backend_artifact / name).is_symlink()
           for name in REQUIRED_BACKEND_FILES):
        raise ValueError("backend runtime file missing")
    frontend_metadata = {
        "browser": browser_artifact / "web/frontend-version.json",
        "desktop": desktop_artifact / "frontend-version.json",
    }
    actual_frontend_versions = {}
    for component, metadata_path in frontend_metadata.items():
        verify_frontend_profile(artifact_paths[component], component, environment)
        if not metadata_path.is_file() or metadata_path.is_symlink():
            raise ValueError(f"{component} frontend version metadata missing")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        actual_frontend_versions[component] = metadata.get("version") if isinstance(metadata, dict) else None
    backend_version_path = backend_artifact / "backend/VERSION"
    backend_version_text = _read_regular_text(backend_version_path, MAX_BACKEND_VERSION_BYTES)
    if backend_version_text is None:
        raise ValueError("backend version metadata must be a regular bounded file")
    backend_version = backend_version_text.strip()
    versions = manifest.get("frontendVersions")
    if (not isinstance(versions, dict)
            or not all(isinstance(versions.get(component), str) and VERSION_PATTERN.fullmatch(versions[component])
                       for component in ("browser", "desktop"))
            or any(versions[component] != actual_frontend_versions[component] for component in frontend_metadata)
            or not VERSION_PATTERN.fullmatch(backend_version)
            or manifest.get("backendVersion") != backend_version
            or not isinstance(manifest.get("programVersion"), str)
            or not VERSION_PATTERN.fullmatch(manifest["programVersion"])):
        raise ValueError("release version binding mismatch")
    if environment == "production" and not all(STABLE_VERSION_PATTERN.fullmatch(version) for version in (
            manifest["programVersion"], versions["browser"], versions["desktop"], backend_version)):
        raise ValueError("production versions must be stable releases")
    expected_hashes = manifest.get("artifactSha256")
    if not isinstance(expected_hashes, dict):
        raise ValueError("release artifact hashes missing")
    for component, artifact_path in artifact_paths.items():
        expected_hash = expected_hashes.get(component)
        if not isinstance(expected_hash, str) or not SHA256_PATTERN.fullmatch(expected_hash):
            raise ValueError(f"invalid {component} artifact hash")
        if artifact_sha256(artifact_path) != expected_hash:
            raise ValueError(f"{component} artifact hash mismatch")
    verify_browser_static_policy(browser_artifact)
    verify_desktop_renderer(desktop_artifact, environment)
    for component, artifact_path in (("browser", browser_artifact), ("desktop", desktop_artifact)):
        verify_frontend_page_versions(artifact_path, component, versions[component])
        verify_frontend_bundle_version(artifact_path, component, versions[component])
    verify_browser_bundle_backend(browser_artifact, environment)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--environment", choices=("test", "production"), required=True)
    parser.add_argument("--browser-artifact", type=Path, required=True)
    parser.add_argument("--desktop-artifact", type=Path, required=True)
    parser.add_argument("--backend-artifact", type=Path, required=True)
    args = parser.parse_args()
    verify_release_artifacts(
        args.manifest, args.environment, args.browser_artifact,
        args.desktop_artifact, args.backend_artifact,
    )
    print("release artifact hashes and component versions verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
