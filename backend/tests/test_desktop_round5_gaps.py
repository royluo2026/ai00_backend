"""Round5 gap closure uses actual owner repositories and production Gateway."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest
from jsonschema import Draft202012Validator
from backend.capabilities.registry_next import CapabilityRegistry
from plugins.project_management.project_management_backend.capabilities import register_capabilities


def test_project_update_v2_is_closed_and_keeps_v1():
    registry=CapabilityRegistry();register_capabilities(registry)
    for kind in ('task','issue'):
        name=f'project.{kind}.change.apply.atomic.{kind}s_update'
        old=registry.get(name,1).descriptor
        entry=registry.get(name,2)
        assert old.output_schema['properties']['data']=={'type':'object','properties':{},'additionalProperties':False}
        validator=Draft202012Validator(entry.descriptor.input_schema)
        validator.validate({'arguments':{'gid':'item-one','updates':{'title':'Changed'}}})
        for updates in ({},{'owner_user_gid':'forged'},{'title':[]},{'attachments':[{'url':'file:///secret'}]}):
            assert list(validator.iter_errors({'arguments':{'gid':'item-one','updates':updates}}))
        Draft202012Validator(entry.descriptor.output_schema).validate({'data':{'success':True}})


def test_craft_rule_update_rejects_foreign_tenant_before_mutation():
    from plugins.craft.craft_backend.capabilities.rule_library import change_rule_library
    conn=MagicMock();conn.__enter__.return_value=conn;cur=conn.cursor.return_value.__enter__.return_value
    cur.fetchone.return_value={'gid':'rule-one','creator_gid':'other','owner_user_gid':'other','applicable_scope':{'team_gid':'other-team'}}
    with patch('plugins.craft.craft_backend.capabilities.rule_library.get_conn',return_value=conn):
        with pytest.raises(Exception):
            change_rule_library({'operation':'update','gid':'rule-one','record':{'name':'Forbidden'}},SimpleNamespace(user_gid='reader',team_gid='our-team',active_roles=('super_admin',)))
    assert not any(call.args[0].startswith('UPDATE') for call in cur.execute.call_args_list)


def test_gap_owner_handlers_through_real_gateway():
    from backend.tests.support.desktop_gateway_matrix import DesktopGatewayMatrix
    from backend.tests.support.desktop_round5_gap_fixtures import execute_gap_matrix
    rows=execute_gap_matrix(DesktopGatewayMatrix())
    assert len(rows)==9
