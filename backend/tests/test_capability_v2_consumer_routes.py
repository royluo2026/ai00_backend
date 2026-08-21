from __future__ import annotations

from pathlib import Path

import pytest

from backend.capability_v2.consumer_routes import (
    RouteScanConfigurationError,
    scan_web_routes,
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
