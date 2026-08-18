"""Verify the live backend serves the Capability V2 Web/plugin-center bundle."""
from __future__ import annotations

import argparse
import json
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
        "/web/settings/index.html": (200, "text/html", "plugin_center_model.js"),
        "/web/settings/plugin_center_model.js": (
            200,
            "text/javascript",
            "AI00PluginCenterModel",
        ),
        "/web/settings/plugin_center_api.js": (
            200,
            "text/javascript",
            "createPluginCenterApi",
        ),
        "/web/settings/plugin_center.js": (
            200,
            "text/javascript",
            "Server-backed Capability V2 plugin center controller",
        ),
        "/web/admin/capability_governance/index.html": (200, "text/html", "governance_controller.js"),
    }
    results: list[dict[str, object]] = []
    errors: list[str] = []
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
        except (HTTPError, URLError, TimeoutError) as exc:
            results.append({"path": path, "error": str(exc)})
            errors.append(f"{path}: {exc}")
    return {"status": "passed" if not errors else "failed", "checks": results, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8094")
    args = parser.parse_args()
    report = check(args.base_url)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
