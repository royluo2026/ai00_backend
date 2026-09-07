"""Real registered handlers with deterministic repository ports for route migration."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from backend.capabilities.registry_next import CapabilityRegistry
from backend.tests.support.desktop_handler_fixtures import Connection, Clock


def execute():
    from plugins.craft.craft_backend.capabilities import register_capabilities
    from plugins.craft.craft_backend.capabilities import vpps_audit
    from plugins.craft.craft_backend.vpps_audit import service
    from backend.base.web_atomic import register_atomic_web_capabilities
    registry = CapabilityRegistry()
    register_capabilities(registry)
    register_atomic_web_capabilities(registry)
    context = SimpleNamespace(user_gid='fixture-user', team_gid='fixture-team', active_roles=('super_admin',))
    rows = []

    def call(capability_id, payload, method, route, body=None, path=None, query=''):
        entry = registry.get(capability_id, 1)
        value = entry.handler(deepcopy(payload), context)
        result = value.data if hasattr(value, 'data') else value
        rows.append(dict(id=capability_id, version=1, payload=payload, provider_data=result,
                         method=method, route=route, body=body or {}, path=path or {}, query=query,
                         input_schema=entry.descriptor.input_schema, output_schema=entry.descriptor.output_schema))

    class Operations:
        def __init__(self): self.items = []
        def get_active_rule4_ignores(self, version): return {x.pbom_row_gid for x in self.items if x.is_active and x.pbom_version_gid == version}
        def save_batch(self, values): self.items.extend(values)
        def revert(self, gid, actor, name):
            original = next((x for x in self.items if x.gid == gid and x.is_active), None)
            if original is None: return None
            value = replace(original, is_active=False, reverted_by_gid=actor, reverted_by_name=name, reverted_at=Clock.now())
            self.items[self.items.index(original)] = value
            return value

    repository, connection = Operations(), Connection()
    with patch.object(vpps_audit, 'get_conn', return_value=connection), patch.object(vpps_audit, 'MySqlVppsOperationRepository', return_value=repository), patch.object(service, 'next_gid', return_value='operation-one'), patch.object(service, 'datetime', SimpleNamespace(now=lambda **kwargs: Clock.now())):
        body = {'pbom_version_gid':'version-one', 'rows':[{'pbom_row_gid':'row-one', 'original_vpps_desc':'Fixture'}], 'actor_gid':'fixture-user', 'actor_name':'Fixture user'}
        call('craft.vpps_audit.change.apply', {'operation':'rule4_bulk_ignore', **body}, 'POST', '/api/vpps-operations/rule4-bulk-ignore', body)
        call('craft.vpps_audit.change.apply', {'operation':'revert', 'gid':'operation-one', 'actor_gid':'fixture-user', 'actor_name':'Fixture user'}, 'POST', '/api/vpps-operations/{gid}/revert', {'reverted_by_gid':'fixture-user','reverted_by_name':'Fixture user'}, {'gid':'operation-one'})
        assert connection.commits == 2 and repository.items[0].is_active is False

    from backend.base import structural_web
    from backend.services import user_service
    sql = MagicMock(); sql.__enter__.return_value = sql
    cursor = sql.cursor.return_value.__enter__.return_value
    with patch.object(structural_web, 'get_conn', return_value=sql), patch.object(user_service, 'get_conn', return_value=sql):
        cursor.fetchall.return_value = [{'gid':'team-one','name':'Fixture team','is_active':True,'parent_team_gid':None,'created_at':'2026-09-08'}]
        call('base.team.directory.list', {}, 'GET', '/teams')
        cursor.fetchall.return_value = [{'gid':'user-one','name':'Fixture user','email':'user@example.invalid','avatar_url':'','is_active':True}]
        call('base.identity.admin_user.list', {}, 'GET', '/users/')
        call('base.identity.user.search', {'query':'Fixture','limit':10}, 'GET', '/users/search', query='q=Fixture&limit=10')
        assert cursor.execute.call_count == 3
        assert cursor.execute.call_args.args[1] == ('%Fixture%', '%Fixture%', 10)
    return rows


if __name__ == '__main__':
    import json
    from pathlib import Path
    target = Path(__file__).resolve().parents[1] / 'fixtures/desktop_round4_outcomes.json'
    target.write_text(json.dumps({'fixture_kind':'Real registered handlers and actual owner services, deterministic repository/SQL ports; no live database or runtime approval', 'rows':execute()}, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
