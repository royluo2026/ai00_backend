"""Verify the live backend serves the Capability V2 Web/plugin-center bundle."""
from __future__ import annotations

import argparse
import json
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _get(base_url: str, path: str) -> tuple[int, str, str]:
    request = Request(f"{base_url.rstrip('/')}{path}", headers={"Accept": "*/*"})
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310 - operator supplied URL
            return response.status, response.headers.get_content_type(), response.read().decode("utf-8")
    except HTTPError as exc:
        return exc.code, exc.headers.get_content_type(), exc.read().decode("utf-8", errors="replace")


def check(base_url: str) -> dict[str, object]:
    checks = {
        "/health": (200, "application/json", '"status"'),
        "/ready": (200, "application/json", '"status"'),
        "/": (200, "text/html", "AI00"),
        # The current settings page owns the plugin center panel in
        # ``settings.js``.  Older deployments used three standalone assets;
        # both shapes are accepted so a rolling deployment remains checkable.
        "/web/settings/index.html": (200, "text/html", None),
        "/web/admin/capability_governance/index.html": (200, "text/html", "governance_controller.js"),
    }
    results: list[dict[str, object]] = []
    errors: list[str] = []
    governance_html = ""
    for path, (expected_status, expected_type, marker) in checks.items():
        try:
            status, content_type, body = _get(base_url, path)
            row = {
                "path": path,
                "status": status,
                "content_type": content_type,
                "marker_present": marker in body if marker is not None else None,
            }
            results.append(row)
            if status != expected_status:
                errors.append(f"{path}: expected HTTP {expected_status}, got {status}")
            if expected_type is not None and content_type != expected_type:
                errors.append(f"{path}: expected {expected_type}, got {content_type}")
            if marker is not None and marker not in body:
                errors.append(f"{path}: missing marker {marker!r}")
            if path == "/web/settings/index.html":
                _check_plugin_center_entry(base_url, body, results, errors)
            if path == "/web/admin/capability_governance/index.html":
                governance_html = body
        except (HTTPError, URLError, TimeoutError) as exc:
            results.append({"path": path, "error": str(exc)})
            errors.append(f"{path}: {exc}")
    if governance_html:
        _check_governance_assets(base_url, governance_html, results, errors)
    return {"status": "passed" if not errors else "failed", "checks": results, "errors": errors}


def _check_plugin_center_entry(base_url: str, html: str, results: list[dict[str, object]], errors: list[str]) -> None:
    """Validate the plugin-center entry for both supported bundle layouts."""
    legacy = all(marker in html for marker in ("plugin_center_model.js", "plugin_center_api.js", "plugin_center.js"))
    if legacy:
        for path, marker in (
            ("/web/settings/plugin_center_model.js", "AI00PluginCenterModel"),
            ("/web/settings/plugin_center_api.js", "createPluginCenterApi"),
            ("/web/settings/plugin_center.js", "Server-backed Capability V2 plugin center controller"),
        ):
            _asset_result(base_url, path, "text/javascript", marker, results, errors)
        return
    current = 'id="panel-plugin-market"' in html and 'src="settings.js' in html
    if not current:
        errors.append("/web/settings/index.html: missing plugin-center entry")
        return
    _asset_result(
        base_url,
        "/web/settings/settings.js",
        "text/javascript",
        "panel-plugin-market",
        results,
        errors,
    )


def _check_governance_assets(base_url: str, html: str, results: list[dict[str, object]], errors: list[str]) -> None:
    scripts = {
        "governance_model.js": "CapabilityGovernanceModel",
        "governance_api.js": "CapabilityGovernanceApi",
        "governance_controller.js": "CapabilityGovernanceController",
    }
    linked_scripts = set(re.findall(r'<script[^>]+src="([^"/]+)"', html))
    stylesheets = set(re.findall(r'<link[^>]+href="(/assets/[^"?#]+\.css)"', html))
    for filename, marker in scripts.items():
        if filename not in linked_scripts:
            errors.append(f"governance_html: missing script {filename}")
            continue
        _asset_result(base_url, f"/web/admin/capability_governance/{filename}", "text/javascript", marker, results, errors)
    if not stylesheets:
        errors.append("governance_html: missing stylesheet")
    for path in sorted(stylesheets):
        _asset_result(base_url, path, "text/css", ".governance-shell", results, errors)


def _asset_result(base_url: str, path: str, expected_type: str, marker: str, results: list[dict[str, object]], errors: list[str]) -> None:
    try:
        status, content_type, body = _get(base_url, path)
    except (HTTPError, URLError, TimeoutError) as exc:
        results.append({"path": path, "error": str(exc)})
        errors.append(f"{path}: {exc}")
        return
    present = marker in body
    results.append({"path": path, "status": status, "content_type": content_type, "marker_present": present})
    if status != 200:
        errors.append(f"{path}: expected HTTP 200, got {status}")
    if content_type != expected_type:
        errors.append(f"{path}: expected {expected_type}, got {content_type}")
    if not present:
        errors.append(f"{path}: missing marker {marker!r}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8094")
    args = parser.parse_args()
    report = check(args.base_url)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
