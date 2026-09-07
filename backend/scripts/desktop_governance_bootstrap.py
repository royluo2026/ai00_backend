"""Immutable Git bootstrap, run via python -I -S before importing application code.

Load this file from a fixed Git blob (the release gate's isolated command does
so). A normal Python startup may already have executed sitecustomize; this
script cannot undo that and therefore refuses non-isolated startup.
"""
import sys

if not sys.flags.isolated or not sys.flags.no_site:
    raise SystemExit("isolated_bootstrap_required: use the documented fixed Git blob entry")

import argparse
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--bootstrap-commit", default=globals().get("BOOTSTRAP_COMMIT"))
    args, generator_args = parser.parse_known_args()
    if not args.bootstrap_commit:
        raise SystemExit("fixed_bootstrap_commit_required")
    root = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
    commit = subprocess.check_output(["git", "rev-parse", "--verify", f"{args.bootstrap_commit}^{{commit}}"],
        cwd=root, text=True).strip()
    name = "backend/scripts/build_desktop_app_governance.py"
    blob = subprocess.check_output(["git", "show", f"{commit}:{name}"], cwd=root)
    # The fixed implementation retains the original repository as its Git
    # object source/output directory; no working-directory Python is imported.
    implementation = {"__name__": "committed_desktop_generator", "__file__": str(root / name)}
    exec(compile(blob, f"{commit}:{name}", "exec"), implementation)
    if "--write" in generator_args and "--source-revision" not in generator_args:
        generator_args.extend(("--source-revision", commit))
    return implementation["main"](generator_args)


if __name__ == "__main__":
    raise SystemExit(main())
