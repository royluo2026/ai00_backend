from backend.config import Settings, get_settings
import importlib
import sys
from pathlib import Path


REQUIRED_ENV = {
    'FEISHU_APP_ID': 'test-app-id',
    'FEISHU_APP_SECRET': 'test-app-secret',
    'FEISHU_REDIRECT_URI': 'http://127.0.0.1:8080/auth/feishu/callback',
    'JWT_SECRET': 'unit-test-secret',
    'USERS_DB_URL': 'mysql://root:root@127.0.0.1:3306/workmanship',
}


def make_settings(monkeypatch, **overrides):
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)
    for key, value in overrides.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    return Settings()


def test_internal_backend_base_uses_explicit_override(monkeypatch):
    settings = make_settings(monkeypatch, BACKEND_BASE_URL='http://backend.internal:9010')
    assert settings.internal_backend_base_url == 'http://backend.internal:9010'


def test_frontend_config_prefers_public_url(monkeypatch):
    settings = make_settings(
        monkeypatch,
        PUBLIC_URL='https://api.example.com',
        BACKEND_BASE_URL='http://127.0.0.1:8080',
    )
    assert settings.public_url == 'https://api.example.com'


def test_agent_legacy_http_tool_handlers_are_retired():
    root = Path(__file__).resolve().parents[2]
    assert not any((root / "plugins/agent/agent_backend/ai_assistant/tool_handlers").rglob("*.py"))
