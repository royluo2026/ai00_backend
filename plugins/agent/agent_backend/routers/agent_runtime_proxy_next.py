"""Compatibility proxy from legacy /api/ai routes to the Pi Agent Runtime."""
from __future__ import annotations

import json
import os
from typing import Iterator
from urllib.parse import quote

import httpx


def enabled() -> bool:
    return os.getenv("AI00_AGENT_RUNTIME_MODE", "legacy").strip().lower() == "pi"


def _base_url() -> str:
    value = os.getenv("AI00_AGENT_RUNTIME_URL", "").strip().rstrip("/")
    if not value:
        raise RuntimeError("AI00_AGENT_RUNTIME_URL is required when AI00_AGENT_RUNTIME_MODE=pi")
    if not value.startswith(("http://", "https://")):
        raise RuntimeError("AI00_AGENT_RUNTIME_URL must use http or https")
    return value


def _headers(token: str) -> dict[str, str]:
    if not token:
        raise RuntimeError("X-AI00-Token is required")
    return {"X-AI00-Token": token, "Content-Type": "application/json"}


def _error_event(message: str) -> str:
    return f"data: {json.dumps({'type': 'error', 'message': message}, ensure_ascii=False)}\n\n"


def _ensure_session(client: httpx.Client, token: str, session_gid: str | None) -> str:
    if session_gid:
        return session_gid
    response = client.post(f"{_base_url()}/v1/sessions", headers=_headers(token), json={"channelType": "web"})
    response.raise_for_status()
    return str(response.json()["data"]["gid"])


def _start_run(client: httpx.Client, token: str, session_gid: str, body: dict) -> str:
    context = body.get("context") or {}
    if isinstance(context, str):
        context = {"text": context}
    response = client.post(
        f"{_base_url()}/v1/runs", headers=_headers(token),
        json={"sessionId": session_gid, "goal": body.get("message", ""), "context": context, "channelType": "web"},
    )
    response.raise_for_status()
    return str(response.json()["data"]["runId"])


def stream_chat(body: dict, token: str) -> Iterator[str]:
    """Relay upstream SSE without buffering; never silently fall back after a failure."""
    try:
        timeout = httpx.Timeout(connect=10.0, read=None, write=30.0, pool=10.0)
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            session_gid = _ensure_session(client, token, body.get("session_id") or body.get("session_gid"))
            run_id = _start_run(client, token, session_gid, body)
            payload = {"text": body.get("message", "")}
            with client.stream(
                "POST", f"{_base_url()}/v1/runs/{quote(run_id, safe='')}/messages/stream",
                headers=_headers(token), json=payload,
            ) as response:
                if response.status_code >= 400:
                    response.read()
                    yield _error_event(f"Agent Runtime HTTP {response.status_code}")
                    return
                for chunk in response.iter_text():
                    if chunk:
                        yield chunk
    except Exception as exc:
        yield _error_event(f"Agent Runtime unavailable: {str(exc)[:240]}")


def sync_chat(body: dict, token: str) -> dict:
    try:
        with httpx.Client(timeout=180.0, trust_env=False) as client:
            session_gid = _ensure_session(client, token, body.get("session_id") or body.get("session_gid"))
            run_id = _start_run(client, token, session_gid, body)
            response = client.post(
                f"{_base_url()}/v1/runs/{quote(run_id, safe='')}/messages",
                headers=_headers(token), json={"text": body.get("message", "")},
            )
            response.raise_for_status()
            return {"answer": response.json()["data"]["text"], "session_id": session_gid, "run_id": run_id, "tool_calls": [], "model": "pi"}
    except Exception as exc:
        return {"error": f"Agent Runtime unavailable: {str(exc)[:240]}"}


def list_sessions(token: str) -> dict:
    with httpx.Client(timeout=20.0, trust_env=False) as client:
        response = client.get(f"{_base_url()}/v1/sessions", headers=_headers(token))
        response.raise_for_status()
        rows = response.json()["data"]
    return {"sessions": [{"gid": row["gid"], "title": "Pi 对话", "created_at": row["createdAt"], "updated_at": row["updatedAt"]} for row in rows]}


def get_session(token: str, gid: str) -> dict:
    with httpx.Client(timeout=20.0, trust_env=False) as client:
        response = client.get(f"{_base_url()}/v1/sessions/{quote(gid, safe='')}", headers=_headers(token))
        response.raise_for_status()
        return response.json()["data"]


def delete_session(token: str, gid: str) -> dict:
    with httpx.Client(timeout=20.0, trust_env=False) as client:
        response = client.delete(f"{_base_url()}/v1/sessions/{quote(gid, safe='')}", headers=_headers(token))
        response.raise_for_status()
    return {"success": True}


def new_session(token: str) -> dict:
    with httpx.Client(timeout=20.0, trust_env=False) as client:
        gid = _ensure_session(client, token, None)
    return {"session_gid": gid}


def list_tools(token: str) -> dict:
    with httpx.Client(timeout=20.0, trust_env=False) as client:
        response = client.get(f"{_base_url()}/v1/tools", headers=_headers(token))
        response.raise_for_status()
        specs = response.json()["data"]["descriptors"]
    read = [{"name": spec["id"], "description": spec.get("description", ""), "category": "read", "need_confirm": False, "params": list(spec.get("input_schema", {}).get("properties", {}))} for spec in specs if spec.get("side_effect_level") == "read" and spec.get("confirmation_policy") == "none" and spec.get("execution_mode") == "cloud_sync"]
    return {"read": read, "write_confirm": [], "write_no_confirm": [], "system": [], "total": len(read)}


def health() -> dict:
    with httpx.Client(timeout=10.0, trust_env=False) as client:
        response = client.get(f"{_base_url()}/health")
        response.raise_for_status()
        data = response.json()
    return {"success": bool(data.get("ok")), "reply": "Pi Agent Runtime 可用", "model": "pi"}
