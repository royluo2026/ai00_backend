from __future__ import annotations

from pathlib import Path

import pytest

from backend.capability_v2.consumer_routes import (
    OperationsExclusion,
    RouteScanConfigurationError,
    load_operations_exclusions,
    scan_web_api_routes,
    scan_web_routes,
)


def _scan(source: str, tmp_path: Path, **kwargs):
    web = tmp_path / "web"
    web.mkdir()
    (web / "app.js").write_text(source, encoding="utf-8")
    return scan_web_api_routes(
        [web],
        legacy_index=kwargs.get("legacy_index", set()),
        bff_index=kwargs.get("bff_index", set()),
        exclusions=kwargs.get("exclusions", ()),
        frontend_revision="abc123",
    )


def test_scanner_discovers_api_outside_configured_prefixes(tmp_path: Path) -> None:
    report = _scan("fetch('/api/agents/' + agentId)\n", tmp_path)

    assert report.routes[0].normalized_route == "/api/agents/{dynamic}"
    assert report.routes[0].disposition == "unresolved"


def test_ambiguous_method_is_unresolved(tmp_path: Path) -> None:
    report = _scan("client.request('/api/tasks')\n", tmp_path)

    assert report.routes[0].method is None
    assert report.routes[0].disposition == "unresolved"


def test_scanner_preserves_method_after_markup_and_optional_chaining(
    tmp_path: Path,
) -> None:
    report = _scan(
        "const markup = `<div class=\"item\">x</div>`;\n"
        "window._cloudFetch?.(`/api/tasks/${encodeURIComponent(gid)}`, {\n"
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
