import os
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from plugins.agent.agent_backend.infrastructure.runtime_secret_store import (
    RuntimeSecretStore,
    resolve_runtime_config,
)
from plugins.agent.agent_backend.routers import ai_chat


def test_runtime_secret_store_encrypts_and_round_trips(tmp_path):
    path = tmp_path / "agent-runtime-secret.dpapi"
    store = RuntimeSecretStore(
        path,
        protect=lambda raw: b"protected:" + raw[::-1],
        unprotect=lambda raw: raw.removeprefix(b"protected:")[::-1],
    )
    config = {"api_key": "secret-value", "model": "gpt-4o", "api_base": ""}

    store.save(config)

    assert b"secret-value" not in path.read_bytes()
    assert store.load() == config


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI only")
def test_runtime_secret_store_uses_real_windows_dpapi(tmp_path):
    path = tmp_path / "agent-runtime-secret.dpapi"
    store = RuntimeSecretStore(path)
    config = {"api_key": "real-dpapi-secret", "model": "gpt-4o", "api_base": ""}

    store.save(config)

    assert b"real-dpapi-secret" not in path.read_bytes()
    assert store.load() == config


def test_runtime_secret_store_preserves_previous_file_when_replace_fails(tmp_path, monkeypatch):
    path = tmp_path / "agent-runtime-secret.dpapi"
    store = RuntimeSecretStore(path, protect=lambda raw: raw[::-1], unprotect=lambda raw: raw[::-1])
    original = {"api_key": "first", "model": "gpt-4o", "api_base": ""}
    store.save(original)
    original_bytes = path.read_bytes()

    monkeypatch.setattr(os, "replace", lambda *_args: (_ for _ in ()).throw(OSError("replace failed")))
    with pytest.raises(OSError, match="replace failed"):
        store.save({"api_key": "second", "model": "gpt-4o", "api_base": ""})

    assert path.read_bytes() == original_bytes
    assert store.load() == original
    assert list(tmp_path.iterdir()) == [path]


def test_runtime_config_prefers_environment_then_local_secret(tmp_path, monkeypatch):
    store = RuntimeSecretStore(
        tmp_path / "secret.dpapi",
        protect=lambda raw: raw[::-1],
        unprotect=lambda raw: raw[::-1],
    )
    store.save({"api_key": "stored-key", "model": "stored-model", "api_base": "stored-base"})
    for name in ("AI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "AI_MODEL", "AI_API_BASE"):
        monkeypatch.delenv(name, raising=False)

    assert resolve_runtime_config(store=store) == {
        "api_key": "stored-key", "model": "stored-model",
        "api_base": "stored-base", "source": "local_secret",
    }

    monkeypatch.setenv("AI_API_KEY", "env-key")
    monkeypatch.setenv("AI_MODEL", "env-model")
    monkeypatch.setenv("AI_API_BASE", "env-base")
    assert resolve_runtime_config(store=store) == {
        "api_key": "env-key", "model": "env-model",
        "api_base": "env-base", "source": "env",
    }


def test_admin_config_save_is_gated_and_never_returns_secret(tmp_path, monkeypatch):
    store = RuntimeSecretStore(
        tmp_path / "secret.dpapi",
        protect=lambda raw: b"encrypted:" + raw[::-1],
        unprotect=lambda raw: raw.removeprefix(b"encrypted:")[::-1],
    )
    monkeypatch.setattr(ai_chat, "runtime_secret_store", lambda: store)
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    body = {"api_key": "shared-secret", "model": "gpt-4o", "api_base": ""}

    monkeypatch.delenv("ALLOW_LOCAL_RUNTIME_SECRET_ADMIN", raising=False)
    with pytest.raises(HTTPException) as disabled:
        ai_chat.save_admin_config(body, request, {"gid": "admin"})
    assert (disabled.value.status_code, disabled.value.detail) == (
        403, "local_runtime_secret_admin_disabled",
    )

    monkeypatch.setenv("ALLOW_LOCAL_RUNTIME_SECRET_ADMIN", "1")
    request.client.host = "10.0.0.5"
    with pytest.raises(HTTPException) as remote:
        ai_chat.save_admin_config(body, request, {"gid": "admin"})
    assert (remote.value.status_code, remote.value.detail) == (
        403, "local_runtime_secret_admin_loopback_only",
    )

    request.client.host = "127.0.0.1"
    result = ai_chat.save_admin_config(body, request, {"gid": "admin"})
    assert result == {
        "source": "local_secret", "model": "gpt-4o", "api_base": "",
        "has_key": True, "key_preview": "shar••••cret", "is_admin": True,
    }
    assert "api_key" not in result
    assert b"shared-secret" not in store.path.read_bytes()

    result = ai_chat.save_admin_config(
        {"api_key": "", "model": "gpt-4o-mini", "api_base": ""},
        request,
        {"gid": "admin"},
    )
    assert store.load()["api_key"] == "shared-secret"
    assert result["model"] == "gpt-4o-mini"
