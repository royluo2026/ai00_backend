from backend.config import Settings, get_settings
import importlib
import sys


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


def test_craft_tools_uses_settings_internal_backend_base(monkeypatch):
    make_settings(monkeypatch, BACKEND_BASE_URL=None, HOST='10.9.8.7', PORT='8091')
    sys.modules.pop('plugins.agent.agent_backend.ai_assistant.tool_handlers.craft_tools', None)
    module = importlib.import_module('plugins.agent.agent_backend.ai_assistant.tool_handlers.craft_tools')
    module = importlib.reload(module)
    assert module._BASE_URL == 'http://10.9.8.7:8091'
