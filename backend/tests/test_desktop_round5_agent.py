from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import asyncio
import pytest
from jsonschema import Draft202012Validator
from backend.capabilities.registry_next import CapabilityRegistry
from plugins.agent.agent_backend.capabilities import register_capabilities


def test_every_agent_action_executes_its_real_application_and_repository():
    from backend.tests.support.desktop_round5_agent_fixtures import execute_agent_matrix
    rows = execute_agent_matrix()
    assert len(rows) == 10
    assert next(row for row in rows if row['id']=='agent.interaction.chat.change.apply')['runtime_requests'][-1]['path'].endswith('/messages')


def test_closed_agent_desktop_registrations_preserve_legacy_majors():
    registry = CapabilityRegistry()
    register_capabilities(registry, canvas_runtime=None)
    for capability_id, version in (
        ('agent.interaction.chat.change.apply', 3), ('agent.skill.create', 1),
        ('agent.skill.update', 1), ('agent.session.list', 1), ('agent.audit.search', 1),
        ('agent.tool_catalog.list', 1), ('agent.flow.capability_manifest.get', 1),
        ('agent.runtime.connection.test', 1), ('agent.runtime.config.set', 1),
        ('agent.interaction.cancel', 2),
    ):
        entry = registry.get(capability_id, version)
        assert entry.spec.owner == 'agent'
        validator = Draft202012Validator(entry.descriptor.input_schema)
        assert not validator.is_valid({'auth_token': 'forged'})
        assert entry.descriptor.output_schema['additionalProperties'] is False


def test_skill_create_executes_actual_repository_and_owner_bound_transaction():
    registry = CapabilityRegistry()
    transaction = MagicMock()
    register_capabilities(registry, canvas_runtime=None, transaction_factory=lambda: transaction)
    entry = registry.get('agent.skill.create', 1)
    conn = MagicMock()
    conn.__enter__.return_value = conn
    cursor = conn.cursor.return_value.__enter__.return_value
    payload = {'name': 'fixture_skill', 'title': 'Fixture', 'skill_type': 'prompt', 'content': {'template': 'Hello {{name}}', 'variables': [{'name':'name','label':'Name','required':True,'default':''}], 'system_hint':''}}
    context = SimpleNamespace(user_gid='owner', team_gid='team', active_roles=('member',), request_id='fixture-request')
    with patch('plugins.agent.agent_backend.infrastructure.repository.get_agent_conn', return_value=conn):
        result = entry.handler(payload, context)
    assert result.data['success'] is True
    assert cursor.execute.call_args.args[1][7:9] == ('owner', 'team')
    assert transaction.commit.call_count == 1
    assert transaction.record_outbox.call_args.args[:2] == ('agent.skill.create', 1)


def test_chat_v3_uses_only_scoped_transport_credential():
    from backend.platform_sdk.request_credentials import authenticated_transport_scope, downstream_runtime_credential
    from plugins.agent.agent_backend.capabilities.desktop_actions import chat
    from plugins.agent.agent_backend.routers import ai_chat
    seen=[]
    def owner(body, user, token):
        seen.append((body,user,token))
        return {'answer':'Fixture answer','session_id':'session-one'}
    with patch.object(ai_chat,'_legacy_chat_sync',owner):
        with authenticated_transport_scope('trusted-main-credential'):
            result=asyncio.run(chat({'operation':'chat_sync','body':{'message':'hello','context':{'text':'Fixture context'}}},SimpleNamespace(user_gid='actor')))
    assert seen[0][0] == {'message':'hello','context':{'text':'Fixture context'}}
    assert seen[0][2] == 'trusted-main-credential'
    assert downstream_runtime_credential() == ''
    assert 'trusted-main-credential' not in str(result)


def test_canonical_transport_can_consume_its_gateway_stream():
    from backend.routers import capabilities
    from backend.capability_v2.contracts import CapabilityResultV2, CapabilityStatus, CorrelationRef
    assert hasattr(capabilities,'_stream_response'), 'canonical invoke has no bounded stream projection'
    result=CapabilityResultV2(ok=True,status=CapabilityStatus.COMPLETED,capability_id='agent.interaction.chat.change.apply',major_version=3,
        data={'data':{'stream_id':'capability-stream-'+'a'*32,'media_type':'text/event-stream'}},correlation=CorrelationRef(request_id='stream-one')).model_copy(update={'status':CapabilityStatus.ACCEPTED})
    async def iterator():
        yield 'data: {"type":"token","content":"hello"}\n\n'
        yield 'data: {"type":"done","session_id":"session-one"}\n\n'
    class Gateway:
        async def claim_stream(self,stream_id):
            assert stream_id=='capability-stream-'+'a'*32
            return iterator(),'text/event-stream'
    async def exercise():
        response=await capabilities._stream_response(result,Gateway())
        text=''.join([chunk.decode() if isinstance(chunk,bytes) else chunk async for chunk in response.body_iterator])
        assert 'capability_result' in text and 'hello' in text
    asyncio.run(exercise())
