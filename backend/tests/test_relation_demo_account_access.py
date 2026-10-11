import pytest
from backend.capabilities.models_next import CapabilityContext, CapabilityBusinessError
from backend.platform_sdk.demo_access import has_relation_demo_access
from plugins.craft.craft_backend.capabilities.demo_relation_change import _require_super_admin, _require_demo_version
from plugins.craft.craft_backend.capabilities.demo_relation_change import _relation_plan


@pytest.fixture
def configured_demo(monkeypatch):
    monkeypatch.setenv('TABLE_PREFIX', 'test_')
    monkeypatch.setenv('AI00_DEMO_ACCOUNT_GID', '7001')
    monkeypatch.setenv('AI00_DEMO_PROJECT_GID', '8001')
    monkeypatch.delenv('AI00_DEPLOY_PROFILE', raising=False)
    monkeypatch.setattr('backend.platform_sdk.project_access.can_edit_project_bop', lambda *args, **kwargs: True)


def test_only_configured_demo_actor_receives_access(configured_demo):
    assert has_relation_demo_access('7001')
    assert has_relation_demo_access('7001', '8001')
    assert not has_relation_demo_access('7002')
    assert not has_relation_demo_access('7001', '8002')
    _require_super_admin(CapabilityContext(user_gid='7001', active_roles=('member',)))


def test_demo_account_cannot_be_enabled_outside_test_tables(configured_demo, monkeypatch):
    monkeypatch.setenv('TABLE_PREFIX', 'pp_')
    assert not has_relation_demo_access('7001')
    with pytest.raises(CapabilityBusinessError):
        _require_super_admin(CapabilityContext(user_gid='7001', active_roles=('member',)))


class Cursor:
    def __init__(self, row):
        self.row = row
    def execute(self, query, params):
        assert 'project_gid' in query
        assert params == ('b1',)
    def fetchone(self):
        return self.row


def test_demo_account_is_checked_against_stored_version_project(configured_demo):
    context = CapabilityContext(user_gid='7001', active_roles=('member',))
    row = {'gid':'b1', 'project_gid':'8001', 'project_code':'L5', 'frozen_at':None, 'meta':{'demo':{'relation_demo':True}}}
    _require_demo_version(Cursor(row), 'b1', context)
    with pytest.raises(CapabilityBusinessError) as error:
        _require_demo_version(Cursor({**row, 'project_gid':'8002'}), 'b1', context)
    assert error.value.code == 'demo_project_scope_denied'


def test_normal_l5_version_still_cannot_be_reset(configured_demo):
    context = CapabilityContext(user_gid='7001', active_roles=('member',))
    with pytest.raises(CapabilityBusinessError) as error:
        _require_demo_version(Cursor({'gid':'b1','project_gid':'8001','project_code':'L5','frozen_at':None,'meta':{}}), 'b1', context)
    assert error.value.code == 'demo_version_required'


def test_revoked_project_responsibility_removes_demo_operation_access(configured_demo, monkeypatch):
    monkeypatch.setattr('backend.platform_sdk.project_access.can_edit_project_bop', lambda *args, **kwargs: False)
    context = CapabilityContext(user_gid='7001', active_roles=('member',))
    row = {'gid':'b1','project_gid':'8001','project_code':'L5','frozen_at':None,'meta':{'demo':{'relation_demo':True}}}
    with pytest.raises(CapabilityBusinessError) as error:
        _require_demo_version(Cursor(row), 'b1', context)
    assert error.value.code == 'demo_project_responsibility_required'


def test_unconfigured_actor_cannot_claim_permission_in_context(configured_demo):
    with pytest.raises(CapabilityBusinessError):
        _require_super_admin(CapabilityContext(user_gid='7002', active_roles=('member',), permissions=('craft.demo.relation',)))


def test_relation_plan_is_loaded_from_only_selected_version():
    class PlanCursor:
        def execute(self, query, params):
            assert 'WHERE gid=%s' in query
            assert params == ('b1',)
        def fetchone(self):
            return {'meta': {'demo': {'relation_plan': {'process_codes': {'DEMO-P-1':'p1'}}}}}
    assert _relation_plan(PlanCursor(), 'b1')['process_codes'] == {'DEMO-P-1':'p1'}
