"""Generate live RC evidence for eleven-domain database grant isolation."""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.capability_v2.database_isolation import (
    DatabaseIsolationError,
    load_probe_targets,
    verify_database_grants,
)


def _head(root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()


def _required(environ: Mapping[str, str], name: str) -> str:
    value = str(environ.get(name, "")).strip()
    if not value:
        raise DatabaseIsolationError(f"missing:{name}")
    return value


def _load_provider_evidence(
    path: Path,
    *,
    domain_ids: set[str],
    environment_id: str,
    run_id: str,
    git_commit: str,
) -> dict[str, str]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise DatabaseIsolationError("provider_crud_evidence_unreadable") from exc
    if document.get("schema_version") != 1:
        raise DatabaseIsolationError("provider_crud_evidence_schema_mismatch")
    if document.get("environment_id") != environment_id:
        raise DatabaseIsolationError("provider_crud_evidence_environment_mismatch")
    if document.get("run_id") != run_id:
        raise DatabaseIsolationError("provider_crud_evidence_run_mismatch")
    if document.get("git_commit") != git_commit:
        raise DatabaseIsolationError("provider_crud_evidence_commit_mismatch")
    domains = document.get("domains", {})
    if set(domains) != domain_ids or any(value != "passed" for value in domains.values()):
        raise DatabaseIsolationError(
            "provider_crud_evidence_requires_exactly_eleven_passed_domains"
        )
    return domains


def main(
    argv: Sequence[str] | None = None,
    *,
    root: Path = ROOT,
    environ: Mapping[str, str] = os.environ,
    connect: Callable | None = None,
    git_commit: Callable[[], str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    environment_id = _required(environ, "AI00_ACCEPTANCE_ENVIRONMENT_ID")
    run_id = _required(environ, "AI00_ACCEPTANCE_RUN_ID")
    ca_path = _required(environ, "AI00_ACCEPTANCE_OCEANBASE_SSL_CA")
    commit = (git_commit or (lambda: _head(root)))()
    targets = load_probe_targets(root)
    domain_ids = {target.domain_id for target in targets}
    _load_provider_evidence(
        args.provider_evidence,
        domain_ids=domain_ids,
        environment_id=environment_id,
        run_id=run_id,
        git_commit=commit,
    )

    kwargs = {"ca_path": ca_path}
    if connect is not None:
        kwargs["connect"] = connect
    isolation = verify_database_grants(targets, environ, **kwargs)
    isolation["owner_operations"] = {
        domain_id: {"provider_crud": "passed", **result}
        for domain_id, result in isolation["owner_operations"].items()
    }
    document = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "environment_id": environment_id,
        "run_id": run_id,
        "git_commit": commit,
        "database_isolation": isolation,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(args.output)
    print(
        json.dumps(
            {
                "domains": len(isolation["owner_operations"]),
                "cross_domain_pairs": len(isolation["cross_domain"]),
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DatabaseIsolationError, subprocess.CalledProcessError) as exc:
        print(f"database isolation verification failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
