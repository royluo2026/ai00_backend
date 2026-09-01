#!/usr/bin/env python3
"""Generate or verify the Capability V2 human and machine developer manual."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.capability_v2.catalog import load_catalog_release
from backend.capability_v2.docs.generator import generated_files


DEFAULT_CATALOG = ROOT / "docs/governance/capability-catalog-release.json"
DEFAULT_OUTPUT = ROOT / "docs/capabilities"


def _actual_files(root: Path) -> dict[str, str]:
    if not root.is_dir():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in root.rglob("*") if path.is_file()
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--catalog-release")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    release = load_catalog_release(args.catalog.read_text(encoding="utf-8"))
    if args.catalog_release and args.catalog_release != release.release_id:
        print(f"catalog release mismatch: requested {args.catalog_release}, found {release.release_id}")
        return 1
    expected = generated_files(release)
    if args.check:
        actual = _actual_files(args.output)
        if actual != expected:
            missing = sorted(set(expected) - set(actual))
            extra = sorted(set(actual) - set(expected))
            changed = sorted(name for name in set(actual) & set(expected) if actual[name] != expected[name])
            print(f"Capability docs drift: missing={missing}, extra={extra}, changed={changed}")
            return 1
        print(f"Capability docs check passed: {release.release_id}, {len(release.descriptors)} pages")
        return 0
    args.output.mkdir(parents=True, exist_ok=True)
    # Remove only paths declared by the previous generated manifest. Never
    # delete an untracked/manual file merely because it shares this directory.
    manifest_path = args.output / ".generated-manifest.json"
    if manifest_path.is_file():
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        root = args.output.resolve()
        for relative in previous.get("files", ()):
            path = (args.output / str(relative)).resolve()
            if path != root and root in path.parents and path.is_file():
                path.unlink()
    for relative, content in expected.items():
        path = args.output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
    print(f"Capability docs written: {release.release_id}, {len(release.descriptors)} pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
