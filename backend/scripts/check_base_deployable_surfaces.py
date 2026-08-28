"""Scan every deployable Base web/Electron root for retired authority paths."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
from typing import Any


ROOTS = ("dist-production/packages", "dist-production/web", "packages/core/electron")
PATTERNS = {
    "retired_electron_url_install": ("install-plugin-url", "installPluginFromUrl", "installFromUrl(", "/bridge/plugin/install_plugin"),
    "retired_electron_destructive_uninstall": ("uninstall-user-plugin", "uninstallUserPlugin", ".uninstall(", "/bridge/plugin/uninstall_plugin"),
    "stale_saved_view_rest": ("/api/views",),
    "stale_annotation_rest": ("/api/self_ann",),
    "stale_identity_rest": ("/api/users/me",),
    "silent_saved_view_local_authority": ("localStorage.getItem('ai00_saved_views", 'localStorage.getItem("ai00_saved_views'),
}


def build_report(frontend: Path) -> dict[str, Any]:
    frontend = frontend.resolve()
    findings: list[dict[str, str]] = []
    scanned = 0
    for relative_root in ROOTS:
        root = frontend / relative_root
        if not root.is_dir():
            findings.append({"code": "missing_deployable_root", "path": relative_root, "token": ""})
            continue
        for path in sorted(item for item in root.rglob("*") if item.is_file() and item.suffix.lower() in {".js", ".mjs", ".cjs", ".html"}):
            scanned += 1
            text = path.read_text(encoding="utf-8", errors="replace")
            for code, tokens in PATTERNS.items():
                electron_check = code.startswith("retired_electron") and relative_root == "packages/core/electron"
                web_check = not code.startswith("retired_electron") and relative_root.startswith("dist-production")
                if electron_check or web_check:
                    for token in tokens:
                        if token in text:
                            findings.append({"code": code, "path": path.relative_to(frontend).as_posix(), "token": token})
    revision = subprocess.run(["git", "-C", str(frontend), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    return {"schema_version": 1, "frontend_revision": revision, "roots": list(ROOTS),
            "scanned_files": scanned, "findings": findings}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frontend", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_report(args.frontend)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 1 if report["findings"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
