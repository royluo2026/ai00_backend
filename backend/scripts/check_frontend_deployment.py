"""Verify the live backend serves the Capability V2 Web/plugin-center bundle."""
from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _get(base_url: str, path: str) -> tuple[int, str, str]:
    request = Request(f"{base_url.rstrip('/')}{path}", headers={"Accept": "*/*"})
    with urlopen(request, timeout=10) as response:  # noqa: S310 - operator supplied URL
        return response.status, response.headers.get_content_type(), response.read().decode("utf-8")


def check(base_url: str) -> dict[str, object]:
    checks = {
        "/health": ("application/json", '"status"'),
        "/ready": ("application/json", '"status"'),
        "/": ("text/html", "AI00"),
        "/web/settings/index.html": ("text/html", "plugin_center.js"),
        "/web/settings/plugin_center.js": (
            "text/javascript",
            "/api/v1/plugin-marketplace/catalog",
        ),
    }
    results: list[dict[str, object]] = []
    errors: list[str] = []
    for path, (expected_type, marker) in checks.items():
        try:
            status, content_type, body = _get(base_url, path)
            row = {
                "path": path,
                "status": status,
                "content_type": content_type,
                "marker_present": marker in body,
            }
            results.append(row)
            if status != 200:
                errors.append(f"{path}: expected HTTP 200, got {status}")
            if content_type != expected_type:
                errors.append(f"{path}: expected {expected_type}, got {content_type}")
            if marker not in body:
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
