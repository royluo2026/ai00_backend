from contextlib import ExitStack
import hashlib
import io
from types import SimpleNamespace
from unittest.mock import patch
import httpx
import pytest
from jsonschema import Draft202012Validator
from backend.capabilities.registry_next import CapabilityRegistry
from backend.capability_v2.artifacts import ArtifactService, InMemoryArtifactStore, InMemoryObjectStorage, ArtifactError
from backend.platform_sdk import artifacts
from backend.base.desktop_artifacts import DEFINITIONS as FILES
from backend.base.desktop_actions import register_desktop_capabilities
from plugins.craft.craft_backend.capabilities.desktop_exchange import DEFINITIONS, register_desktop_exchange


def execute_file_matrix(invoke=None):
    store=InMemoryArtifactStore();storage=InMemoryObjectStorage();service=ArtifactService(store,storage)
    ctx=SimpleNamespace(user_gid='fixture-user',team_gid='fixture-team',active_roles=('super_admin',))
    registry=CapabilityRegistry();register_desktop_capabilities(registry);register_desktop_exchange(registry)
    with ExitStack() as stack:
        stack.enter_context(patch.object(artifacts,'artifact_service',return_value=service))
        stack.enter_context(patch('backend.base.desktop_actions._actor',return_value={'gid':ctx.user_gid}))
        stack.enter_context(patch('backend.services.user_service.get_feishu_token',return_value='private-fixture-feishu-token'))
        calls=[]
        def remote(request):
            calls.append((request.method,request.url.path))
            assert request.headers['Authorization']=='Bearer private-fixture-feishu-token'
            return httpx.Response(200,json={'code':0,'data':{'valueRange':{'values':[['Name'],['Fixture']]},'items':[{'fields':{'Name':'Fixture'}}],'has_more':False}})
        real_client=httpx.Client
        stack.enter_context(patch('plugins.craft.craft_backend.capabilities.lark_exchange.httpx.Client',side_effect=lambda **kw:real_client(transport=httpx.MockTransport(remote))))
        stack.enter_context(patch('plugins.craft.craft_backend.capabilities.data_exchange.httpx.put',side_effect=lambda url,headers,json,timeout:real_client(transport=httpx.MockTransport(remote)).put(url,headers=headers,json=json)))
        source=artifacts.create_artifact(b'Name,Value\nFixture,1\n','text/csv',ctx)
        adoption={'artifact_ref':source,'name':'fixture.csv'}
        diff={'columns':[{'key':'name','label':'Name','width':15}],'diff_rows':[{'status':'modified','values_a':['Old'],'values_b':['New'],'changed_fields':['name']}]}
        payloads={
            'base.artifact.import':adoption,'base.artifact.get':adoption,'base.artifact.bytes.get':{'artifact_ref':source},'base.artifact.batch.import':{'artifacts':[adoption]},
            'base.artifact.text.get':{'artifact_ref':source},'base.artifact.text.create':{'name':'fixture.md','content':'# Fixture','media_type':'text/markdown'},
            'base.artifact.revise':{**adoption,'previous_artifact_ref':source},
            'craft.data_exchange.excel.parse':adoption,
            'craft.data_exchange.excel.export':{'columns':[{'key':'name','label':'Name','width':15}],'rows':[['Fixture']],'filename':'fixture.xlsx'},
            'craft.data_exchange.diff_report.export':{**diff,'filename':'diff.xlsx'},
            'craft.data_exchange.feishu_diff.write':{**diff,'spreadsheet_token':'sheet-one','sheet_id':'Sheet1'},
            'craft.data_exchange.feishu_sheet.write':{'spreadsheet_token':'sheet-one','sheet_id':'Sheet1','headers':['Name'],'rows':[['Fixture']]},
            'craft.data_exchange.feishu_sheet.read':{'spreadsheet_token':'sheet-one','sheet_range':'Sheet1!A1:Z1000'},
            'craft.data_exchange.feishu_bitable.read':{'app_token':'app-one','table_id':'table-one','page_size':500},
            'craft.data_exchange.feishu_bitable.write':{'app_token':'app-one','table_id':'table-one','headers':['Name'],'rows':[['Fixture']]},
        }
        rows=[]
        for capability_id,payload in payloads.items():
            entry=registry.get(capability_id,1)
            result=invoke(entry,payload,ctx) if invoke else entry.handler(payload,ctx)
            Draft202012Validator(entry.descriptor.input_schema).validate(payload)
            Draft202012Validator(entry.descriptor.output_schema).validate(result)
            assert 'private-fixture-feishu-token' not in str(result)
            if capability_id.endswith('.export'):
                import openpyxl
                data=artifacts.read_artifact(result['artifact_ref'],ctx)
                assert openpyxl.load_workbook(io.BytesIO(data)).active.max_row>=2
            rows.append({'id':capability_id,'version':1,'payload':payload,'provider_data':result,'input_schema':entry.descriptor.input_schema,'output_schema':entry.descriptor.output_schema,'runtime_requests':list(calls)})
        assert rows[7]['provider_data']['data']['rows']==[['Fixture','1']]
        with pytest.raises(ArtifactError): artifacts.read_artifact(source,SimpleNamespace(user_gid='foreign',team_gid='fixture-team',active_roles=('member',)))
        with pytest.raises(ValueError): artifacts.require_artifact({**source,'sha256':'0'*64},ctx)
        storage._objects[next(iter(storage._objects))]=b'tampered'
        with pytest.raises(ArtifactError): artifacts.read_artifact(source,ctx)
        return rows


def test_real_artifact_parse_export_feishu_handlers_and_foreign_or_tampered_rejection():
    assert len(execute_file_matrix())==15
