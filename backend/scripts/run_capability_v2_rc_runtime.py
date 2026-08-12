#!/usr/bin/env python3
"""Generate current-run Capability V2 runtime and Provider RC evidence."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Callable, Literal, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.scripts.run_capability_v2_acceptance import (
    _domain_manifest_binding,
    _domain_migration_bindings,
    _migration_binding,
    contract_test_command,
)


_REQUIRED_COMPONENTS = frozenset(
    {"backend_gateway", "plugin", "agent", "mcp", "local_runtime"}
)
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


class RuntimeEvidenceError(RuntimeError):
    """Raised when current-run evidence is incomplete or cannot be trusted."""


@dataclass(frozen=True)
class RuntimeProbeResult:
    component: str
    status: Literal["passed", "failed"]
    endpoint: str
    checks: tuple[str, ...]
    duration_ms: int
    correlation_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class HttpResult:
    status: int
    body: object
    headers: Mapping[str, str]


@dataclass(frozen=True)
class ProviderProbeResult:
    domain_id: str
    capability_id: str
    major_version: int
    duration_ms: int
    correlation_ids: tuple[str, ...]


@dataclass(frozen=True)
class MandatoryOutcomeRun:
    outcomes: dict[str, str]
    outcome_sha256: str
    summary: str


def collect_mandatory_outcomes(
    *,
    root: Path,
    temp_root: Path,
    run: Callable[..., object] = subprocess.run,
) -> MandatoryOutcomeRun:
    """Run the mandatory acceptance suite once and read its raw outcome file."""

    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="runtime-", dir=temp_root) as directory:
        run_directory = Path(directory)
        result_path = run_directory / "outcomes.json"
        command = contract_test_command(run_directory)
        process_environment = dict(os.environ)
        process_environment["AI00_ACCEPTANCE_RESULT_PATH"] = str(result_path)
        completed = run(
            command,
            cwd=root,
            env=process_environment,
            text=True,
            capture_output=True,
            check=False,
        )
        if int(getattr(completed, "returncode", 1)) != 0:
            raise RuntimeEvidenceError("acceptance_pytest_failed")
        if not result_path.is_file():
            raise RuntimeEvidenceError("acceptance_outcome_missing")
        raw = result_path.read_bytes()
        def unique_object(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    raise RuntimeEvidenceError("acceptance_outcome_duplicate")
                value[key] = item
            return value

        try:
            payload = json.loads(raw, object_pairs_hook=unique_object)
        except RuntimeEvidenceError:
            raise
        except Exception:
            raise RuntimeEvidenceError("acceptance_outcome_unreadable") from None
        if payload.get("exit_status") != 0 or not isinstance(payload.get("outcomes"), dict):
            raise RuntimeEvidenceError("acceptance_outcome_invalid")
        summary = next(
            (
                line.strip()
                for line in reversed(str(getattr(completed, "stdout", "")).splitlines())
                if line.strip()
            ),
            "pytest passed",
        )
        return MandatoryOutcomeRun(
            outcomes={str(key): str(value) for key, value in payload["outcomes"].items()},
            outcome_sha256="sha256:" + hashlib.sha256(raw).hexdigest(),
            summary=summary,
        )


def _origin(value: str) -> str:
    if value.startswith("outbound://"):
        parsed = urlparse(value)
        if not parsed.hostname:
            raise RuntimeEvidenceError("probe_endpoint_invalid")
        return f"outbound://{parsed.hostname}"
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username:
        raise RuntimeEvidenceError("probe_endpoint_invalid")
    port = f":{parsed.port}" if parsed.port else ""
    return f"https://{parsed.hostname}{port}"


_COMPONENT_CHECKS = {
    "backend_gateway": frozenset(
        {"health", "catalog", "unauthenticated_denial", "permitted_invoke", "audit"}
    ),
    "plugin": frozenset({"catalog", "permitted", "denied", "approval"}),
    "agent": frozenset({"health", "tools", "permitted", "denied", "approval"}),
    "mcp": frozenset({"initialize", "tools", "permitted", "denied"}),
    "local_runtime": frozenset({"heartbeat", "lease"}),
}


def _read_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeEvidenceError(f"{label}_unreadable") from exc
    if not isinstance(value, dict):
        raise RuntimeEvidenceError(f"{label}_invalid")
    return value


def load_probe_config(root: Path, path: Path) -> dict:
    """Load the protected probe plan and bind it to current Catalog ownership."""

    config = _read_json(path, "probe_config")
    if config.get("schema_version") != 1:
        raise RuntimeEvidenceError("probe_config_schema_mismatch")
    components = config.get("components")
    if not isinstance(components, dict) or set(components) != _REQUIRED_COMPONENTS:
        raise RuntimeEvidenceError("component_probe_set_mismatch")
    for component, expected in _COMPONENT_CHECKS.items():
        steps = components.get(component)
        if not isinstance(steps, list) or {
            str(step.get("name", "")) for step in steps if isinstance(step, dict)
        } != expected or len(steps) != len(expected):
            raise RuntimeEvidenceError(f"component_check_set_mismatch:{component}")
        required_target = {
            "backend_gateway": "backend", "plugin": "backend",
            "agent": "agent", "mcp": "mcp", "local_runtime": "backend",
        }[component]
        if any(str(step.get("target", "")) != required_target for step in steps):
            raise RuntimeEvidenceError(f"component_target_mismatch:{component}")
        if component == "plugin" and any(
            not str(step.get("path", "")).startswith("/api/v1/plugin-marketplace/")
            for step in steps
        ):
            raise RuntimeEvidenceError("plugin_probe_must_use_mount_gateway")
        if component == "local_runtime" and any(
            not str(step.get("path", "")).startswith("/api/v1/device-runtime/")
            for step in steps
        ):
            raise RuntimeEvidenceError("local_runtime_probe_must_be_outbound")

    domains_document = _read_json(
        root / "backend/capability_v2/official_domains.json", "domain_manifest"
    )
    domains = {
        str(item["domain_id"]): frozenset(str(value) for value in item["allowed_owners"])
        for item in domains_document.get("domains", [])
    }
    providers = config.get("providers")
    if not isinstance(providers, dict) or set(providers) != set(domains):
        raise RuntimeEvidenceError("provider_probe_set_mismatch")
    catalog = _read_json(root / "docs/capabilities/catalog.v2.json", "catalog")
    descriptors = {
        (str(item["id"]), int(item["major_version"])): item
        for item in catalog.get("capabilities", [])
    }
    for domain_id, probe in providers.items():
        if not isinstance(probe, dict) or not isinstance(probe.get("payload"), dict):
            raise RuntimeEvidenceError(f"provider_probe_invalid:{domain_id}")
        key = (str(probe.get("capability_id", "")), int(probe.get("major_version", 0)))
        descriptor = descriptors.get(key)
        if descriptor is None or str(descriptor.get("owner_domain")) not in domains[domain_id]:
            raise RuntimeEvidenceError(f"provider_probe_owner_mismatch:{domain_id}")
    if not isinstance(config.get("gateway_headers_env"), dict):
        raise RuntimeEvidenceError("gateway_headers_env_invalid")
    return config


def request_json(
    method: str,
    url: str,
    headers: Mapping[str, str],
    body: object | None,
    timeout: float,
) -> HttpResult:
    encoded = None if body is None else json.dumps(body).encode("utf-8")
    request = Request(url, data=encoded, method=method.upper(), headers=dict(headers))
    if encoded is not None:
        request.add_header("Content-Type", "application/json")
    try:
        response = urlopen(request, timeout=timeout)
    except HTTPError as exc:
        response = exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeEvidenceError("probe_transport_failed") from exc
    raw = response.read()
    try:
        payload: object = json.loads(raw) if raw else {}
    except Exception:
        payload = {}
    return HttpResult(
        status=int(response.status),
        body=payload,
        headers={str(key): str(value) for key, value in response.headers.items()},
    )


def _headers_from_env(spec: object, environ: Mapping[str, str]) -> dict[str, str]:
    if not isinstance(spec, dict):
        raise RuntimeEvidenceError("probe_headers_invalid")
    headers: dict[str, str] = {}
    for header, source in spec.items():
        prefix = ""
        if isinstance(source, dict):
            variable = str(source.get("env", ""))
            prefix = str(source.get("prefix", ""))
        else:
            variable = str(source)
        value = str(environ.get(variable, "")).strip()
        if not value:
            raise RuntimeEvidenceError(f"probe_secret_missing:{variable}")
        headers[str(header)] = prefix + value
    return headers


def _correlation_ids(value: object, headers: Mapping[str, str]) -> tuple[str, ...]:
    found: set[str] = set()

    def visit(item: object) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if key in {"request_id", "trace_id", "correlation_id"} and isinstance(child, str) and child:
                    found.add(child)
                else:
                    visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    for key, child in headers.items():
        if key.casefold() in {"x-request-id", "x-trace-id", "x-correlation-id"} and child:
            found.add(child)
    return tuple(sorted(found))


def _nonempty_catalog(body: object) -> bool:
    if not isinstance(body, dict):
        return False
    candidates = [body.get("data"), body.get("descriptors")]
    result = body.get("result")
    if isinstance(result, dict):
        candidates.extend((result.get("tools"), result.get("descriptors")))
    return any(isinstance(value, list) and bool(value) for value in candidates)


def _validate_step(name: str, expectation: str, response: HttpResult) -> None:
    body = response.body
    if expectation == "denied":
        if response.status not in {401, 403, 404}:
            raise RuntimeEvidenceError(f"probe_expected_denial:{name}")
        return
    if not 200 <= response.status < 300:
        raise RuntimeEvidenceError(f"probe_http_failed:{name}")
    if expectation in {"catalog", "tools"} and not _nonempty_catalog(body):
        raise RuntimeEvidenceError(f"probe_catalog_empty:{name}")
    if expectation == "health" and not (
        isinstance(body, dict) and (body.get("ok") is True or body.get("success") is True)
    ):
        raise RuntimeEvidenceError(f"probe_health_failed:{name}")
    if expectation == "approval" and not (
        isinstance(body, dict)
        and any(body.get(key) for key in ("approval_reference", "confirmation_token", "approval_id"))
    ):
        raise RuntimeEvidenceError(f"probe_approval_missing:{name}")
    if expectation in {"success", "initialize"} and isinstance(body, dict):
        if body.get("success") is False or body.get("ok") is False:
            raise RuntimeEvidenceError(f"probe_result_failed:{name}")
        data = body.get("data")
        if isinstance(data, dict) and data.get("status") in {"failed", "denied", "error"}:
            raise RuntimeEvidenceError(f"probe_result_failed:{name}")


def _step_url(step: Mapping, bases: Mapping[str, str]) -> str:
    target = str(step.get("target", ""))
    if target not in bases:
        raise RuntimeEvidenceError("probe_target_invalid")
    base = bases[target].rstrip("/") + "/"
    _origin(base)
    path = str(step.get("path", ""))
    if not path.startswith("/") or urlparse(path).scheme or path.startswith("//"):
        raise RuntimeEvidenceError("probe_path_invalid")
    return urljoin(base, path.lstrip("/"))


def run_component_probes(
    *,
    root: Path,
    backend_url: str,
    agent_url: str,
    mcp_url: str,
    config: Mapping,
    environ: Mapping[str, str],
    request: Callable[..., HttpResult] = request_json,
    run: Callable[..., object] = subprocess.run,
) -> tuple[RuntimeProbeResult, ...]:
    bases = {"backend": backend_url, "agent": agent_url, "mcp": mcp_url}
    results: list[RuntimeProbeResult] = []
    for component in sorted(_REQUIRED_COMPONENTS):
        started = time.monotonic()
        checks: list[str] = []
        correlations: set[str] = set()
        if component == "local_runtime":
            completed = run(
                [
                    "dotnet", "test", str(root / "local-runtime/Ai00.LocalRuntime.sln"),
                    "--configuration", "Release", "--nologo",
                ],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            if int(getattr(completed, "returncode", 1)) != 0:
                raise RuntimeEvidenceError("local_runtime_dotnet_tests_failed")
            checks.append("dotnet_tests")
        for step in config["components"][component]:
            name = str(step["name"])
            headers = _headers_from_env(step.get("headers_env", {}), environ)
            response = request(
                str(step.get("method", "GET")),
                _step_url(step, bases),
                headers,
                step.get("body"),
                float(step.get("timeout_seconds", 20)),
            )
            _validate_step(name, str(step.get("expect", "success")), response)
            correlations.update(_correlation_ids(response.body, response.headers))
            checks.append(name)
        if not correlations:
            raise RuntimeEvidenceError(f"component_correlation_missing:{component}")
        results.append(RuntimeProbeResult(
            component=component,
            status="passed",
            endpoint=(
                "outbound://backend-device-gateway"
                if component == "local_runtime"
                else bases[
                    "backend" if component in {"backend_gateway", "plugin"} else component
                ]
            ),
            checks=tuple(checks),
            duration_ms=max(0, int((time.monotonic() - started) * 1000)),
            correlation_ids=tuple(sorted(correlations)),
        ))
    return tuple(results)


def run_provider_probes(
    *,
    root: Path,
    backend_url: str,
    config: Mapping,
    environ: Mapping[str, str],
    run_id: str,
    request: Callable[..., HttpResult] = request_json,
) -> tuple[ProviderProbeResult, ...]:
    del root  # Ownership was already bound by load_probe_config.
    _origin(backend_url)
    base_headers = _headers_from_env(config["gateway_headers_env"], environ)
    results: list[ProviderProbeResult] = []
    for domain_id, probe in sorted(config["providers"].items()):
        started = time.monotonic()
        request_id = "rc_" + re.sub(r"[^A-Za-z0-9_.:-]", "_", f"{run_id}_{domain_id}")[-220:]
        headers = {**base_headers, "X-Request-ID": request_id, "X-Trace-ID": request_id}
        capability_id = str(probe["capability_id"])
        response = request(
            "POST",
            backend_url.rstrip("/") + "/api/v1/capabilities/" + quote(capability_id, safe=".") + ":invoke",
            headers,
            {"payload": probe["payload"], "version": int(probe["major_version"])},
            float(probe.get("timeout_seconds", 30)),
        )
        _validate_step(f"provider:{domain_id}", "success", response)
        correlations = _correlation_ids(response.body, response.headers)
        if request_id not in correlations:
            raise RuntimeEvidenceError(f"provider_correlation_missing:{domain_id}")
        results.append(ProviderProbeResult(
            domain_id=domain_id,
            capability_id=capability_id,
            major_version=int(probe["major_version"]),
            duration_ms=max(0, int((time.monotonic() - started) * 1000)),
            correlation_ids=correlations,
        ))
    return tuple(results)


def build_provider_evidence(
    *, environment_id: str, run_id: str, git_commit: str, backend_url: str,
    results: Sequence[ProviderProbeResult],
) -> dict:
    _validate_bindings(environment_id, run_id, git_commit, "sha256:" + "0" * 64)
    domains = {result.domain_id: "passed" for result in results}
    if len(domains) != 11 or len(domains) != len(results):
        raise RuntimeEvidenceError("provider_probe_set_mismatch")
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "environment_id": environment_id,
        "run_id": run_id,
        "git_commit": git_commit,
        "endpoint": _origin(backend_url),
        "domains": domains,
        "probes": {
            result.domain_id: {
                "capability_id": result.capability_id,
                "major_version": result.major_version,
                "status": "passed",
                "duration_ms": result.duration_ms,
                "correlation_ids": list(result.correlation_ids),
            }
            for result in results
        },
    }


def _validate_bindings(
    environment_id: str,
    run_id: str,
    git_commit: str,
    outcome_sha256: str,
) -> None:
    normalized = environment_id.strip().casefold()
    if (
        not normalized
        or "prod" in normalized
        or not any(marker in normalized for marker in ("test", "rc"))
    ):
        raise RuntimeEvidenceError("environment_not_test_or_rc")
    if not run_id.strip():
        raise RuntimeEvidenceError("run_id_invalid")
    if not _COMMIT.fullmatch(git_commit):
        raise RuntimeEvidenceError("git_commit_invalid")
    if not _SHA256.fullmatch(outcome_sha256):
        raise RuntimeEvidenceError("outcome_hash_invalid")


def build_runtime_evidence(
    *,
    root: Path,
    environment_id: str,
    run_id: str,
    git_commit: str,
    outcomes: Mapping[str, str],
    probes: Sequence[RuntimeProbeResult],
    outcome_sha256: str,
) -> dict:
    """Bind exact pytest outcomes and current component probes to this RC run."""

    _validate_bindings(environment_id, run_id, git_commit, outcome_sha256)
    catalog = json.loads(
        (root / "docs/capabilities/catalog.v2.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (
            root / "backend/tests/acceptance/fixtures/case-manifest.json"
        ).read_text(encoding="utf-8")
    )
    expected = {
        node: (capability_key, case)
        for capability_key, cases in manifest["capabilities"].items()
        for case, node in cases.items()
    }
    if set(outcomes) != set(expected):
        raise RuntimeEvidenceError("mandatory_outcome_set_mismatch")
    if any(outcomes[node] != "passed" for node in expected):
        raise RuntimeEvidenceError("mandatory_outcomes_not_passed")

    probes_by_component = {probe.component: probe for probe in probes}
    if len(probes_by_component) != len(probes) or set(probes_by_component) != _REQUIRED_COMPONENTS:
        raise RuntimeEvidenceError("component_probe_set_mismatch")
    for component, probe in probes_by_component.items():
        if probe.status != "passed":
            raise RuntimeEvidenceError(f"component_probe_failed:{component}")
        if not probe.checks or probe.duration_ms < 0:
            raise RuntimeEvidenceError(f"component_probe_invalid:{component}")

    capabilities = {
        capability_key: {
            case: outcomes[node]
            for case, node in cases.items()
        }
        for capability_key, cases in manifest["capabilities"].items()
    }
    component_results = {
        component: probes_by_component[component].status
        for component in sorted(_REQUIRED_COMPONENTS)
    }
    component_provenance = {
        component: {
            "endpoint": _origin(probes_by_component[component].endpoint),
            "checks": list(probes_by_component[component].checks),
            "duration_ms": probes_by_component[component].duration_ms,
            "correlation_ids": list(probes_by_component[component].correlation_ids),
        }
        for component in sorted(_REQUIRED_COMPONENTS)
    }
    return {
        "schema_version": 1,
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "git_commit": git_commit,
        "catalog_release": catalog["release_id"],
        "catalog_hash": catalog["catalog_hash"],
        "migration": _migration_binding(),
        "domain_manifest": _domain_manifest_binding(),
        "domain_migrations": _domain_migration_bindings(),
        "provider_artifacts": catalog["provider_artifacts"],
        "environment_id": environment_id,
        "component_results": component_results,
        "probe_provenance": {
            "outcome_sha256": outcome_sha256,
            "components": component_provenance,
        },
        "capabilities": capabilities,
    }


def _required(environ: Mapping[str, str], name: str) -> str:
    value = str(environ.get(name, "")).strip()
    if not value:
        raise RuntimeEvidenceError(f"missing:{name}")
    return value


def _head(root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True,
        capture_output=True, check=False,
    )
    if completed.returncode != 0:
        raise RuntimeEvidenceError("git_commit_unavailable")
    return completed.stdout.strip()


def _write_json(path: Path, document: Mapping) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main(
    argv: Sequence[str] | None = None,
    *,
    root: Path = ROOT,
    environ: Mapping[str, str] = os.environ,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-url", required=True)
    parser.add_argument("--agent-url", required=True)
    parser.add_argument("--mcp-url", required=True)
    parser.add_argument("--provider-output", type=Path, required=True)
    parser.add_argument("--runtime-output", type=Path, required=True)
    args = parser.parse_args(argv)

    environment_id = _required(environ, "AI00_ACCEPTANCE_ENVIRONMENT_ID")
    run_id = _required(environ, "AI00_ACCEPTANCE_RUN_ID")
    config_path = Path(_required(environ, "AI00_RC_PROBE_CONFIG"))
    config = load_probe_config(root, config_path)
    commit = _head(root)
    outcomes = collect_mandatory_outcomes(
        root=root,
        temp_root=args.runtime_output.parent / ".runtime-test-tmp",
    )
    component_results = run_component_probes(
        root=root,
        backend_url=args.backend_url,
        agent_url=args.agent_url,
        mcp_url=args.mcp_url,
        config=config,
        environ=environ,
    )
    provider_results = run_provider_probes(
        root=root,
        backend_url=args.backend_url,
        config=config,
        environ=environ,
        run_id=run_id,
    )
    runtime_evidence = build_runtime_evidence(
        root=root,
        environment_id=environment_id,
        run_id=run_id,
        git_commit=commit,
        outcomes=outcomes.outcomes,
        probes=component_results,
        outcome_sha256=outcomes.outcome_sha256,
    )
    provider_evidence = build_provider_evidence(
        environment_id=environment_id,
        run_id=run_id,
        git_commit=commit,
        backend_url=args.backend_url,
        results=provider_results,
    )
    _write_json(args.runtime_output, runtime_evidence)
    _write_json(args.provider_output, provider_evidence)
    print(json.dumps({
        "status": "passed",
        "environment_id": environment_id,
        "run_id": run_id,
        "mandatory_outcomes": len(outcomes.outcomes),
        "components": len(component_results),
        "domains": len(provider_results),
        "runtime_output": str(args.runtime_output),
        "provider_output": str(args.provider_output),
    }, sort_keys=True))
    return 0


__all__ = [
    "RuntimeEvidenceError",
    "HttpResult",
    "MandatoryOutcomeRun",
    "ProviderProbeResult",
    "RuntimeProbeResult",
    "build_runtime_evidence",
    "build_provider_evidence",
    "collect_mandatory_outcomes",
    "load_probe_config",
    "request_json",
    "run_component_probes",
    "run_provider_probes",
]


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeEvidenceError as exc:
        print(f"RC runtime evidence failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
