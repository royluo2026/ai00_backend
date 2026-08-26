from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from backend.capability_v2 import consumer_routes
from backend.capability_v2.consumer_routes import (
    OperationsExclusion,
    RouteScanConfigurationError,
    load_operations_exclusions,
    load_wrapper_contracts,
    normalize_route,
    scan_web_api_routes,
    scan_web_routes,
)
from backend.scripts.check_web_capability_routes import _require_known_methods


def _scan(source: str, tmp_path: Path, **kwargs):
    web = tmp_path / "web"
    web.mkdir(exist_ok=True)
    (web / kwargs.get("source_name", "app.js")).write_text(source, encoding="utf-8")
    return scan_web_api_routes(
        [web],
        legacy_index=kwargs.get("legacy_index", set()),
        bff_index=kwargs.get("bff_index", set()),
        exclusions=kwargs.get("exclusions", ()),
        frontend_revision="abc123",
        wrapper_contracts=kwargs.get("wrapper_contracts", ()),
    )


def _wrapper_contracts(
    tmp_path: Path,
    source: str,
    entries: list[dict[str, object]],
):
    lines = source.splitlines(keepends=True)
    source_sha256 = hashlib.sha256(source.encode("utf-8")).hexdigest()
    for entry in entries:
        start_line = int(entry.pop("definition_start_line", 1))
        end_line = int(entry.pop("definition_end_line", start_line))
        definition = "".join(lines[start_line - 1:end_line])
        binding = entry.pop(
            "binding",
            {
                "kind": "function_declaration",
                "parameters": ["route", "options = {}"],
            },
        )
        call_site_lines = entry.pop(
            "call_site_lines",
            [
                index
                for index, line in enumerate(lines, start=1)
                if index > end_line and "/api/" in line
            ],
        )
        selected_call_lines = set(call_site_lines)
        call_sites = []
        for match in consumer_routes._ROUTE_LITERAL.finditer(source):
            route_offset = match.start("route")
            line = source.count("\n", 0, route_offset) + 1
            if line not in selected_call_lines:
                continue
            line_start = source.rfind("\n", 0, route_offset) + 1
            raw_fragment = source[match.start("route"):match.end("route")]
            raw_route = consumer_routes._raw_route(source, match.end(), raw_fragment)
            call_sites.append(
                {
                    "source_path": "web/app.js",
                    "line": line,
                    "column": route_offset - line_start + 1,
                    "raw_route": raw_route,
                    "normalized_route": normalize_route(raw_route),
                    "source_sha256": source_sha256,
                }
            )
        entry.update(
            {
                "source": "web/app.js",
                "source_sha256": source_sha256,
                "definition": {
                    "source_path": "web/app.js",
                    "start_line": start_line,
                    "end_line": end_line,
                    "sha256": hashlib.sha256(definition.encode("utf-8")).hexdigest(),
                },
                "expected_definition": definition.strip(),
                "binding": binding,
                "call_sites": call_sites,
            }
        )
    path = tmp_path / "wrapper-contracts.json"
    path.write_text(
        json.dumps({"schema_version": 3, "entries": entries}),
        encoding="utf-8",
    )
    return consumer_routes.load_wrapper_contracts(path)


def _exact_wrapper_contracts(
    tmp_path: Path,
    source: str,
    *,
    call_routes: list[str],
    contract_source_sha256: str | None = None,
    call_source_sha256: str | None = None,
    definition_source_path: str = "web/app.js",
    source_path: str = "web/app.js",
):
    lines = source.splitlines(keepends=True)
    definition = lines[0]
    source_sha256 = hashlib.sha256(source.encode("utf-8")).hexdigest()
    cursor = 0
    call_sites = []
    for raw_route in call_routes:
        offset = source.index(raw_route, cursor)
        cursor = offset + len(raw_route)
        line = source.count("\n", 0, offset) + 1
        line_start = source.rfind("\n", 0, offset) + 1
        call_sites.append(
            {
                "source_path": source_path,
                "line": line,
                "column": offset - line_start + 1,
                "raw_route": raw_route,
                "normalized_route": normalize_route(raw_route),
                "source_sha256": call_source_sha256 or source_sha256,
            }
        )
    document = {
        "schema_version": 3,
        "entries": [
            {
                "source": source_path,
                "source_sha256": contract_source_sha256 or source_sha256,
                "callee": "request",
                "signature": {
                    "route_argument": 0,
                    "method_source": "options_argument",
                    "method_argument": 1,
                    "default_method": "GET",
                },
                "definition": {
                    "source_path": definition_source_path,
                    "start_line": 1,
                    "end_line": 1,
                    "sha256": hashlib.sha256(definition.encode("utf-8")).hexdigest(),
                },
                "expected_definition": definition.strip(),
                "binding": {
                    "kind": "function_declaration",
                    "parameters": ["route", "options = {}"],
                },
                "call_sites": call_sites,
            }
        ],
    }
    path = tmp_path / "exact-wrapper-contracts.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return load_wrapper_contracts(path)


def test_scanner_discovers_api_outside_configured_prefixes(tmp_path: Path) -> None:
    report = _scan("fetch('/api/agents/' + agentId)\n", tmp_path)

    assert report.routes[0].normalized_route == "/api/agents/{dynamic}"
    assert report.routes[0].disposition == "unresolved"


def test_ambiguous_method_is_unresolved(tmp_path: Path) -> None:
    report = _scan("client.request('/api/tasks')\n", tmp_path)

    assert report.routes[0].method is None
    assert report.routes[0].disposition == "unresolved"


def test_canonical_gate_rejects_ambiguous_method(tmp_path: Path) -> None:
    report = _scan("client.request('/api/tasks')\n", tmp_path)

    with pytest.raises(RouteScanConfigurationError, match="method is unknown"):
        _require_known_methods(report)


@pytest.mark.parametrize("callee", ["api", "cf", "fn"])
def test_generic_call_names_do_not_imply_get(
    tmp_path: Path, callee: str
) -> None:
    report = _scan(f"{callee}('/api/tasks')\n", tmp_path)

    assert report.routes[0].method is None
    assert report.routes[0].disposition == "unresolved"


def test_arbitrary_object_method_name_does_not_imply_http_method(
    tmp_path: Path,
) -> None:
    report = _scan("routes.get('/api/tasks')\n", tmp_path)

    assert report.routes[0].method is None


def test_nested_payload_method_does_not_override_fetch_default_get(
    tmp_path: Path,
) -> None:
    report = _scan(
        "fetch('/api/tasks', { body: JSON.stringify({ method: 'POST' }) });\n",
        tmp_path,
        legacy_index={("GET", "/api/tasks")},
    )

    assert report.routes[0].method == "GET"
    assert report.routes[0].disposition == "legacy_registered"


def test_arbitrary_options_call_does_not_imply_http_method(tmp_path: Path) -> None:
    report = _scan("dispatch('/api/tasks', { method: 'POST' });\n", tmp_path)

    assert report.routes[0].method is None


def test_direct_fetch_accepts_quoted_top_level_method_key(tmp_path: Path) -> None:
    report = _scan(
        "fetch('/api/tasks', { 'method': 'POST' });\n",
        tmp_path,
        legacy_index={("POST", "/api/tasks")},
    )

    assert report.routes[0].method == "POST"
    assert report.routes[0].disposition == "legacy_registered"


def test_commented_fetch_method_does_not_override_default_get(tmp_path: Path) -> None:
    report = _scan(
        "fetch('/api/tasks', { // method: 'POST'\n});\n",
        tmp_path,
        legacy_index={("GET", "/api/tasks")},
    )

    assert report.routes[0].method == "GET"
    assert report.routes[0].disposition == "legacy_registered"


def test_scanner_preserves_method_after_markup_and_optional_chaining(
    tmp_path: Path,
) -> None:
    report = _scan(
        "const markup = `<div class=\"item\">x</div>`;\n"
        "_cloudFetch?.(`/api/tasks/${encodeURIComponent(gid)}`, {\n"
        "  method: 'PATCH',\n"
        "});\n",
        tmp_path,
        legacy_index={("PATCH", "/api/tasks/{gid}")},
    )

    assert report.routes[0].normalized_route == "/api/tasks/{dynamic}"
    assert report.routes[0].method == "PATCH"
    assert report.routes[0].disposition == "legacy_registered"


def test_scanner_reads_explicit_method_argument_before_route(tmp_path: Path) -> None:
    report = _scan(
        "_cf('POST', '/api/tasks', { title: 'one' });\n",
        tmp_path,
        legacy_index={("POST", "/api/tasks")},
    )

    assert report.routes[0].method == "POST"
    assert report.routes[0].disposition == "legacy_registered"


def test_unknown_method_first_call_contract_stays_unresolved(tmp_path: Path) -> None:
    report = _scan("dispatch('POST', '/api/tasks')\n", tmp_path)

    assert report.routes[0].method is None
    assert report.routes[0].disposition == "unresolved"


@pytest.mark.parametrize(
    "source",
    [
        "client.fetch('/api/tasks', { method: 'POST' });\n",
        "client._cf('POST', '/api/tasks');\n",
        "client._cloudFetch('/api/tasks', { method: 'POST' });\n",
    ],
)
def test_qualified_callee_does_not_inherit_direct_http_contract(
    tmp_path: Path, source: str
) -> None:
    report = _scan(source, tmp_path)

    assert report.routes[0].method is None
    assert report.routes[0].disposition == "unresolved"


def test_source_anchored_wrapper_contract_resolves_group_through_shared_classifier(
    tmp_path: Path,
) -> None:
    source = (
        "function request(route, options = {}) { return fetch(route, options); }\n"
        "request('/api/tasks');\n"
        "request('/api/tasks', { method: 'POST' });\n"
    )
    contracts = _wrapper_contracts(
        tmp_path,
        source,
        [
            {
                "callee": "request",
                "signature": {
                    "route_argument": 0,
                    "method_source": "options_argument",
                    "method_argument": 1,
                    "default_method": "GET",
                },
            }
        ],
    )

    report = _scan(
        source,
        tmp_path,
        wrapper_contracts=contracts,
        legacy_index={("GET", "/api/tasks"), ("POST", "/api/tasks")},
    )

    assert [route.method for route in report.routes] == ["GET", "POST"]
    assert {route.disposition for route in report.routes} == {"legacy_registered"}


def test_wrapper_contract_modes_use_exact_signature_positions(tmp_path: Path) -> None:
    source = (
        "function create(route, body) { return fetch(route, { method: 'POST', body }); }\n"
        "function request(method, route) { return fetch(route, { method }); }\n"
        "create('/api/tasks', {});\n"
        "request('GET', '/api/tasks');\n"
    )
    contracts = _wrapper_contracts(
        tmp_path,
        source,
        [
            {
                "callee": "create",
                "signature": {
                    "route_argument": 0,
                    "method_source": "constant",
                    "method": "POST",
                },
                "definition_start_line": 1,
                "binding": {
                    "kind": "function_declaration",
                    "parameters": ["route", "body"],
                },
                "call_site_lines": [3],
            },
            {
                "callee": "request",
                "signature": {
                    "route_argument": 1,
                    "method_source": "method_argument",
                    "method_argument": 0,
                },
                "definition_start_line": 2,
                "binding": {
                    "kind": "function_declaration",
                    "parameters": ["method", "route"],
                },
                "call_site_lines": [4],
            },
        ],
    )

    report = _scan(
        source,
        tmp_path,
        wrapper_contracts=contracts,
        legacy_index={("GET", "/api/tasks"), ("POST", "/api/tasks")},
    )

    assert [route.method for route in report.routes] == ["POST", "GET"]
    assert {route.disposition for route in report.routes} == {"legacy_registered"}


def test_wrapper_contract_rejects_stale_source_and_definition_anchors(
    tmp_path: Path,
) -> None:
    source = (
        "function request(route) { return fetch(route); }\n"
        "client.request('/api/tasks');\n"
    )
    contracts = _wrapper_contracts(
        tmp_path,
        source,
        [
            {
                "callee": "request",
                "signature": {
                    "route_argument": 0,
                    "method_source": "constant",
                    "method": "GET",
                },
            }
        ],
    )

    with pytest.raises(RouteScanConfigurationError, match="source hash is stale"):
        _scan(source.replace("fetch(route)", "fetch(route, {})"), tmp_path, wrapper_contracts=contracts)

    stale_anchor = contracts[0].definition
    contracts = (
        consumer_routes.WrapperContract(
            source=contracts[0].source,
            source_sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
            callee=contracts[0].callee,
            signature=contracts[0].signature,
            definition=consumer_routes.SourceAnchor(
                source_path=stale_anchor.source_path,
                start_line=stale_anchor.start_line,
                end_line=stale_anchor.end_line,
                sha256="0" * 64,
            ),
            expected_definition=contracts[0].expected_definition,
            binding=contracts[0].binding,
            call_sites=contracts[0].call_sites,
        ),
    )
    with pytest.raises(RouteScanConfigurationError, match="definition hash is stale"):
        _scan(source, tmp_path, wrapper_contracts=contracts)


def test_wrapper_contract_rejects_ambiguous_and_wildcard_contracts(
    tmp_path: Path,
) -> None:
    source = (
        "function request(route) { return fetch(route); }\n"
        "request('/api/tasks');\n"
    )
    entry = {
        "callee": "request",
        "signature": {
            "route_argument": 0,
            "method_source": "constant",
            "method": "GET",
        },
        "binding": {
            "kind": "function_declaration",
            "parameters": ["route"],
        },
    }
    with pytest.raises(RouteScanConfigurationError, match="ambiguous wrapper contract"):
        _wrapper_contracts(tmp_path, source, [entry, dict(entry)])

    with pytest.raises(RouteScanConfigurationError, match="wildcard"):
        _wrapper_contracts(
            tmp_path,
            source,
            [
                {
                    "callee": "client.*",
                    "signature": {
                        "route_argument": 0,
                        "method_source": "constant",
                        "method": "GET",
                    },
                }
            ],
        )


@pytest.mark.parametrize(
    "options",
    [
        "{ ...opts }",
        "{ /* runtime overrides */ ...opts }",
        "{ method }",
        "{ ['method']: 'POST' }",
        "{ method: 'GET', method: 'POST' }",
    ],
)
def test_options_contract_fails_closed_on_runtime_method_overrides(
    tmp_path: Path, options: str
) -> None:
    source = (
        "function request(route, options = {}) { return fetch(route, options); }\n"
        f"request('/api/tasks', {options});\n"
    )
    contracts = _wrapper_contracts(
        tmp_path,
        source,
        [
            {
                "callee": "request",
                "signature": {
                    "route_argument": 0,
                    "method_source": "options_argument",
                    "method_argument": 1,
                    "default_method": "GET",
                },
            }
        ],
    )

    report = _scan(
        source,
        tmp_path,
        wrapper_contracts=contracts,
        legacy_index={("GET", "/api/tasks"), ("POST", "/api/tasks")},
    )

    assert report.routes[0].method is None
    assert report.routes[0].disposition == "unresolved"


def test_options_contract_defaults_get_only_for_unambiguous_object(
    tmp_path: Path,
) -> None:
    source = (
        "function request(route, options = {}) { return fetch(route, options); }\n"
        "request('/api/tasks', { headers: {} });\n"
    )
    contracts = _wrapper_contracts(
        tmp_path,
        source,
        [
            {
                "callee": "request",
                "signature": {
                    "route_argument": 0,
                    "method_source": "options_argument",
                    "method_argument": 1,
                    "default_method": "GET",
                },
            }
        ],
    )

    report = _scan(
        source,
        tmp_path,
        wrapper_contracts=contracts,
        legacy_index={("GET", "/api/tasks")},
    )

    assert report.routes[0].method == "GET"
    assert report.routes[0].disposition == "legacy_registered"


def test_direct_fetch_options_spread_does_not_fall_back_to_get(
    tmp_path: Path,
) -> None:
    report = _scan(
        "fetch('/api/tasks', { ...opts });\n",
        tmp_path,
        legacy_index={("GET", "/api/tasks")},
    )

    assert report.routes[0].method is None
    assert report.routes[0].disposition == "unresolved"


def test_wrapper_contract_rejects_unanchored_call_reference(tmp_path: Path) -> None:
    source = (
        "function request(route, options = {}) { return fetch(route, options); }\n"
        "function first() { return request('/api/tasks'); }\n"
        "function second() { return request('/api/issues'); }\n"
    )
    contracts = _wrapper_contracts(
        tmp_path,
        source,
        [
            {
                "callee": "request",
                "signature": {
                    "route_argument": 0,
                    "method_source": "options_argument",
                    "method_argument": 1,
                    "default_method": "GET",
                },
                "call_site_lines": [2],
            }
        ],
    )

    with pytest.raises(
        RouteScanConfigurationError,
        match="reference is ambiguous",
    ):
        _scan(source, tmp_path, wrapper_contracts=contracts)


def test_exact_wrapper_contract_rejects_same_line_shadowed_binding(
    tmp_path: Path,
) -> None:
    source = (
        "function request(route, options = {}) { return fetch(route, options); }\n"
        "function shadowed() { function request(route) { return fetch(route, { method: 'POST' }); } "
        "request('/api/issues'); } request('/api/tasks');\n"
    )
    contracts = _exact_wrapper_contracts(
        tmp_path,
        source,
        call_routes=["/api/tasks"],
    )

    with pytest.raises(
        RouteScanConfigurationError,
        match="reference is ambiguous",
    ):
        _scan(source, tmp_path, wrapper_contracts=contracts)


def test_exact_wrapper_contract_rejects_anchored_shadowed_binding(
    tmp_path: Path,
) -> None:
    source = (
        "function request(route, options = {}) { return fetch(route, options); }\n"
        "function shadowed() {\n"
        "  function request(route) { return fetch(route, { method: 'POST' }); }\n"
        "  return request('/api/issues');\n"
        "}\n"
        "request('/api/tasks');\n"
    )
    contracts = _exact_wrapper_contracts(
        tmp_path,
        source,
        call_routes=["/api/issues", "/api/tasks"],
    )

    with pytest.raises(
        RouteScanConfigurationError,
        match="reference is ambiguous",
    ):
        _scan(source, tmp_path, wrapper_contracts=contracts)


def test_exact_wrapper_contract_rejects_anchored_parameter_shadow(
    tmp_path: Path,
) -> None:
    source = (
        "function request(route, options = {}) { return fetch(route, options); }\n"
        "function invoke(request) { return request('/api/issues'); }\n"
        "request('/api/tasks');\n"
    )
    contracts = _exact_wrapper_contracts(
        tmp_path,
        source,
        call_routes=["/api/issues", "/api/tasks"],
    )

    with pytest.raises(
        RouteScanConfigurationError,
        match="reference is ambiguous",
    ):
        _scan(source, tmp_path, wrapper_contracts=contracts)


@pytest.mark.parametrize(
    "extra_reference",
    [
        "const { request: alias } = clients;",
        "import { request as importedRequest } from './client.js';",
        "const alias = request;",
        "const alias = `${request}`;",
        "const client = { request: unrelated };",
    ],
)
def test_wrapper_contract_rejects_unproved_callee_reference(
    tmp_path: Path,
    extra_reference: str,
) -> None:
    source = (
        "function request(route, options = {}) { return fetch(route, options); }\n"
        f"{extra_reference}\n"
        "request('/api/tasks');\n"
    )
    contracts = _exact_wrapper_contracts(
        tmp_path,
        source,
        call_routes=["/api/tasks"],
        definition_source_path="web/app.html",
        source_path="web/app.html",
    )

    with pytest.raises(
        RouteScanConfigurationError,
        match="reference is ambiguous",
    ):
        _scan(
            source,
            tmp_path,
            wrapper_contracts=contracts,
            source_name="app.html",
        )


def test_wrapper_contract_accepts_only_definition_and_exact_call_references(
    tmp_path: Path,
) -> None:
    source = (
        "function request(route, options = {}) { return fetch(route, options); }\n"
        "request('/api/tasks');\n"
        "request('/api/issues', { method: 'POST' });\n"
    )
    contracts = _exact_wrapper_contracts(
        tmp_path,
        source,
        call_routes=["/api/tasks", "/api/issues"],
    )

    report = _scan(source, tmp_path, wrapper_contracts=contracts)

    assert [route.method for route in report.routes] == ["GET", "POST"]


def test_wrapper_contract_rejects_cross_source_definition(
    tmp_path: Path,
) -> None:
    source = (
        "function request(route, options = {}) { return fetch(route, options); }\n"
        "request('/api/tasks');\n"
    )

    with pytest.raises(
        RouteScanConfigurationError,
        match="definition source is ambiguous",
    ):
        _exact_wrapper_contracts(
            tmp_path,
            source,
            call_routes=["/api/tasks"],
            definition_source_path="web/request.js",
        )


def test_scanner_rejects_cross_source_definition_if_loader_is_bypassed(
    tmp_path: Path,
) -> None:
    source = (
        "function request(route, options = {}) { return fetch(route, options); }\n"
        "request('/api/tasks');\n"
    )
    contract = _exact_wrapper_contracts(
        tmp_path,
        source,
        call_routes=["/api/tasks"],
    )[0]
    contract = replace(
        contract,
        definition=replace(contract.definition, source_path="web/request.js"),
    )

    with pytest.raises(
        RouteScanConfigurationError,
        match="definition source is ambiguous",
    ):
        _scan(source, tmp_path, wrapper_contracts=[contract])


def test_wrapper_contract_rejects_additional_callee_assignment(
    tmp_path: Path,
) -> None:
    source = (
        "function request(route, options = {}) { return fetch(route, options); }\n"
        "request = function(route) { return fetch(route, { method: 'POST' }); };\n"
        "request('/api/tasks');\n"
    )
    contracts = _exact_wrapper_contracts(
        tmp_path,
        source,
        call_routes=["/api/tasks"],
    )

    with pytest.raises(
        RouteScanConfigurationError,
        match="reference is ambiguous",
    ):
        _scan(source, tmp_path, wrapper_contracts=contracts)


def test_exact_wrapper_anchor_rejects_moved_column(tmp_path: Path) -> None:
    source = (
        "function request(route, options = {}) { return fetch(route, options); }\n"
        "request('/api/tasks');\n"
    )
    moved = source.replace("request('/api/tasks')", "  request('/api/tasks')")
    moved_hash = hashlib.sha256(moved.encode("utf-8")).hexdigest()
    contracts = _exact_wrapper_contracts(
        tmp_path,
        source,
        call_routes=["/api/tasks"],
        contract_source_sha256=moved_hash,
        call_source_sha256=moved_hash,
    )

    with pytest.raises(RouteScanConfigurationError, match="call site occurrence is stale"):
        _scan(moved, tmp_path, wrapper_contracts=contracts)


def test_exact_wrapper_anchor_rejects_stale_call_source_hash(tmp_path: Path) -> None:
    source = (
        "function request(route, options = {}) { return fetch(route, options); }\n"
        "request('/api/tasks');\n"
    )
    with pytest.raises(RouteScanConfigurationError, match="call site source hash is stale"):
        _exact_wrapper_contracts(
            tmp_path,
            source,
            call_routes=["/api/tasks"],
            call_source_sha256="0" * 64,
        )


def test_exact_wrapper_occurrence_artifact_is_bijective(tmp_path: Path) -> None:
    source = (
        "function request(route, options = {}) { return fetch(route, options); }\n"
        "request('/api/tasks'); request('/api/issues', { method: 'POST' });\n"
    )
    contracts = _exact_wrapper_contracts(
        tmp_path,
        source,
        call_routes=["/api/tasks", "/api/issues"],
    )

    report = _scan(
        source,
        tmp_path,
        wrapper_contracts=contracts,
        legacy_index={("GET", "/api/tasks"), ("POST", "/api/issues")},
    )
    anchors = {
        (
            anchor.source_path,
            anchor.line,
            anchor.column,
            anchor.raw_route,
            anchor.normalized_route,
        )
        for anchor in contracts[0].call_sites
    }
    occurrences = {
        (route.source, route.line, route.column, route.raw_route, route.normalized_route)
        for route in report.routes
    }

    assert anchors == occurrences


def test_wrapper_contract_rejects_mismatched_declared_signature(
    tmp_path: Path,
) -> None:
    source = (
        "function request(options, route) { return fetch(route, options); }\n"
        "request({}, '/api/tasks');\n"
    )
    contracts = _wrapper_contracts(
        tmp_path,
        source,
        [
            {
                "callee": "request",
                "signature": {
                    "route_argument": 0,
                    "method_source": "options_argument",
                    "method_argument": 1,
                    "default_method": "GET",
                },
                "binding": {
                    "kind": "function_declaration",
                    "parameters": ["route", "options = {}"],
                },
            }
        ],
    )

    with pytest.raises(RouteScanConfigurationError, match="parameter contract"):
        _scan(source, tmp_path, wrapper_contracts=contracts)


@pytest.mark.parametrize(
    "injected_definition",
    [
        'const injected = "function request(route, options = {})";',
        "const injected = /function request(route, options = {})/;",
    ],
)
def test_wrapper_contract_rejects_injected_definition_text(
    tmp_path: Path, injected_definition: str,
) -> None:
    source = (
        f"{injected_definition}\n"
        "request('/api/tasks');\n"
    )
    contracts = _wrapper_contracts(
        tmp_path,
        source,
        [
            {
                "callee": "request",
                "signature": {
                    "route_argument": 0,
                    "method_source": "options_argument",
                    "method_argument": 1,
                    "default_method": "GET",
                },
            }
        ],
    )

    with pytest.raises(RouteScanConfigurationError, match="definition binding"):
        _scan(source, tmp_path, wrapper_contracts=contracts)


def test_scanner_assigns_exactly_one_governed_disposition_per_occurrence(
    tmp_path: Path,
) -> None:
    exclusions = (
        OperationsExclusion(
            route_method="GET",
            normalized_route="/api/health",
            owner="platform-runtime",
            reason="Browser readiness probe for the local runtime.",
            approval_reference="OPS-2026-08-26-web-readiness",
            expires_at="2026-11-21T23:59:59+08:00",
        ),
    )
    report = _scan(
        "fetch('/api/tasks')\n"
        "fetch('/api/page-summary')\n"
        "fetch('/api/health')\n"
        "fetch(`/api/v1/capabilities/${id}:invoke`, { method: 'POST' })\n",
        tmp_path,
        legacy_index={("GET", "/api/tasks")},
        bff_index={("GET", "/api/page-summary")},
        exclusions=exclusions,
    )

    assert [route.disposition for route in report.routes] == [
        "legacy_registered",
        "bff_registered",
        "operations_excluded",
        "capability",
    ]
    assert report.counts == {
        "capability": 1,
        "legacy_registered": 1,
        "bff_registered": 1,
        "operations_excluded": 1,
        "unresolved": 0,
    }
    assert len({route.occurrence_id for route in report.routes}) == 4


def test_report_records_frontend_revision_content_hash_roots_and_exclusions(
    tmp_path: Path,
) -> None:
    report = _scan("fetch('/api/tasks')\n", tmp_path)
    serialized = report.serialized()

    assert serialized["frontend_revision"] == "abc123"
    assert len(serialized["content_hash"]) == 64
    assert serialized["scan_roots"] == ["web"]
    assert "**/node_modules/**" in serialized["excluded_roots"]
    assert serialized["routes"][0]["occurrence_id"].endswith(
        ":GET:/api/tasks"
    )


def test_lexical_audit_catches_api_token_missed_by_primary_extractor(
    tmp_path: Path,
) -> None:
    report = _scan("fetch('https://example.test/api/tasks')\n", tmp_path)

    audit = report.serialized()["lexical_audit"]
    assert audit["token_count"] == 1
    assert audit["mapped_count"] == 0
    assert audit["reviewed_non_route_count"] == 0
    assert audit["unmatched_count"] == 1
    assert audit["unmatched_tokens"] == ["web/app.js:1:28:/api/"]


def test_report_keeps_sibling_scan_roots_repository_relative(tmp_path: Path) -> None:
    web = tmp_path / "web"
    packages = tmp_path / "packages"
    web.mkdir()
    packages.mkdir()
    (web / "app.js").write_text("fetch('/api/tasks')\n", encoding="utf-8")
    (packages / "plugin.js").write_text("fetch('/api/issues')\n", encoding="utf-8")

    report = scan_web_api_routes(
        [web, packages], set(), set(), (), "abc123"
    )

    assert report.scan_roots == ("web", "packages")
    assert [route.source for route in report.routes] == [
        "packages/plugin.js",
        "web/app.js",
    ]


def test_scanner_excludes_test_and_spec_filenames_from_routes_and_hash(
    tmp_path: Path,
) -> None:
    web = tmp_path / "web"
    web.mkdir()
    (web / "app.js").write_text("fetch('/api/tasks')\n", encoding="utf-8")
    test_source = web / "app.test.js"
    spec_source = web / "app.spec.ts"
    test_source.write_text("fetch('/api/test-only')\n", encoding="utf-8")
    spec_source.write_text("fetch('/api/spec-only')\n", encoding="utf-8")

    before = scan_web_api_routes([web], set(), set(), (), "abc123")
    test_source.write_text("fetch('/api/changed-test-only')\n", encoding="utf-8")
    spec_source.write_text("fetch('/api/changed-spec-only')\n", encoding="utf-8")
    after = scan_web_api_routes([web], set(), set(), (), "abc123")

    assert [route.normalized_route for route in before.routes] == ["/api/tasks"]
    assert after.content_hash == before.content_hash
    assert "**/*.test.*" in before.excluded_roots
    assert "**/*.spec.*" in before.excluded_roots


@pytest.mark.parametrize(
    ("entries", "message"),
    [
        (
            [
                {
                    "route_method": "GET",
                    "normalized_route": "/api/*",
                    "owner": "platform",
                    "reason": "probe",
                    "approval_reference": "OPS-1",
                    "expires_at": "2026-11-21T00:00:00+00:00",
                }
            ],
            "wildcard",
        ),
        (
            [
                {
                    "route_method": "GET",
                    "normalized_route": "/api/health",
                    "owner": "platform",
                    "reason": "probe",
                    "approval_reference": "OPS-1",
                    "expires_at": "2020-01-01T00:00:00+00:00",
                }
            ],
            "expired",
        ),
    ],
)
def test_operations_exclusions_reject_unsafe_records(
    tmp_path: Path, entries: list[dict[str, str]], message: str
) -> None:
    path = tmp_path / "operations.json"
    path.write_text(
        __import__("json").dumps({"schema_version": 1, "entries": entries}),
        encoding="utf-8",
    )

    with pytest.raises(RouteScanConfigurationError, match=message):
        load_operations_exclusions(path)


def test_repository_operations_exclusions_are_current_and_exact() -> None:
    root = Path(__file__).resolve().parents[2]

    exclusions = load_operations_exclusions(
        root / "docs/governance/web-api-operations-exclusions.json"
    )

    assert exclusions
    assert all("*" not in item.normalized_route for item in exclusions)
    assert len({item.key for item in exclusions}) == len(exclusions)


def test_repository_wrapper_contracts_are_exact_and_unambiguous() -> None:
    root = Path(__file__).resolve().parents[2]

    contracts = load_wrapper_contracts(
        root / "docs/governance/web-api-wrapper-contracts.json"
    )

    assert contracts
    assert len({(item.source, item.callee) for item in contracts}) == len(contracts)
    assert all("*" not in item.source and "*" not in item.callee for item in contracts)
    anchors = [anchor for contract in contracts for anchor in contract.call_sites]
    identities = {
        (
            anchor.source_path,
            anchor.line,
            anchor.column,
            anchor.raw_route,
            anchor.normalized_route,
            anchor.source_sha256,
        )
        for anchor in anchors
    }
    assert len(anchors) == len(identities) == 18
    assert all(
        anchor.source_sha256 == contract.source_sha256
        for contract in contracts
        for anchor in contract.call_sites
    )


def test_scan_web_routes_reports_legacy_and_capability_calls_but_skips_dist_and_tests(
    tmp_path: Path,
) -> None:
    web = tmp_path / "web"
    (web / "pages").mkdir(parents=True)
    (web / "dist").mkdir()
    (web / "tests").mkdir()
    (web / "pages" / "bop.js").write_text(
        """\nfetch('/api/bop/entries/search?q=x');\nfetch('/api/v1/capabilities/craft.bop.read:invoke');\n// fetch('/api/bop/comment-only');\n/* fetch('/api/bop/block-comment-only'); */\n""",
        encoding="utf-8",
    )
    (web / "dist" / "bundle.js").write_text(
        "fetch('/api/bop/should-not-count');\n", encoding="utf-8"
    )
    (web / "tests" / "fixture.js").write_text(
        "fetch('/api/bop/test-fixture');\n", encoding="utf-8"
    )

    report = scan_web_routes(
        tmp_path,
        roots=["web"],
        legacy_prefixes=["/api/bop"],
    )

    assert report.legacy_count == 1
    assert report.capability_count == 1
    assert report.total_count == 2
    assert report.routes[0].source == "web/pages/bop.js"
    assert report.routes[0].line == 2
    assert report.routes[0].kind == "legacy"
    assert report.routes[1].kind == "capability"


def test_scan_web_routes_ignores_routes_in_comments_but_preserves_template_literals(
    tmp_path: Path,
) -> None:
    web = tmp_path / "web"
    web.mkdir()
    (web / "comments.js").write_text(
        "// fetch('/api/bop/nope')\n"
        "/* fetch('/api/bop/nope-either') */\n"
        "fetch(`/api/bop/${gid}`);\n",
        encoding="utf-8",
    )

    report = scan_web_routes(tmp_path, roots=["web"], legacy_prefixes=["/api/bop"])

    assert report.legacy_count == 1
    assert report.routes[0].route == "/api/bop/${gid}"


def test_scan_web_routes_fails_closed_on_unreadable_source(tmp_path: Path) -> None:
    web = tmp_path / "web"
    web.mkdir()
    source = web / "broken.js"
    source.write_text("const broken = ;\n", encoding="utf-8")

    with pytest.raises(RouteScanConfigurationError, match="cannot be parsed"):
        scan_web_routes(tmp_path, roots=["web"], legacy_prefixes=["/api/bop"])


def test_scan_web_routes_requires_explicit_allowlist_for_internal_legacy_routes(tmp_path: Path) -> None:
    web = tmp_path / "web"
    web.mkdir()
    (web / "flow.js").write_text(
        "fetch('/api/flows/test-node');\nfetch('/api/flows/entries');\n",
        encoding="utf-8",
    )

    report = scan_web_routes(
        tmp_path,
        roots=["web"],
        legacy_prefixes=["/api/flows"],
        allowlisted_legacy_routes=["/api/flows/test-node"],
    )

    assert report.legacy_count == 1
    assert report.allowlisted_count == 1
    assert {route.kind for route in report.routes} == {"legacy", "allowlisted"}


def test_scan_web_routes_rejects_unsafe_root(tmp_path: Path) -> None:
    with pytest.raises(RouteScanConfigurationError, match="repository-relative"):
        scan_web_routes(tmp_path, roots=["../web"], legacy_prefixes=["/api/bop"])
