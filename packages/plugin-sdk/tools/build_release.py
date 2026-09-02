"""Build a deterministic AI00 Web Plugin ZIP and detached Manifest v2 release envelope."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath

PLUGIN_ID = re.compile(r"^[a-z][a-z0-9]*(?:\.[a-z][a-z0-9-]*){2,7}$")
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
FIXED_TIME = (2026, 1, 1, 0, 0, 0)
SDK_ASSET_NAME = "ai00-plugin-sdk.js"


def descriptor(source: Path, version_override: str | None = None) -> dict:
    path = source / "plugin.json"
    if not path.is_file():
        raise ValueError("plugin source must contain plugin.json at its root")
    value = json.loads(path.read_text(encoding="utf-8"))
    required = {"schema_version", "plugin_id", "publisher_id", "name", "version", "compatibility", "runtimes", "permissions"}
    missing = sorted(required - set(value))
    if missing:
        raise ValueError(f"plugin.json is missing: {', '.join(missing)}")
    if "artifact" in value:
        raise ValueError("plugin.json must not contain the detached artifact envelope")
    if value["schema_version"] != "2.0" or not PLUGIN_ID.fullmatch(str(value["plugin_id"])):
        raise ValueError("plugin.json must use schema 2.0 and a reverse-DNS plugin_id")
    if version_override is not None:
        value["version"] = version_override
    if not SEMVER.fullmatch(str(value["version"])):
        raise ValueError("plugin version must be SemVer")
    if not str(value["plugin_id"]).startswith(str(value["publisher_id"]) + "."):
        raise ValueError("plugin_id must belong to publisher_id")
    permissions = value.get("permissions", [])
    if not isinstance(permissions, list) or len(permissions) != len(set(permissions)):
        raise ValueError("permissions must be a unique list")
    value["permissions"] = sorted(permissions)
    # Emit optional fields with their canonical server defaults before signing.
    # Otherwise the server's strict Manifest model adds them after upload and
    # verifies a different byte sequence than the publisher signed.
    value.setdefault("capabilities", {"required": [], "optional": []})
    value.setdefault("plugins", {"required": [], "optional": []})
    web = value.get("runtimes", {}).get("web", {})
    entry = PurePosixPath(str(web.get("entry", "")))
    if not str(entry) or entry.is_absolute() or ".." in entry.parts or not (source / entry).is_file():
        raise ValueError("web runtime entry must be a safe file inside the package")
    return value


def source_files(source: Path, output: Path) -> list[tuple[Path, str]]:
    result = []
    for path in sorted(source.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_dir():
            continue
        if path.is_symlink() or stat.S_ISLNK(path.lstat().st_mode):
            raise ValueError(f"symbolic links are forbidden: {path}")
        if output == path or output in path.parents:
            continue
        relative = path.relative_to(source).as_posix()
        parts = PurePosixPath(relative).parts
        if any(part in {".git", "__pycache__", "dist"} for part in parts):
            continue
        if any(part.startswith(".") for part in parts):
            continue
        result.append((path, relative))
    return result


def build(source: Path, output_dir: Path, version_override: str | None = None) -> tuple[Path, Path, dict]:
    source = source.resolve()
    output_dir = output_dir.resolve()
    value = descriptor(source, version_override)
    output_dir.mkdir(parents=True, exist_ok=True)
    basename = f"{value['plugin_id']}-{value['version']}"
    package_path = output_dir / f"{basename}.zip"
    files = source_files(source, output_dir)
    if not files or not any(name == "plugin.json" for _, name in files):
        raise ValueError("plugin package is empty or missing plugin.json")
    if any(name == SDK_ASSET_NAME for _, name in files):
        raise ValueError(f"{SDK_ASSET_NAME} is supplied by the AI00 build tool and must not exist in plugin source")
    sdk_path = Path(__file__).resolve().parents[1] / "src" / "index.js"
    if not sdk_path.is_file():
        raise ValueError("AI00 Plugin SDK runtime is missing")
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, name in files:
            info = zipfile.ZipInfo(name, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            info.create_system = 3
            content = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8") if name == "plugin.json" else path.read_bytes()
            archive.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        sdk_info = zipfile.ZipInfo(SDK_ASSET_NAME, FIXED_TIME)
        sdk_info.compress_type = zipfile.ZIP_DEFLATED
        sdk_info.external_attr = 0o100644 << 16
        sdk_info.create_system = 3
        archive.writestr(sdk_info, sdk_path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    data = package_path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    release = dict(value)
    release["artifact"] = {
        "object_key": f"plugins/{value['publisher_id']}/{value['plugin_id']}/{value['version']}/{digest}.zip",
        "sha256": digest,
        "size": len(data),
        "media_type": "application/zip",
    }
    release_path = output_dir / f"{basename}.release.json"
    release_path.write_text(json.dumps(release, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return package_path, release_path, release


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--version", help="Build an immutable test/upgrade version without editing the source descriptor.")
    args = parser.parse_args()
    package, release, value = build(args.source, args.output_dir, args.version)
    print(json.dumps({"package": str(package), "release": str(release), "sha256": value["artifact"]["sha256"], "size": value["artifact"]["size"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
