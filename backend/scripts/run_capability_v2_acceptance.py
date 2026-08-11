#!/usr/bin/env python3
"""Run fail-closed Capability V2 acceptance and emit a release-bound report."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
CATALOG_PATH = ROOT / "docs/capabilities/catalog.v2.json"
MANIFEST_PATH = ROOT / "backend/tests/acceptance/fixtures/case-manifest.json"
REPORT_SCHEMA_PATH = ROOT / "docs/acceptance/capability-v2-report.schema.json"
RC_EVIDENCE_SCHEMA_PATH = ROOT / "docs/acceptance/capability-v2-rc-evidence.schema.json"
MANDATORY_CASES = {
    "success", "invalid_input", "unauthenticated", "resource_denied",
    "output_contract", "consumer_contract", "version_pin",
}
RC_URLS = {
    "ois": "AI00_ACCEPTANCE_OIS_HEALTH_URL",
    "jwt": "AI00_ACCEPTANCE_JWT_DISCOVERY_URL",
    "oauth": "AI00_ACCEPTANCE_OAUTH_DISCOVERY_URL",
    "local_runtime": "AI00_ACCEPTANCE_LOCAL_RUNTIME_HEALTH_URL",
}


def load_documents() -> tuple[dict, dict]:
    return (
        json.loads(CATALOG_PATH.read_text(encoding="utf-8")),
        json.loads(MANIFEST_PATH.read_text(encoding="utf-8")),
    )


def validate_manifest(catalog: dict, manifest: dict) -> list[str]:
    errors: list[str] = []
    if manifest.get("catalog_release") != catalog.get("release_id"):
        errors.append("manifest catalog release mismatch")
    declared = manifest.get("capabilities", {})
    if set(manifest.get("mandatory_cases", ())) != MANDATORY_CASES:
        errors.append("manifest mandatory_cases must equal the seven supported case types")
    stable = {
        f'{item["id"]}@{item["major_version"]}'
        for item in catalog.get("capabilities", [])
        if item.get("lifecycle_status") == "stable"
    }
    for capability_key in sorted(stable):
        cases = declared.get(capability_key, {})
        missing = MANDATORY_CASES - set(cases)
        for case in sorted(missing):
            errors.append(f"{capability_key}: missing mandatory case {case}")
        for unknown in sorted(set(cases) - MANDATORY_CASES):
            errors.append(f"{capability_key}: unknown mandatory case {unknown}")
        nodes = list(cases.values()) if isinstance(cases, dict) else []
        if len(nodes) != len(set(nodes)):
            errors.append(f"{capability_key}: verifier node ids must be unique")
        if any(not isinstance(node, str) or "::test_" not in node for node in nodes):
            errors.append(f"{capability_key}: every mandatory case requires an executable pytest node id")
    for extra in sorted(set(declared) - stable):
        errors.append(f"{extra}: manifest entry is not an exact stable capability")
    return errors


def _http_json_probe(name: str, value: str, environment_id: str, env: dict[str, str]) -> str | None:
    parsed = urlparse(value)
    local_host = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (name == "local_runtime" and parsed.scheme == "http" and local_host):
        return f"{name} health probe requires HTTPS"
    try:
        request = Request(value, method="GET", headers={"User-Agent": "ai00-capability-acceptance/1"})
        with urlopen(request, timeout=10) as response:
            if not 200 <= response.status < 400:
                return f"{name} health probe returned HTTP {response.status}"
            final = urlparse(response.geturl())
            if (final.scheme, final.hostname, final.port) != (parsed.scheme, parsed.hostname, parsed.port):
                return f"{name} health probe redirected across origin"
            document = json.loads(response.read(1024 * 1024).decode("utf-8"))
    except Exception as exc:
        return f"{name} health probe failed: {type(exc).__name__}"
    if not isinstance(document, dict):
        return f"{name} health probe returned a non-object document"
    if name in {"jwt", "oauth"}:
        expected_issuer = env.get(f"AI00_ACCEPTANCE_{name.upper()}_ISSUER", "").strip()
        if not expected_issuer or document.get("issuer") != expected_issuer:
            return f"{name} discovery issuer mismatch"
        if urlparse(str(document.get("jwks_uri") or "")).scheme != "https":
            return f"{name} discovery requires an HTTPS jwks_uri"
    elif name == "ois":
        if document.get("service") != "ois" or document.get("environment_id") != environment_id:
            return "ois service identity or environment mismatch"
    elif name == "local_runtime":
        if (
            document.get("service") != "ai00-local-runtime"
            or document.get("protocol") != "ai00.local-operation.v2"
            or document.get("environment_id") != environment_id
        ):
            return "local_runtime service identity, protocol, or environment mismatch"
    return None


def _oceanbase_probe(value: str, ca_path: str) -> str | None:
    parsed = urlparse(value)
    if parsed.scheme not in {"mysql", "mysql+pymysql"} or not parsed.hostname or not parsed.path.strip("/"):
        return "oceanbase URL is invalid"
    if not ca_path or not Path(ca_path).is_file():
        return "oceanbase TLS CA is missing"
    try:
        import pymysql
        from backend.db.migration_readiness import assert_migrations_applied

        connection = pymysql.connect(
            host=parsed.hostname, port=parsed.port or 2881,
            user=unquote(parsed.username or ""), password=unquote(parsed.password or ""),
            database=parsed.path.strip("/"), connect_timeout=10,
            cursorclass=pymysql.cursors.DictCursor,
            ssl={"ca": ca_path, "check_hostname": True},
        )
        try:
            assert_migrations_applied(connection)
        finally:
            connection.close()
    except Exception as exc:
        return f"oceanbase probe failed: {type(exc).__name__}"
    return None


def environment_errors(mode: str, env: dict[str, str], *, probe: bool = True) -> list[str]:
    if mode == "offline":
        return []
    errors: list[str] = []
    if not env.get("AI00_ACCEPTANCE_ENVIRONMENT_ID", "").strip():
        errors.append("missing AI00_ACCEPTANCE_ENVIRONMENT_ID")
    for component in ("AGENT", "MCP", "LOCAL_RUNTIME"):
        if env.get(f"AI00_ACCEPTANCE_{component}_RESULT") != "passed":
            errors.append(f"AI00_ACCEPTANCE_{component}_RESULT must be passed")
    if mode == "nightly":
        return errors
    if not env.get("AI00_ACCEPTANCE_RUN_ID", "").strip():
        errors.append("missing AI00_ACCEPTANCE_RUN_ID")
    oceanbase = env.get("AI00_ACCEPTANCE_OCEANBASE_URL", "").strip()
    if not oceanbase:
        errors.append("missing AI00_ACCEPTANCE_OCEANBASE_URL")
    ca_path = env.get("AI00_ACCEPTANCE_OCEANBASE_SSL_CA", "").strip()
    if not ca_path:
        errors.append("missing AI00_ACCEPTANCE_OCEANBASE_SSL_CA")
    for name in ("JWT", "OAUTH"):
        if not env.get(f"AI00_ACCEPTANCE_{name}_ISSUER", "").strip():
            errors.append(f"missing AI00_ACCEPTANCE_{name}_ISSUER")
    environment_id = env.get("AI00_ACCEPTANCE_ENVIRONMENT_ID", "").strip()
    for name, variable in RC_URLS.items():
        value = env.get(variable, "").strip()
        if not value:
            errors.append(f"missing {variable}")
        elif probe:
            failure = _http_json_probe(name, value, environment_id, env)
            if failure:
                errors.append(failure)
    if oceanbase and probe:
        failure = _oceanbase_probe(oceanbase, ca_path)
        if failure:
            errors.append(failure)
    return errors


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, text=True, capture_output=True, check=True,
    ).stdout.strip()


def _migration_binding() -> dict:
    candidates = sorted((ROOT / "backend/db/migrations").glob("*.sql"))
    latest = candidates[-1]
    return {
        "migration_id": latest.name.split("_", 1)[0],
        "filename": latest.name,
        "sha256": "sha256:" + hashlib.sha256(latest.read_bytes()).hexdigest(),
    }


def catalog_integrity_errors(catalog: dict) -> list[str]:
    from backend.capability_v2.catalog import CatalogRelease
    from backend.capability_v2.docs.generator import build_documentation

    release_document = json.loads(
        (ROOT / "docs/governance/capability-catalog-release.json").read_text(encoding="utf-8")
    )
    try:
        release = CatalogRelease.model_validate(release_document)
    except Exception as exc:
        return [f"catalog release integrity failed: {type(exc).__name__}"]
    errors = []
    if (catalog.get("release_id"), catalog.get("catalog_hash")) != (release.release_id, release.catalog_hash):
        errors.append("developer catalog release/hash differs from immutable release")
    expected_catalog = build_documentation(release).machine_catalog
    if catalog != expected_catalog:
        errors.append("developer catalog projection differs from immutable release")
    return errors


def validate_runtime_evidence(catalog: dict, manifest: dict, env: dict[str, str]) -> tuple[list[str], str | None]:
    from jsonschema import Draft202012Validator, FormatChecker

    value = env.get("AI00_ACCEPTANCE_RC_EVIDENCE", "").strip()
    if not value:
        return ["missing AI00_ACCEPTANCE_RC_EVIDENCE"], None
    path = Path(value)
    if not path.is_file():
        return ["AI00_ACCEPTANCE_RC_EVIDENCE is not a readable file"], None
    raw = path.read_bytes()
    try:
        evidence = json.loads(raw)
    except Exception:
        return ["AI00_ACCEPTANCE_RC_EVIDENCE is not valid JSON"], None
    evidence_hash = "sha256:" + hashlib.sha256(raw).hexdigest()
    schema = json.loads(RC_EVIDENCE_SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = [
        f"RC evidence schema: {error.message}"
        for error in Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(evidence)
    ]
    if errors:
        return errors, evidence_hash
    if evidence.get("catalog_release") != catalog.get("release_id"):
        errors.append("RC evidence catalog release mismatch")
    if evidence.get("catalog_hash") != catalog.get("catalog_hash"):
        errors.append("RC evidence catalog hash mismatch")
    if evidence.get("environment_id") != env.get("AI00_ACCEPTANCE_ENVIRONMENT_ID"):
        errors.append("RC evidence environment mismatch")
    if evidence.get("run_id") != env.get("AI00_ACCEPTANCE_RUN_ID"):
        errors.append("RC evidence run identity mismatch")
    try:
        expected_commit = _git("rev-parse", "HEAD")
    except subprocess.CalledProcessError:
        expected_commit = ""
    if evidence.get("git_commit") != expected_commit:
        errors.append("RC evidence git commit mismatch")
    if evidence.get("migration") != _migration_binding():
        errors.append("RC evidence migration binding mismatch")
    if evidence.get("provider_artifacts") != catalog.get("provider_artifacts", []):
        errors.append("RC evidence provider artifact binding mismatch")
    try:
        generated_at = datetime.fromisoformat(evidence["generated_at"].replace("Z", "+00:00"))
    except (TypeError, ValueError):
        errors.append("RC evidence generation time cannot be parsed safely")
    else:
        now = datetime.now(UTC)
        if generated_at < now - timedelta(hours=6) or generated_at > now + timedelta(minutes=5):
            errors.append("RC evidence generation time is stale or in the future")
    results = evidence.get("capabilities", {})
    for capability_key, cases in manifest.get("capabilities", {}).items():
        actual = results.get(capability_key, {})
        for case in cases:
            if actual.get(case) != "passed":
                errors.append(f"{capability_key}: RC runtime case {case} is not passed")
    for extra in sorted(set(results) - set(manifest.get("capabilities", {}))):
        errors.append(f"{extra}: RC evidence is not an exact stable capability")
    return errors, evidence_hash


def evaluate_case_outcomes(manifest: dict, outcomes: dict[str, str]) -> tuple[dict[str, int], list[str]]:
    expected = {
        node: (capability_key, case)
        for capability_key, cases in manifest.get("capabilities", {}).items()
        for case, node in cases.items()
    }
    blockers = []
    counts = {"passed": 0, "failed": 0, "skipped": 0, "missing": 0}
    for node, (capability_key, case) in expected.items():
        outcome = outcomes.get(node, "missing")
        if outcome == "passed":
            counts["passed"] += 1
        elif outcome in {"skipped", "xfailed"}:
            counts["skipped"] += 1
            blockers.append(f"{capability_key}: mandatory case {case} was {outcome}")
        elif outcome == "missing":
            counts["missing"] += 1
            blockers.append(f"{capability_key}: mandatory case {case} was not collected")
        else:
            counts["failed"] += 1
            blockers.append(f"{capability_key}: mandatory case {case} was {outcome}")
    return counts, blockers


def _run_contract_tests(manifest: dict) -> tuple[dict, list[str]]:
    with tempfile.TemporaryDirectory(prefix="ai00-capability-acceptance-") as directory:
        result_path = Path(directory) / "outcomes.json"
        command = [
            sys.executable, "-m", "pytest", "backend/tests/acceptance", "-q",
            "-p", "backend.tests.acceptance.outcome_plugin",
        ]
        process_env = dict(os.environ)
        process_env["AI00_ACCEPTANCE_RESULT_PATH"] = str(result_path)
        completed = subprocess.run(command, cwd=ROOT, env=process_env, text=True, capture_output=True, check=False)
        combined = "\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part.strip())
        summary = next(
            (line for line in reversed(combined.splitlines()) if re.search(r"\b(passed|failed|skipped|error)s?\b", line)),
            "no pytest summary",
        )
        payload = json.loads(result_path.read_text(encoding="utf-8")) if result_path.is_file() else {"outcomes": {}}
    outcomes = payload.get("outcomes", {})
    counts, blockers = evaluate_case_outcomes(manifest, outcomes)
    if completed.returncode != 0 and not blockers:
        blockers.append(f"acceptance pytest failed with exit code {completed.returncode}")
    return {
        "exit_code": completed.returncode,
        "summary": summary,
        "command": " ".join(command),
        "outcome_counts": counts,
    }, blockers


def build_report(mode: str, catalog: dict, manifest: dict, blockers: list[str], test_result: dict, *, runtime_evidence_hash: str | None = None) -> dict:
    commit = _git("rev-parse", "HEAD")
    clean = not bool(_git("status", "--porcelain", "--untracked-files=no"))
    stable_count = len(manifest.get("capabilities", {}))
    declared_cases = sum(len(value) for value in manifest.get("capabilities", {}).values())
    counts = test_result["outcome_counts"]
    status = "passed" if not blockers and test_result["exit_code"] == 0 and counts["passed"] == declared_cases else "failed"
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": mode,
        "status": status,
        "git_commit": commit,
        "working_tree_clean": clean,
        "catalog_release": catalog["release_id"],
        "catalog_hash": catalog["catalog_hash"],
        "schema_hashes": {
            f'{item["id"]}@{item["major_version"]}': item["schema_hash"]
            for item in catalog["capabilities"]
        },
        "migration": _migration_binding(),
        "provider_artifacts": catalog.get("provider_artifacts", []),
        "environment_id": os.environ.get("AI00_ACCEPTANCE_ENVIRONMENT_ID", f"offline:{socket.gethostname()}"),
        "validation_scope": "runtime_e2e" if mode == "release-candidate" else "contract",
        "runtime_evidence_hash": runtime_evidence_hash,
        "component_results": {
            "agent": os.environ.get("AI00_ACCEPTANCE_AGENT_RESULT", "not_run"),
            "mcp": os.environ.get("AI00_ACCEPTANCE_MCP_RESULT", "not_run"),
            "local_runtime": os.environ.get("AI00_ACCEPTANCE_LOCAL_RUNTIME_RESULT", "not_run"),
        },
        "cases": {
            "stable_capabilities": stable_count,
            "mandatory_case_types": len(MANDATORY_CASES),
            "declared_cases": declared_cases,
            "validated_cases": counts["passed"],
            "failed": counts["failed"] + counts["missing"],
            "skipped": counts["skipped"],
        },
        "test_run": {key: test_result[key] for key in ("command", "exit_code", "summary")},
        "blockers": blockers,
    }
    canonical = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    report["report_id"] = "sha256:" + hashlib.sha256(canonical).hexdigest()
    return report


def validate_report_schema(report: dict) -> list[str]:
    from jsonschema import Draft202012Validator, FormatChecker

    schema = json.loads(REPORT_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = [
        f"report schema: {'.'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
        for error in sorted(validator.iter_errors(report), key=lambda item: list(item.absolute_path))
    ]
    document = {key: value for key, value in report.items() if key != "report_id"}
    canonical = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    expected = "sha256:" + hashlib.sha256(canonical).hexdigest()
    if report.get("report_id") != expected:
        errors.append("report integrity: report_id does not match canonical report content")
    cases = report.get("cases", {})
    if report.get("status") == "passed" and cases.get("validated_cases") != cases.get("declared_cases"):
        errors.append("report truth: passed report must validate every declared case")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("offline", "nightly", "release-candidate"), required=True)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    catalog, manifest = load_documents()
    blockers = validate_manifest(catalog, manifest)
    blockers.extend(catalog_integrity_errors(catalog))
    current_env = dict(os.environ)
    blockers.extend(environment_errors(args.mode, current_env))
    runtime_evidence_hash = None
    if args.mode == "release-candidate":
        evidence_errors, runtime_evidence_hash = validate_runtime_evidence(catalog, manifest, current_env)
        blockers.extend(evidence_errors)
        try:
            if _git("status", "--porcelain"):
                blockers.append("release-candidate requires a clean working tree")
        except subprocess.CalledProcessError:
            blockers.append("release-candidate cannot resolve git working tree")
    test_result, test_blockers = _run_contract_tests(manifest)
    blockers.extend(test_blockers)
    report = build_report(
        args.mode, catalog, manifest, blockers, test_result,
        runtime_evidence_hash=runtime_evidence_hash,
    )
    schema_errors = validate_report_schema(report)
    if schema_errors:
        blockers.extend(schema_errors)
        report = build_report(
            args.mode, catalog, manifest, blockers, test_result,
            runtime_evidence_hash=runtime_evidence_hash,
        )
        remaining = validate_report_schema(report)
        if remaining:
            raise RuntimeError("acceptance report cannot satisfy its checked-in schema: " + "; ".join(remaining))
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.report:
        target = args.report if args.report.is_absolute() else ROOT / args.report
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    failed = report["status"] != "passed"
    return 1 if failed and args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
