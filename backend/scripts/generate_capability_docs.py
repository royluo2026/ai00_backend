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


def _write_changed_files(root: Path, expected: dict[str, str]) -> tuple[int, int]:
    """Update generated docs without rewriting files whose content is unchanged."""
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / ".generated-manifest.json"
    previous_files: set[str] = set()
    if manifest_path.is_file():
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        previous_files = {str(value) for value in previous.get("files", ())}

    resolved_root = root.resolve()
    removed = 0
    for relative in sorted(previous_files - set(expected)):
        path = (root / relative).resolve()
        if path != resolved_root and resolved_root in path.parents and path.is_file():
            path.unlink()
            removed += 1

    written = 0
    for relative, content in expected.items():
        path = root / relative
        if path.is_file() and path.read_text(encoding="utf-8") == content:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        written += 1
    return written, removed


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
    written, removed = _write_changed_files(args.output, expected)
    print(
        f"Capability docs synchronized: {release.release_id}, "
        f"{len(release.descriptors)} pages, written={written}, removed={removed}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
