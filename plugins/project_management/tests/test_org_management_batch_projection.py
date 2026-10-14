import asyncio
from contextlib import nullcontext
from types import SimpleNamespace
from plugins.project_management.project_management_backend.application import org_management


def test_batch_projection_has_independent_replay_keys_and_reports_failure(monkeypatch):
    events = []
    lines = [{'gid': gid, 'leader_user_gids': ['u'], 'bop_line_gid': gid} for gid in ['a', 'b']]
    repo = SimpleNamespace(
        project=lambda gid: {'gid': gid, 'team_id': 't', 'is_deleted': False},
        apply=lambda **kw: {'operation_gid': 'op', 'revision': 2, 'status': 'pending_projection'},
        pending_projection=lambda *args: {'line': {'lines': lines}, 'revision': 2},
        complete_projection=lambda *args: events.append('complete'),
        fail_projection=lambda *args: events.append('failed'))
    monkeypatch.setattr(org_management, 'OrgManagementRepository', lambda: repo)
    monkeypatch.setattr('backend.capability_v2.identity.IdentityBroker.for_worker', lambda *args, **kw: object())
    monkeypatch.setattr('backend.capability_v2.official_service_grants.official_service_identities.trusted_tenant', lambda **kw: nullcontext())
    async def invoke(call, *args):
        if call.capability_id == 'base.project_responsibility.projection.apply':
            events.append(call.payload)
        return SimpleNamespace(ok=True, data={})
    context = SimpleNamespace(team_gid='t', user_gid='admin', active_roles=('super_admin',), effective_identity=object(), domain_client=SimpleNamespace(invoke=invoke))
    payload = {'operation': 'managed_line.assign', 'arguments': {'project_gid': 'p', 'line_gids': ['a', 'b'], 'leader_user_gids': ['u']}, 'expected_revision': 1, 'idempotency_key': 'key'}
    result = asyncio.run(org_management.change(payload, context))
    assert result['data']['status'] == 'completed'
    assert [event['operation_gid'] for event in events if isinstance(event, dict)] == ['op:a', 'op:b']
    assert events[-1] == 'complete'
    events.clear()
    async def fail_second(call, *args):
        if call.capability_id == 'base.project_responsibility.projection.apply' and call.payload['source_gid'] == 'b':
            return SimpleNamespace(ok=False, error=SimpleNamespace(message='unavailable'))
        return await invoke(call, *args)
    context.domain_client.invoke = fail_second
    assert asyncio.run(org_management.change(payload, context))['data']['status'] == 'failed_retryable'
    assert events[-1] == 'failed'
