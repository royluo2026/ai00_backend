"""Execute the registered Agent actions against deterministic SQL and HTTP ports."""
import asyncio
from contextlib import ExitStack
from datetime import datetime
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import httpx
from jsonschema import Draft202012Validator
from backend.capabilities.registry_next import CapabilityRegistry
from backend.platform_sdk.request_credentials import authenticated_transport_scope
from plugins.agent.agent_backend.application import AgentApplication
from plugins.agent.agent_backend.infrastructure import AgentCapabilityRepository
from plugins.agent.agent_backend.data.audit_repository import AuditRepository
from plugins.agent.agent_backend.data.session_repository import SessionRepository
from plugins.agent.agent_backend.capabilities.desktop_actions import register_desktop_agent_capabilities, DEFINITIONS

PAYLOADS = {
    'agent.skill.create': {'name':'fixture_skill','title':'Fixture Skill','skill_type':'prompt','visibility':'private','content':{'template':'Hello'}},
    'agent.skill.update': {'skill_gid':'skill-one','changes':{'title':'Updated Skill','content':{'template':'Updated'}}},
    'agent.session.list': {}, 'agent.audit.search': {'limit':5,'offset':0},
    'agent.tool_catalog.list': {}, 'agent.flow.capability_manifest.get': {},
    'agent.interaction.cancel': {'session_gid':'session-one'},
    'agent.runtime.config.set': {'model':'pi','api_base':'https://runtime.invalid','api_key':'private-fixture-key'},
    'agent.runtime.connection.test': {},
    'agent.interaction.chat.change.apply': {'operation':'chat_sync','body':{'message':'Hello','context':{'text':'Fixture'}}},
}

def execute_agent_matrix(invoke=None):
    rows = []
    for capability_id, version in [(d[0],d[1]) for d in DEFINITIONS] + [('agent.interaction.chat.change.apply',3)]:
        conn = MagicMock()
        conn.__enter__.return_value = conn
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.rowcount = 1
        cursor.fetchone.return_value = {'total':1,'gid':'skill-one','is_system':False,'owner_gid':'fixture-user'}
        cursor.fetchall.return_value = []
        if capability_id == 'agent.session.list':
            cursor.fetchall.return_value = [{'gid':'session-one','title':'Fixture','created_at':datetime(2026,9,8),'updated_at':datetime(2026,9,8)}]
        if capability_id == 'agent.audit.search':
            cursor.fetchall.return_value = [{'id':1,'gid':'audit-one','session_gid':'session-one','user_gid':'fixture-user','tool_name':'Fixture','is_write':False,'is_confirmed':False,'inputs_json':'{}','result_json':'{}','resource_gid':'','resource_type':'','status':'ok','created_at':datetime(2026,9,8)}]
        transaction = MagicMock()
        registry = CapabilityRegistry()
        provider = AgentApplication(AgentCapabilityRepository(),AuditRepository(connection_factory=lambda:conn),SessionRepository(connection_factory=lambda:conn),None)
        register_desktop_agent_capabilities(registry,provider,lambda:transaction)
        context = SimpleNamespace(user_gid='fixture-user',team_gid='fixture-team',active_roles=('super_admin',),request_id='fixture-'+capability_id)
        remote_calls = []
        def remote(request):
            remote_calls.append({'method':request.method,'path':request.url.path})
            data = {'ok':True} if request.url.path == '/health' else {'data':{'gid':'session-one','runId':'run-one','text':'Fixture answer'}}
            return httpx.Response(200,json=data)
        real_client = httpx.Client
        with ExitStack() as stack:
            stack.enter_context(patch('plugins.agent.agent_backend.infrastructure.repository.get_agent_conn',return_value=conn))
            stack.enter_context(patch.dict('os.environ',{'ALLOW_LOCAL_RUNTIME_SECRET_ADMIN':'1','AI00_AGENT_RUNTIME_MODE':'pi','AI00_AGENT_RUNTIME_URL':'https://runtime.invalid'}))
            stack.enter_context(patch('plugins.agent.agent_backend.routers.agent_runtime_proxy_next.httpx.Client',side_effect=lambda **kw:real_client(transport=httpx.MockTransport(remote))))
            secret_store = MagicMock()
            secret_store.load.return_value = {}
            stack.enter_context(patch('plugins.agent.agent_backend.infrastructure.runtime_secret_store.runtime_secret_store',return_value=secret_store))
            entry = registry.get(capability_id,version)
            payload = PAYLOADS[capability_id]
            with authenticated_transport_scope('trusted-fixture-credential'):
                result = invoke(entry,payload,context) if invoke else entry.handler(payload,context)
                if asyncio.iscoroutine(result): result = asyncio.run(result)
            data = result.data if hasattr(result,'data') else result
            Draft202012Validator(entry.descriptor.input_schema).validate(payload)
            Draft202012Validator(entry.descriptor.output_schema).validate(data)
            assert 'trusted-fixture-credential' not in json.dumps(data)
            assert 'private-fixture-key' not in json.dumps(data)
            rows.append({'id':capability_id,'version':version,'payload':payload,'provider_data':data,'input_schema':entry.descriptor.input_schema,'output_schema':entry.descriptor.output_schema,'sql_statements':[call.args[0] for call in cursor.execute.call_args_list],'runtime_requests':remote_calls,'outbox_count':transaction.record_outbox.call_count})
    return rows
