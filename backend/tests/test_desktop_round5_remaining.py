"""Real remaining owner services with only SQL/storage I/O replaced deterministically."""
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest
from jsonschema import Draft202012Validator
from backend.capabilities.registry_next import CapabilityRegistry
from backend.base.desktop_actions import register_desktop_capabilities
from backend.capability_v2.artifacts import ArtifactService, InMemoryArtifactStore, InMemoryObjectStorage
from backend.platform_sdk import artifacts
from plugins.craft.craft_backend.capabilities.desktop_exchange import register_desktop_exchange
from plugins.craft.craft_backend.capabilities.desktop_vpps import register_desktop_vpps
from plugins.craft.craft_backend.capabilities.desktop_pictures import reference_hash
from plugins.project_management.project_management_backend.capabilities import register_capabilities as register_project


def sql():
    conn=MagicMock();conn.__enter__.return_value=conn
    return conn,conn.cursor.return_value.__enter__.return_value


def execute_remaining_matrix(invoke=None):
    registry=CapabilityRegistry();register_desktop_capabilities(registry);register_desktop_exchange(registry);register_desktop_vpps(registry);register_project(registry)
    ctx=SimpleNamespace(user_gid='fixture-user',team_gid='fixture-team',active_roles=('super_admin',),permissions=('craft.read','knowledge.read','project.view'))
    rows=[]
    def call(capability_id,payload):
        entry=registry.get(capability_id,1)
        result=invoke(entry,payload,ctx) if invoke else entry.handler(payload,ctx)
        Draft202012Validator(entry.descriptor.input_schema).validate(payload)
        Draft202012Validator(entry.descriptor.output_schema).validate(result)
        rows.append({'id':capability_id,'version':1,'payload':payload,'provider_data':result,'input_schema':entry.descriptor.input_schema,'output_schema':entry.descriptor.output_schema})
        return result
    with ExitStack() as stack:
        conn,cursor=sql()
        cursor.fetchall.return_value=[{'gid':'template-one','name':'Fixture','module':'craft','owner_gid':ctx.user_gid,'config':{'columns':[{'key':'name','label':'Name','ui_ignored':True}],'styles':{'fontSize':12}},'is_shared':False}]
        stack.enter_context(patch('backend.platform_sdk.export_templates.get_conn',return_value=conn))
        stack.enter_context(patch('backend.base.desktop_actions._actor',return_value={'gid':ctx.user_gid}))
        stack.enter_context(patch('backend.platform_sdk.export_templates.next_gid',return_value='template-created'))
        result=call('base.export_template.list',{'module':'craft'})
        assert result['items'][0]['config']['columns']==[{'key':'name','label':'Name'}]
        assert cursor.execute.call_args.args[1]==(ctx.user_gid,'craft')
        created=call('base.export_template.create',{'name':'New template','module':'craft','config':{'columns':[{'key':'name'}]}})
        assert created['gid']=='template-created'
        assert cursor.execute.call_args.args[1][3]==ctx.user_gid
        cursor.fetchone.return_value={'owner_gid':ctx.user_gid}
        call('base.export_template.update',{'gid':'template-created','changes':{'name':'Renamed'}})
        assert cursor.execute.call_args.args[1]==['Renamed','template-created']
        cursor.fetchone.return_value={'owner_gid':'foreign'}
        with pytest.raises(Exception):registry.get('base.export_template.update',1).handler({'gid':'foreign','changes':{'name':'Forbidden'}},ctx)
        craft,cc=sql();cc.fetchone.return_value={'gid':'version-one','version_tag':'v1','name':'Fixture'}
        cc.fetchall.side_effect=[[{'gid':'part-one','level':3,'vpps':'missing','bom_row':'1'}],[],[]]
        stack.enter_context(patch('plugins.craft.craft_backend.capabilities.vpps_check.get_craft_conn',return_value=craft))
        result=call('craft.pbom.vpps_validation.get',{'snapshot_gid':'version-one'})
        assert result['summary']['rule1_errors']==1 and not result['summary']['ok']
        knowledge,kc=sql();kc.fetchone.return_value={'gid':'knowledge-one','scope_type':'private','creator_gid':ctx.user_gid}
        project,pc=sql();pc.fetchall.return_value=[{'id':1,'gid':'comment-one','content':'Fixture comment'}]
        stack.enter_context(patch('plugins.knowledge.knowledge_backend.infrastructure.repository.get_knowledge_conn',return_value=knowledge))
        stack.enter_context(patch('plugins.project_management.project_management_backend.infrastructure.repository.get_project_management_conn',return_value=project))
        result=call('project.knowledge_comment.list',{'item_gid':'knowledge-one'})
        assert result['entries'][0]['content']=='Fixture comment'
        assert kc.execute.call_args.args[1]==('knowledge-one',ctx.user_gid,ctx.team_gid)
        assert 'scope_type' in kc.execute.call_args.args[0]
        before=pc.execute.call_count;kc.fetchone.return_value=None
        with pytest.raises(Exception):registry.get('project.knowledge_comment.list',1).handler({'item_gid':'foreign'},ctx)
        assert pc.execute.call_count==before
        picture,pic=sql();pic.fetchone.return_value={'gid':'version-one','owner_gid':ctx.user_gid,'shared_team_gid':ctx.team_gid}
        record={'storage':'ois','object_key':'owned/picture.png','url':''}
        pic.fetchall.return_value=[{'process_flow_pic':[record],'process_chart_pic':[]}]
        stack.enter_context(patch('plugins.craft.craft_backend.capabilities.desktop_pictures.get_craft_conn',return_value=picture))
        from backend.tests.test_desktop_historical_attachments import LocalDatabase
        index=LocalDatabase()
        stack.enter_context(patch('backend.platform_sdk.historical_artifacts.get_conn',return_value=index))
        stack.enter_context(patch('backend.platform_sdk.historical_artifacts.get_user_summaries',return_value={ctx.user_gid:{'team_id':ctx.team_gid}}))
        service=ArtifactService(InMemoryArtifactStore(),InMemoryObjectStorage())
        stack.enter_context(patch.object(artifacts,'artifact_service',return_value=service))
        image=b'\x89PNG\r\n\x1a\nfixture'
        from backend.tests.test_desktop_historical_attachments import trust_fixture_upload
        trust_fixture_upload(index,'ois','owned/picture.png',image,'image/png',[{'owner_domain':'craft','parent_type':'bop_version','parent_gid':'version-one'}],owner=ctx.user_gid,tenant=ctx.team_gid)
        read=stack.enter_context(patch('backend.core.ois_storage.get_immutable',return_value=image))
        result=call('craft.bop.picture.resolve',{'version_gid':'version-one','reference_hash':reference_hash(record)})
        assert artifacts.read_artifact(result['artifact_ref'],ctx)==image
        assert read.call_args.kwargs['maximum']==5*1024*1024
        with pytest.raises(Exception):registry.get('craft.bop.picture.resolve',1).handler({'version_gid':'version-one','reference_hash':'0'*64},ctx)
        assert read.call_count==1
    return rows


def test_remaining_owner_handlers_visibility_hash_and_closed_outcomes():
    assert len(execute_remaining_matrix())==6


def test_historical_image_reader_refuses_unconfigured_urls_and_path_escape(tmp_path):
    from backend.platform_sdk.business_images import read_stored_image
    with patch('backend.core.storage._get_minio_config',return_value={}),patch('backend.core.ois_storage._get_ois_config',return_value={}):
        for url in ('https://attacker.invalid/private','/static/uploads/bop_pics/../secret.png'):
            with pytest.raises(ValueError):read_stored_image({'url':url},static_root=tmp_path)
