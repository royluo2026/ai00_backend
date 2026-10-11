import pytest

from backend.db.table_prefix import validate_runtime_profile
from backend.base.remote_data_environment import remote_switch_configured
from backend.scripts.runtime_preflight import validate_deployment_values


@pytest.mark.parametrize('origin', [
    'https://workmanship-backend.chehejia.com',
    'https://workmanship-backend-test.chehejia.com',
])
def test_internal_remote_hosts_use_pp_and_matching_callback(origin, tmp_path):
    values = dict(AI00_DEPLOY_PROFILE='production', TABLE_PREFIX='pp_',
                  PUBLIC_URL=origin, BACKEND_BASE_URL=origin,
                  FEISHU_REDIRECT_URI=origin + '/auth/feishu/callback',
                  FEISHU_APP_ID='app', FEISHU_APP_SECRET='secret', JWT_SECRET='jwt',
                  ENV_FILE=str(tmp_path / '.env'), AI00_ALLOW_DATA_ENVIRONMENT_SWITCH='1',
                  AI00_DATA_ENVIRONMENT_STATE_FILE=str(tmp_path / 'state.json'),
                  AI00_REQUIRE_MIGRATIONS='1', DEBUG='false', PORT='80',
                  CORS_ALLOW_ORIGINS='https://workmanship-web-test.chehejia.com,app://root')
    validate_runtime_profile('production', 'pp_', origin)
    assert remote_switch_configured(values)
    assert validate_deployment_values(values) == []
    with pytest.raises(ValueError):
        validate_runtime_profile('production', 'test_', origin)
    values['FEISHU_REDIRECT_URI'] = 'https://foreign.example/auth/feishu/callback'
    assert validate_deployment_values(values)


def test_remote_host_allowlist_rejects_unknown_host():
    with pytest.raises(ValueError):
        validate_runtime_profile('production', 'pp_', 'https://foreign.example')


def test_uvicorn_entrypoint_replaces_process_with_supervisor(monkeypatch):
    from backend.scripts import managed_entrypoint as entry
    monkeypatch.setattr(entry, 'remote_switch_configured', lambda: True)
    monkeypatch.delenv('AI00_REMOTE_ENVIRONMENT_SUPERVISED', raising=False)
    calls = []
    monkeypatch.setattr(entry.os, 'execv', lambda *args: calls.append(args))
    entry.adopt_managed_remote_entrypoint()
    assert calls == [(entry.sys.executable, [entry.sys.executable, '-m', 'backend.scripts.supervise_environment'])]
    monkeypatch.setenv('AI00_REMOTE_ENVIRONMENT_SUPERVISED', '1')
    entry.adopt_managed_remote_entrypoint()
    assert len(calls) == 1
    monkeypatch.delenv('AI00_REMOTE_ENVIRONMENT_SUPERVISED')
    monkeypatch.setattr(entry, 'remote_switch_configured', lambda: False)
    entry.adopt_managed_remote_entrypoint()
    assert len(calls) == 1


def test_internal_env_factory_builds_real_application_and_dispatcher(monkeypatch):
    from pathlib import Path
    from backend.capability_v2.bootstrap import build_capability_registry
    build_capability_registry(Path(__file__).resolve().parents[2])
    from integration_backend.capabilities.wiring import build_application, build_import_dispatcher
    monkeypatch.setenv('AI00_INTEGRATION_ADAPTER_FACTORY',
                      'integration_backend.infrastructure.production_adapters:build')
    assert build_application() is not None
    assert build_import_dispatcher() is not None


def test_deployment_factory_matches_frozen_provider_lifecycle(monkeypatch):
    import asyncio
    from pathlib import Path
    from dotenv import dotenv_values
    from backend.capability_v2.bootstrap import build_capability_registry
    root = Path(__file__).resolve().parents[2]
    values = dotenv_values(root / 'backend/.env.production.template', interpolate=False)
    monkeypatch.setenv('AI00_INTEGRATION_ADAPTER_FACTORY', values['AI00_INTEGRATION_ADAPTER_FACTORY'])
    registry = build_capability_registry(root)
    start, stop = registry._lifecycles['integration.import-worker']

    async def exercise():
        # Start and immediately stop before the queued poll task accesses any DB.
        await start()
        assert registry.lifecycle_health('integration.import-worker')['status'] == 'starting'
        await stop()
        assert registry.lifecycle_health('integration.import-worker')['status'] == 'stopped'
    asyncio.run(exercise())


@pytest.mark.parametrize('filename', ['.env', '.env.production.template', '.env.test.template', '.env.dev'])
def test_published_env_has_active_connector_signing_key(monkeypatch, filename):
    from pathlib import Path
    from dotenv import dotenv_values
    from backend.routers.health import connector_signing_readiness
    from plugins.simulation.simulation_backend.application.connector_protocol_v2 import PlanSigner
    keys = ('AI00_CONNECTOR_PLAN_SIGNING_P256_KEY_ID',
            'AI00_CONNECTOR_PLAN_SIGNING_P256_PRIVATE_KEY',
            'AI00_CONNECTOR_PLAN_SIGNING_P256_NOT_BEFORE',
            'AI00_CONNECTOR_PLAN_SIGNING_P256_NOT_AFTER')
    values = dotenv_values(Path(__file__).resolve().parents[1] / filename, interpolate=False)
    for key in keys:
        if not values.get(key):
            raise AssertionError('Missing signing configuration: ' + key)
        monkeypatch.setenv(key, values[key])
    assert connector_signing_readiness() == 'ok'
    assert PlanSigner.configured_from_environment()._active_key_record() is not None
