import pytest

from backend.config import Settings, get_settings

REQUIRED_ENV = {
    "FEISHU_APP_ID": "test-app-id",
    "FEISHU_APP_SECRET": "test-app-secret",
    "FEISHU_REDIRECT_URI": "http://127.0.0.1:8080/auth/feishu/callback",
    "JWT_SECRET": "unit-test-secret",
    "USERS_DB_URL": "mysql://root:root@127.0.0.1:3306/workmanship",
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


def test_port_defaults_to_8080(monkeypatch):
    settings = make_settings(monkeypatch, PORT=None, PUBLIC_URL=None, CORS_ALLOW_ORIGINS=None)
    assert settings.port == 8080


def test_public_url_trims_trailing_slash(monkeypatch):
    settings = make_settings(monkeypatch, PUBLIC_URL='https://workmanship-backend-test.chehejia.com/')
    assert settings.public_url == 'https://workmanship-backend-test.chehejia.com'


def test_cors_allow_origins_splits_csv(monkeypatch):
    settings = make_settings(
        monkeypatch,
        CORS_ALLOW_ORIGINS='http://127.0.0.1:5173,https://workmanship-web-test.chehejia.com'
    )
    assert settings.cors_allow_origins == [
        'http://127.0.0.1:5173',
        'https://workmanship-web-test.chehejia.com',
    ]


def test_cors_allow_origins_defaults_cover_local_and_legacy_clients(monkeypatch):
    settings = make_settings(monkeypatch, CORS_ALLOW_ORIGINS=None)
    assert settings.cors_allow_origins == [
        'http://127.0.0.1:5173',
        'http://localhost:5173',
        'app://root',
        'null',
    ]
