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


def test_public_url_can_be_empty_but_internal_backend_base_can_be_explicit(monkeypatch):
    settings = make_settings(
        monkeypatch,
        PUBLIC_URL='',
        BACKEND_BASE_URL='http://backend.internal:9000',
    )
    assert settings.public_url == ''
    assert settings.backend_base_url == 'http://backend.internal:9000'


def test_internal_backend_base_derives_from_host_and_port(monkeypatch):
    settings = make_settings(
        monkeypatch,
        PUBLIC_URL='',
        BACKEND_BASE_URL=None,
        HOST='0.0.0.0',
        PORT='8088',
    )
    assert settings.internal_backend_base_url == 'http://127.0.0.1:8088'


def test_cors_allow_origins_splits_csv(monkeypatch):
    settings = make_settings(
        monkeypatch,
        CORS_ALLOW_ORIGINS='http://127.0.0.1:5173,https://workmanship-web-test.chehejia.com'
    )
    assert settings.cors_allow_origins == [
        'http://127.0.0.1:5173',
        'https://workmanship-web-test.chehejia.com',
    ]


def test_cloud_db_url_builder_encodes_mysql_credentials():
    from backend.routers.admin import CloudDbConfigBody, _cloud_db_url_from_payload

    body = CloudDbConfigBody(
        host='sam-bdmsdb01-test.chj.cloud',
        port=2883,
        user='sht_mes_tool@mom#test_bdms01',
        password='Hsb2Q+6_',
        collab_db='sht_mes_tool',
        public_db='sht_mes_tool',
    )

    assert _cloud_db_url_from_payload(body) == (
        'mysql://sht_mes_tool%40mom%23test_bdms01:Hsb2Q%2B6_'
        '@sam-bdmsdb01-test.chj.cloud:2883/sht_mes_tool'
    )


def test_saved_cloud_db_url_overrides_env(monkeypatch, tmp_path):
    config_dir = tmp_path / '.ai00' / 'config'
    config_dir.mkdir(parents=True)
    (config_dir / 'system.json').write_text(
        '{"cloud_db_config": {"host": "db.internal", "port": 3307, "user": "saved", "password": "saved", "collab_db": "saved_db", "users_db_url": "mysql://outdated:stale@127.0.0.1:3306/old_db"}}',
        encoding='utf-8',
    )
    monkeypatch.setattr('backend.config.Path.home', lambda: tmp_path)

    settings = make_settings(monkeypatch, USERS_DB_URL='mysql://env:env@127.0.0.1:3306/workmanship')

    assert settings.users_db_url == 'mysql://saved:saved@db.internal:3307/saved_db'


def test_empty_saved_cloud_db_password_falls_back_to_env(monkeypatch, tmp_path):
    config_dir = tmp_path / '.ai00' / 'config'
    config_dir.mkdir(parents=True)
    (config_dir / 'system.json').write_text(
        '{"cloud_db_config": {"host": "sam-bdmsdb01-test.chj.cloud", "port": 2883, "user": "saved_user", "password": "", "collab_db": "saved_db", "users_db_url": "mysql://saved_user:@sam-bdmsdb01-test.chj.cloud:2883/saved_db"}}',
        encoding='utf-8',
    )
    monkeypatch.setattr('backend.config.Path.home', lambda: tmp_path)

    settings = make_settings(monkeypatch, USERS_DB_URL='mysql://env:realpass@127.0.0.1:3306/workmanship')

    assert settings.users_db_url == 'mysql://env:realpass@127.0.0.1:3306/workmanship'


def test_saved_cloud_db_url_with_password_still_overrides_env(monkeypatch, tmp_path):
    config_dir = tmp_path / '.ai00' / 'config'
    config_dir.mkdir(parents=True)
    (config_dir / 'system.json').write_text(
        '{"cloud_db_config": {"host": "db.internal", "port": 3307, "user": "saved", "password": "savedpass", "collab_db": "saved_db", "users_db_url": "mysql://saved:savedpass@db.internal:3307/saved_db"}}',
        encoding='utf-8',
    )
    monkeypatch.setattr('backend.config.Path.home', lambda: tmp_path)

    settings = make_settings(monkeypatch, USERS_DB_URL='mysql://env:realpass@127.0.0.1:3306/workmanship')

    assert settings.users_db_url == 'mysql://saved:savedpass@db.internal:3307/saved_db'


def test_saved_cloud_db_url_rebuilds_when_password_changes(monkeypatch, tmp_path):
    config_dir = tmp_path / '.ai00' / 'config'
    config_dir.mkdir(parents=True)
    (config_dir / 'system.json').write_text(
        '{"cloud_db_config": {"host": "sam-bdmsdb01-test.chj.cloud", "port": 2883, "user": "sht_mes_tool@mom#test_bdms01", "password": "Hsb2Q+6_", "collab_db": "sht_mes_tool", "users_db_url": "mysql://sht_mes_tool%40mom%23test_bdms01:@sam-bdmsdb01-test.chj.cloud:2883/sht_mes_tool"}}',
        encoding='utf-8',
    )
    monkeypatch.setattr('backend.config.Path.home', lambda: tmp_path)

    settings = make_settings(monkeypatch, USERS_DB_URL='mysql://env:realpass@127.0.0.1:3306/workmanship')

    assert settings.users_db_url == (
        'mysql://sht_mes_tool%40mom%23test_bdms01:Hsb2Q%2B6_'
        '@sam-bdmsdb01-test.chj.cloud:2883/sht_mes_tool'
    )


def test_saved_ois_config_overrides_env(monkeypatch, tmp_path):
    config_dir = tmp_path / '.ai00' / 'config'
    config_dir.mkdir(parents=True)
    (config_dir / 'system.json').write_text(
        '{"ois_config": {"identify": "saved-identify", "ois3_url": "https://saved-ois.example", "idaas_service_id": "saved-service"}}',
        encoding='utf-8',
    )
    monkeypatch.setattr('backend.config.Path.home', lambda: tmp_path)

    settings = make_settings(
        monkeypatch,
        OIS_IDENTIFY='env-identify',
        OIS_OIS3_URL='https://env-ois.example',
        OIS_IDAAS_SERVICE_ID='env-service',
    )

    assert settings.ois_identify == 'saved-identify'
    assert settings.ois_ois3_url == 'https://saved-ois.example'
    assert settings.ois_idaas_service_id == 'saved-service'


def test_ois_upload_uses_public_base_url_when_configured(monkeypatch):
    import backend.core.ois_storage as ois_storage

    class _FakeResponse:
        def __init__(self, object_key):
            self.data = type('Data', (), {'object_key': object_key})()
        def is_succeed(self):
            return True

    class _FakeClient:
        def put_object(self, bucket, key, stream):
            return _FakeResponse(f'vb-prefix/{key}')

    monkeypatch.setattr(ois_storage, '_get_ois_config', lambda: {
        'identify': 'crawler-platform-public',
        'public_base_url': 'https://cdn.example.com/files',
    })
    monkeypatch.setattr(ois_storage, 'is_enabled', lambda: True)
    monkeypatch.setattr(ois_storage, '_make_client', lambda: (_FakeClient(), None))
    monkeypatch.setattr(ois_storage.uuid, 'uuid4', lambda: type('U', (), {'hex': 'abc123'})())

    url = ois_storage.upload(b'hello', '.png', 'image/png', prefix='uploads')

    assert url == 'https://cdn.example.com/files/vb-prefix/uploads/abc123.png'


def test_ois_upload_returns_none_when_public_base_url_missing(monkeypatch):
    import backend.core.ois_storage as ois_storage

    class _FakeResponse:
        def __init__(self, object_key):
            self.data = type('Data', (), {'object_key': object_key})()
        def is_succeed(self):
            return True

    class _FakeClient:
        def put_object(self, bucket, key, stream):
            return _FakeResponse(f'vb-prefix/{key}')

    monkeypatch.setattr(ois_storage, '_get_ois_config', lambda: {
        'identify': 'crawler-platform-public',
        'public_base_url': '',
        'ois3_url': 'https://ois3-cnhb01.inner.chj.cloud',
    })
    monkeypatch.setattr(ois_storage, 'is_enabled', lambda: True)
    monkeypatch.setattr(ois_storage, '_make_client', lambda: (_FakeClient(), None))
    monkeypatch.setattr(ois_storage.uuid, 'uuid4', lambda: type('U', (), {'hex': 'abc123'})())

    url = ois_storage.upload(b'hello', '.png', 'image/png', prefix='uploads')

    assert url is None


def test_cors_allow_origins_defaults_cover_local_and_legacy_clients(monkeypatch):
    settings = make_settings(monkeypatch, CORS_ALLOW_ORIGINS=None)
    assert settings.cors_allow_origins == [
        'http://127.0.0.1:5173',
        'http://localhost:5173',
        'app://root',
        'null',
    ]
