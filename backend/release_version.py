import json
import os
import re
import stat
from pathlib import Path


RELEASE_MANIFEST = Path(__file__).resolve().parent.parent / "release-manifest.json"
BACKEND_VERSION_FILE = Path(__file__).resolve().parent / "VERSION"
PROGRAM_VERSION_FILE = Path(__file__).resolve().parent / "program-version.json"
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
STABLE_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
MANIFEST_FIELDS = {"schemaVersion", "environment", "programVersion", "frontendVersions", "backendVersion", "artifactSha256"}
ARTIFACT_FIELDS = {"browser", "desktop", "backend"}
MAX_MANIFEST_BYTES = 65536
MAX_BACKEND_VERSION_BYTES = 256


def _valid_version(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    version = value.strip()
    return version if VERSION_PATTERN.fullmatch(version) else None


def _exact_version(value: object) -> str | None:
    return value if isinstance(value, str) and VERSION_PATTERN.fullmatch(value) else None


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate release manifest key")
        result[key] = value
    return result


def parse_release_manifest(source: str) -> object:
    return json.loads(source, object_pairs_hook=_unique_object)


def _read_regular_text(path: Path, max_bytes: int) -> str | None:
    try:
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > max_bytes:
            return None
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if (not stat.S_ISREG(opened.st_mode) or opened.st_size > max_bytes
                    or (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino)):
                return None
            content = stream.read(max_bytes + 1)
        return content.decode("utf-8") if len(content) <= max_bytes else None
    except (OSError, UnicodeError):
        return None


def read_backend_source_version(path: Path = BACKEND_VERSION_FILE) -> str:
    return _valid_version(_read_regular_text(path, MAX_BACKEND_VERSION_BYTES)) or "unmarked"


def read_release_version(
    manifest_path: Path = RELEASE_MANIFEST,
    backend_version_path: Path = BACKEND_VERSION_FILE,
    runtime_environment: str | None = None,
) -> dict[str, object]:
    frontend_versions: dict[str, str | None] = {"browser": None, "desktop": None}
    result: dict[str, object] = {
        "programVersion": None,
        "frontendVersions": frontend_versions,
        "backendVersion": None,
    }
    result["backendVersion"] = _valid_version(_read_regular_text(backend_version_path, MAX_BACKEND_VERSION_BYTES))
    try:
        manifest = parse_release_manifest(_read_regular_text(manifest_path, MAX_MANIFEST_BYTES))
    except (TypeError, ValueError):
        return result
    if not isinstance(manifest, dict):
        return result
    result["programVersion"] = _exact_version(manifest.get("programVersion"))
    versions = manifest.get("frontendVersions")
    if isinstance(versions, dict):
        for client_type in frontend_versions:
            frontend_versions[client_type] = _exact_version(versions.get(client_type))
    artifacts = manifest.get("artifactSha256")
    valid_artifacts = isinstance(artifacts, dict) and set(artifacts) == ARTIFACT_FIELDS and all(
        isinstance(artifacts.get(component), str) and SHA256_PATTERN.fullmatch(artifacts[component])
        for component in ARTIFACT_FIELDS
    )
    active_environment = runtime_environment if runtime_environment is not None else os.getenv("AI00_DEPLOY_PROFILE", "")
    if (set(manifest) != MANIFEST_FIELDS or not isinstance(versions, dict)
            or set(versions) != {"browser", "desktop"}
            or not all(frontend_versions.values()) or not result["backendVersion"]
            or manifest.get("backendVersion") != result["backendVersion"]
            or type(manifest.get("schemaVersion")) is not int or manifest["schemaVersion"] != 1
            or manifest.get("environment") not in ("test", "production")
            or manifest.get("environment") != active_environment
            or (active_environment == "production" and not all(
                STABLE_VERSION_PATTERN.fullmatch(version)
                for version in (result["programVersion"], *frontend_versions.values(), result["backendVersion"])
                if version is not None
            ))
            or not valid_artifacts):
        result["programVersion"] = None
    return result


def read_system_version(
    manifest_path: Path = RELEASE_MANIFEST,
    backend_version_path: Path = BACKEND_VERSION_FILE,
    program_version_path: Path = PROGRAM_VERSION_FILE,
    runtime_environment: str | None = None,
) -> dict[str, object]:
    """Report an explicit development combination without claiming a release."""
    environment = runtime_environment if runtime_environment is not None else os.getenv("AI00_DEPLOY_PROFILE", "")
    result = read_release_version(manifest_path, backend_version_path, environment)
    result['versionSource'] = 'release' if result['programVersion'] else None
    if result['programVersion'] or environment:
        return result
    try:
        source = parse_release_manifest(_read_regular_text(program_version_path, MAX_MANIFEST_BYTES))
    except (TypeError, ValueError):
        return result
    if (not isinstance(source, dict)
            or set(source) != {'programVersion', 'frontendVersions', 'backendVersion'}
            or not _exact_version(source['programVersion'])
            or not result['backendVersion'] or source['backendVersion'] != result['backendVersion']
            or not isinstance(source['frontendVersions'], dict)
            or set(source['frontendVersions']) != {'browser', 'desktop'}
            or not all(_exact_version(value) for value in source['frontendVersions'].values())):
        return result
    result.update(source)
    result['versionSource'] = 'development'
    return result


