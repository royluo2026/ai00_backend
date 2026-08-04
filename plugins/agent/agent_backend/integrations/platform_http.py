from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlencode


class PlatformHttpError(RuntimeError):
    pass


class PlatformHttpClient:
    def __init__(self, auth_token: str = ""):
        self.base_url = os.getenv("AI00_BASE_API_URL", "http://127.0.0.1:8080").rstrip("/")
        self.auth_token = auth_token

    def request(self, method: str, path: str, *, params: dict | None = None, body: dict | None = None) -> Any:
        import httpx

        url = f"{self.base_url}{path}"
        if params:
            url += "?" + urlencode({key: value for key, value in params.items() if value not in (None, "")})
        headers = {"X-AI00-Token": self.auth_token} if self.auth_token else {}
        response = httpx.request(method, url, json=body, headers=headers, timeout=30)
        if response.status_code >= 400:
            detail = response.text[:300]
            raise PlatformHttpError(f"{method} {path} failed: HTTP {response.status_code}: {detail}")
        return response.json() if response.content else {}

    def get(self, path: str, params: dict | None = None):
        return self.request("GET", path, params=params)

    def post(self, path: str, body: dict | None = None):
        return self.request("POST", path, body=body or {})

    def put(self, path: str, body: dict | None = None):
        return self.request("PUT", path, body=body or {})
