import json
from types import SimpleNamespace
import pytest
from backend.base import remote_data_environment as remote
from backend.base import data_environment as environment

@pytest.fixture
def configured(monkeypatch, tmp_path):
    values = {"ENV_FILE":str(tmp_path / "backend.env"),"AI00_DEPLOY_PROFILE":"production","TABLE_PREFIX":"pp_", "PUBLIC_URL":"https://workmanship-backend.chehejia.com", "AI00_ALLOW_DATA_ENVIRONMENT_SWITCH":"1", "AI00_DATA_ENVIRONMENT_STATE_FILE":str(tmp_path / "selection.json"), "AI00_REMOTE_ENVIRONMENT_SUPERVISED":"1"}
    for key,value in values.items(): monkeypatch.setenv(key,value)
    monkeypatch.setattr(remote,"_active_prefix",None)
    monkeypatch.setattr(environment,"_restart",lambda:None)
    from backend.db import table_prefix
    monkeypatch.setattr(table_prefix,"current_table_prefix",lambda:'pp_')
    monkeypatch.setattr(environment,"connect",lambda:SimpleNamespace(close=lambda:None))
    monkeypatch.setattr(environment,"inspect_schemas",lambda _: {p:{"a":[1]} for p in environment.PREFIXES})
    return tmp_path / "selection.json"

def test_remote_defaults_to_pp_and_snapshot_does_not_change_live(configured):
    remote.activate_remote_environment()
    assert remote.runtime_table_prefix() == "pp_"
    configured.write_text(json.dumps({"prefix":"","previous_prefix":"pp_"}))
    assert remote.runtime_table_prefix() == "pp_"
    remote.activate_remote_environment()
    assert remote.runtime_table_prefix() == ""

@pytest.mark.parametrize("prefix",["test_","other_",None])
def test_remote_state_rejects_test_and_invalid_prefix(configured,prefix):
    configured.write_text(json.dumps({"prefix":prefix}))
    with pytest.raises(ValueError): remote.activate_remote_environment()

def test_remote_requires_real_supervisor(configured,monkeypatch):
    monkeypatch.delenv("AI00_REMOTE_ENVIRONMENT_SUPERVISED")
    with pytest.raises(RuntimeError): remote.activate_remote_environment()
    assert not environment.switching_enabled()

def test_schema_change_blocks_persisted_production_selection(configured,monkeypatch):
    configured.write_text('{"prefix":"","previous_prefix":"pp_"}')
    monkeypatch.setattr(environment,"inspect_schemas",lambda _:{"test_":{"a":[1]},"pp_":{"a":[1]},"":{"a":[2]}})
    with pytest.raises(RuntimeError,match="schema is unavailable"): remote.activate_remote_environment()

def test_remote_switch_requires_managed_absolute_paths(configured,monkeypatch):
    assert environment.switching_enabled()
    monkeypatch.setenv("AI00_DATA_ENVIRONMENT_STATE_FILE","relative.json")
    assert not remote.remote_switch_configured()
    assert not environment.switching_enabled()

def test_remote_rejects_test_before_db_access_even_if_client_or_schema_allows_it(configured,monkeypatch):
    monkeypatch.setattr(environment,"_pending",False)
    monkeypatch.setattr(environment,"connect",lambda:pytest.fail("must not access DB"))
    with pytest.raises(ValueError): environment.change_environment({"prefix":"test_","expected_prefix":"pp_"},SimpleNamespace(user_gid="admin"))

def test_remote_options_use_pp_baseline_and_ignore_different_test_schema(configured,monkeypatch):
    monkeypatch.setattr(environment,"inspect_schemas",lambda _: {"test_":{"dev_only":[9]},"pp_":{"a":[1]},"":{"a":[1]}})
    status=environment._status(None)
    assert status["baseline_prefix"] == "pp_"
    assert [o["prefix"] for o in status["options"] if o["available"]] == ["pp_",""]
    assert status["options"][0]["reasons"]


def test_pp_startup_does_not_inspect_environment_parity(configured,monkeypatch):
    monkeypatch.setattr(environment, 'connect', lambda: pytest.fail('pp startup must not compare schemas'))
    remote.activate_remote_environment()
    assert remote.runtime_table_prefix() == 'pp_'


def test_persisted_production_ignores_missing_test_schema(configured,monkeypatch):
    configured.write_text('{"prefix":"","previous_prefix":"pp_"}')
    monkeypatch.setattr(environment, 'inspect_schemas', lambda _: {'test_':{}, 'pp_':{'a':[1]}, '':{'a':[1]}})
    remote.activate_remote_environment()
    assert remote.runtime_table_prefix() == ''


def test_remote_production_switch_rejects_only_pp_production_difference(configured,monkeypatch):
    monkeypatch.setattr(environment, '_pending', False)
    monkeypatch.setattr(environment, '_require_admin', lambda *args: None)
    monkeypatch.setattr(environment, 'inspect_schemas', lambda _: {'test_':{}, 'pp_':{'a':[1]}, '':{'a':[2]}})
    with pytest.raises(ValueError, match='禁止切换'):
        environment.change_environment({'prefix':'', 'expected_prefix':'pp_'}, SimpleNamespace(user_gid='admin'))
    assert not configured.exists()


def test_remote_inspection_failure_does_not_disable_pp(configured,monkeypatch):
    monkeypatch.setattr(environment, '_pending', False)
    monkeypatch.setattr(environment, 'inspect_schemas', lambda _: (_ for _ in ()).throw(RuntimeError('metadata denied')))
    status = environment._status(None)
    options = {item['prefix']: item for item in status['options']}
    assert options['pp_']['available']
    assert not options['']['available']


def test_return_to_pp_skips_parity_but_checks_both_admin_roles(configured,monkeypatch):
    from backend.db import table_prefix
    configured.write_text('{"prefix":"","previous_prefix":"pp_"}')
    monkeypatch.setattr(table_prefix, 'current_table_prefix', lambda: '')
    monkeypatch.setattr(environment, '_pending', False)
    checked = []
    monkeypatch.setattr(environment, '_require_admin', lambda connection, prefix, gid: checked.append(prefix))
    monkeypatch.setattr(environment, 'inspect_schemas', lambda _: pytest.fail('return to pp must not inspect production parity'))
    monkeypatch.setattr(environment.threading, 'Timer', lambda *args: SimpleNamespace(start=lambda: None))
    assert environment.change_environment({'prefix':'pp_', 'expected_prefix':''}, SimpleNamespace(user_gid='admin'))['accepted']
    assert checked == ['', 'pp_']
    assert json.loads(configured.read_text())['prefix'] == 'pp_'

def test_worker_replacement_cannot_accept_a_second_switch_while_restart_is_pending(configured,monkeypatch):
    configured.write_text('{"prefix":"","previous_prefix":"pp_"}')
    monkeypatch.setattr(environment,"_pending",False)
    monkeypatch.setattr(environment,"connect",lambda:pytest.fail("pending switch must block before DB access"))
    assert environment.environment_pending()
    with pytest.raises(ValueError,match="正在重启"):
        environment.change_environment({"prefix":"pp_","expected_prefix":"pp_"},SimpleNamespace(user_gid="admin"))
