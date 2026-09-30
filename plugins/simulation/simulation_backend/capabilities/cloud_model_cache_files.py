"""Exact cached file membership; download admission is separate from viewer opening."""
import json
import re
from datetime import UTC,timedelta
from ..data.cloud_model_cache_repository import CacheError,digest
from .connector_contracts import obj,ARTIFACT_REF,TC_GEOMETRY_REF,TC_VISUALIZATION_SOURCE_SELECTOR
from .cloud_model_cache import CloudModelCacheProvider,BATCH,BID,TEXT
from backend.capability_v2.provider_contracts import CapabilitySpec,CapabilityRisk,CapabilityBusinessError


def member(repo,batch_id,tenant_gid,node_key,dataset_uid,file_uid,**pins):
    result=repo.query_pinned(batch_id,tenant_gid,scope='node',node_key=node_key,projection='properties',**pins)
    node=result['nodes'][0]
    refs=node['geometry_refs']
    if refs is None:raise CacheError('cache_file_references_unavailable')
    matches=[ref for ref in refs if ref.get('dataset_uid')==dataset_uid and ref.get('file_uid')==file_uid and ref.get('relation_type')=='IMAN_Rendering' and ref.get('file_name','').lower().endswith('.jt')]
    if len(matches)!=1:raise CacheError('cache_file_not_referenced')
    return result['identity'],node['item_revision_uid'],matches[0]


from .cloud_model_cache_file_contracts import (IDENTITY,PIN,GENERATION,REQUEST,FILE_INPUT,FILE_OUTPUT,FILE_CONTRACT,ADMISSION,RESULT,
    BATCH_REQUEST,BATCH_ADMISSION,BATCH_RESULT_INPUT,BATCH_RESULT,PREFLIGHT_INPUT,PREFLIGHT_RESULT,PREFLIGHT_CONTRACT)

_FILE_HASH=re.compile(r'^sha256:[a-f0-9]{64}$')


def normalize_batch_files(files):
    if not isinstance(files,list) or not 1<=len(files)<=8:
        raise CacheError('cache_file_batch_size_invalid')
    normalized=[];seen=set()
    for item in files:
        if not isinstance(item,dict) or set(item)-{'node_key','dataset_uid','file_uid','expected_content_hash'}:
            raise CacheError('cache_file_batch_member_invalid')
        if any(not isinstance(item.get(key),str) or not item[key] or len(item[key])>512 for key in ('node_key','dataset_uid','file_uid')):
            raise CacheError('cache_file_batch_member_invalid')
        expected=item.get('expected_content_hash')
        if expected is not None and (not isinstance(expected,str) or not _FILE_HASH.fullmatch(expected)):
            raise CacheError('cache_file_batch_member_invalid')
        key=(item['node_key'],item['dataset_uid'],item['file_uid'])
        if key in seen:raise CacheError('cache_file_batch_duplicate_member')
        seen.add(key)
        normalized.append({**item})
    return normalized


def require_file_runtime(runtime,now,*,batch=False):
    from .connector_runtime import ConnectorError,DIRECT_VISMOCKUP_OPERATIONS
    try:
        heartbeat=runtime['heartbeat_at'];expiry=runtime['session_expires_at']
        heartbeat=heartbeat.replace(tzinfo=UTC) if heartbeat.tzinfo is None else heartbeat.astimezone(UTC)
        expiry=expiry.replace(tzinfo=UTC) if expiry.tzinfo is None else expiry.astimezone(UTC)
        if heartbeat<=now-timedelta(minutes=2) or expiry<=now:raise ConnectorError('connector_offline')
        raw=runtime['adapter_health_json'];health=json.loads(raw) if isinstance(raw,str) else raw
        if (health['runtime_generation'],health['runtime_instance_id'])!=(runtime['runtime_generation'],runtime['current_runtime_instance_id']):raise ConnectorError('adapter_health_unavailable')
        required=[DIRECT_VISMOCKUP_OPERATIONS['tc_file']]
        if batch:required.append(DIRECT_VISMOCKUP_OPERATIONS['tc_file_preflight'])
        operations=health['adapter']['operations']
        if health['adapter']['adapter_id']!='ai00.vismockup' or any(not any(item.get('operation_id')==operation and item.get('contract_hash')==contract for item in operations) for operation,contract in required):raise ConnectorError('adapter_contract_mismatch')
    except (KeyError,ValueError,TypeError,AttributeError) as exc:raise ConnectorError('adapter_health_unavailable') from exc


class CacheFileProvider:
    def __init__(self,cache=None,connector=None):
        from .connector_runtime import connector_control_plane
        self.cache=cache or CloudModelCacheProvider();self.connector=connector or connector_control_plane

    def source(self,payload,context):
        batch=self.cache._read(payload['batch_id'],context)
        pins={key:payload.get(key) for key in ('expected_generation','expected_snapshot_hash')}
        identity,revision,reference=member(self.cache.repo,payload['batch_id'],context.team_gid,payload['node_key'],payload['dataset_uid'],payload['file_uid'],**pins)
        return batch,identity,revision,reference

    def request(self,payload,context):
        raise CapabilityBusinessError('cache_jt_upload_disabled','JT 仅支持在客户端按需从 TC/FMS 下载，请升级数模仿真客户端。')

    def admit(self,payload,context):
        from .connector_runtime import _direct_vismockup_plan_v2,ConnectorError
        try:
            batch,identity,revision,reference=self.source(payload,context)
            runtime=self.connector.repository.bound_runtime_for_user(context.user_gid,context.team_gid)
            if not runtime:raise CacheError('connector_offline')
            require_file_runtime(runtime,self.connector.clock())
            packet={**identity,'source_selector':batch['source_selector'],'node_key':payload['node_key'],'item_revision_uid':revision,'file_ref':reference,'expected_content_hash':payload.get('expected_content_hash'),'artifact_resource_refs':['simulation://model-cache/'+batch['batch_id']]}
            plan=_direct_vismockup_plan_v2(action='tc_file',connector_id=runtime['device_id'],payload=packet,context=context,now=self.connector.clock(),capability_id='simulation.model_cache.file.fetch.request')
            existing=self.connector.repository.get_plan_result(plan['plan_id'],context.user_gid,context.team_gid)
            operation=plan['plan_id'] if existing else self.connector.queue_v2(plan,context,runtime_row=runtime).operation_id
            return self.cache.output({'operation_id':operation,'identity':identity,'node_key':payload['node_key'],'item_revision_uid':revision,'file_ref':reference,'status':existing['status'] if existing else 'queued'})
        except (CacheError,ConnectorError) as exc:raise CapabilityBusinessError(str(exc),str(exc)) from exc

    def request_batch(self,payload,context):
        raise CapabilityBusinessError('cache_jt_upload_disabled','JT 仅支持在客户端按需从 TC/FMS 下载，请升级数模仿真客户端。')

    def admit_batch(self,payload,context):
        from .connector_runtime import _direct_vismockup_plan_v2,build_file_batch_steps,ConnectorError
        try:
            files=normalize_batch_files(payload['files'])
            batch=self.cache._read(payload['batch_id'],context)
            pins={key:payload.get(key) for key in ('expected_generation','expected_snapshot_hash')}
            identity=None;members=[]
            for item in files:
                current,revision,reference=member(self.cache.repo,payload['batch_id'],context.team_gid,
                    item['node_key'],item['dataset_uid'],item['file_uid'],**pins)
                if identity is not None and current!=identity:raise CacheError('cache_snapshot_mismatch')
                identity=current
                members.append({**current,'node_key':item['node_key'],'item_revision_uid':revision,
                    'file_ref':reference,'expected_content_hash':item.get('expected_content_hash')})
            runtime=self.connector.repository.bound_runtime_for_user(context.user_gid,context.team_gid)
            if not runtime:raise CacheError('connector_offline')
            require_file_runtime(runtime,self.connector.clock(),batch=True)
            steps=build_file_batch_steps(identity,batch['source_selector'],members)
            plan=_direct_vismockup_plan_v2(action='tc_file',connector_id=runtime['device_id'],payload={},context=context,
                now=self.connector.clock(),capability_id='simulation.model_cache.file.fetch.batch.request',steps_override=steps)
            existing=self.connector.repository.get_plan_result(plan['plan_id'],context.user_gid,context.team_gid)
            operation=plan['plan_id'] if existing else self.connector.queue_v2(plan,context,runtime_row=runtime).operation_id
            status=existing['status'] if existing else 'queued'
            selected=[{**{key:value for key,value in m.items() if key in ('node_key','item_revision_uid','file_ref')},
                       'step_id':f'step-{index+2:05d}'} for index,m in enumerate(members)]
            return self.cache.output({'operation_id':operation,'identity':identity,'status':status,'files':selected})
        except (CacheError,ConnectorError) as exc:raise CapabilityBusinessError(str(exc),str(exc)) from exc

    def result(self,payload,context):
        try:
            batch,identity,revision,reference=self.source(payload,context)
            with self.cache.repo.connect() as conn,conn.cursor() as cur:
                cur.execute('SELECT plan_json FROM workmanship_sim_connector_runtime_plans WHERE plan_id=%s AND actor_gid=%s AND tenant_gid=%s',(payload['operation_id'],context.user_gid,context.team_gid))
                row=cur.fetchone()
            if not row:raise CacheError('cache_file_operation_not_found')
            from ..data.cache_file_receipt_validation import validate_cached_file_result
            plan=json.loads(row['plan_json'])
            operation=self.connector.repository.get_plan_result(payload['operation_id'],context.user_gid,context.team_gid)
            if not operation:raise CacheError('cache_file_operation_not_found')
            return self.cache.output(validate_cached_file_result(identity,payload['node_key'],revision,reference,payload.get('expected_content_hash'),payload['operation_id'],plan,operation))
        except (CacheError,ValueError,KeyError,TypeError) as exc:
            code=str(exc) if isinstance(exc,CacheError) else 'cache_file_result_invalid'
            raise CapabilityBusinessError(code,code) from exc

    def batch_result(self,payload,context):
        try:
            files=normalize_batch_files(payload['files'])
            batch=self.cache._read(payload['batch_id'],context)
            pins={key:payload.get(key) for key in ('expected_generation','expected_snapshot_hash')}
            identity=None;members=[]
            for index,item in enumerate(files,start=2):
                current,revision,reference=member(self.cache.repo,payload['batch_id'],context.team_gid,
                    item['node_key'],item['dataset_uid'],item['file_uid'],**pins)
                if identity is not None and current!=identity:raise CacheError('cache_snapshot_mismatch')
                identity=current
                members.append({**current,'node_key':item['node_key'],'item_revision_uid':revision,'file_ref':reference,
                    'expected_content_hash':item.get('expected_content_hash'),'step_id':f'step-{index:05d}'})
            with self.cache.repo.connect() as conn,conn.cursor() as cur:
                cur.execute('SELECT plan_json FROM workmanship_sim_connector_runtime_plans WHERE plan_id=%s AND actor_gid=%s AND tenant_gid=%s',(payload['operation_id'],context.user_gid,context.team_gid))
                row=cur.fetchone()
            if not row:raise CacheError('cache_file_operation_not_found')
            plan=json.loads(row['plan_json'])
            if plan.get('plan_id')!=payload['operation_id'] or plan.get('actor_id')!=context.user_gid or plan.get('tenant_id')!=context.team_gid:
                raise CacheError('cache_file_operation_mismatch')
            operation=self.connector.repository.get_plan_result(payload['operation_id'],context.user_gid,context.team_gid)
            if not operation:raise CacheError('cache_file_operation_not_found')
            from ..data.cache_file_receipt_validation import validate_cached_file_batch_result
            return self.cache.output(validate_cached_file_batch_result(identity,members,payload['operation_id'],plan,operation))
        except (CacheError,ValueError,KeyError,TypeError) as exc:
            code=str(exc) if isinstance(exc,CacheError) else 'cache_file_result_invalid'
            raise CapabilityBusinessError(code,code) from exc


def specs(provider=None):
    from backend.capability_v2.reliability import transactional_provider
    provider=provider or CacheFileProvider()
    @transactional_provider
    def request(payload,context):return provider.request(payload,context)
    def local_only(payload,context):raise CapabilityBusinessError('local_runtime_required','local_runtime_required')
    yield CapabilitySpec(id='simulation.teamcenter.model_file.fetch',version=1,owner='simulation',description='Acquire the exact cached ImanFile through TC FMS and publish a verified immutable JT artifact without opening a viewer.',execution='local',risk=CapabilityRisk.WRITE,confirmation='none',permissions=('simulation.use',),input_schema=FILE_INPUT,output_schema=FILE_OUTPUT,tags=('experimental',)),local_only
    yield CapabilitySpec(id='simulation.model_cache.file.fetch.request',version=1,owner='simulation',description='Request immutable acquisition of one exact JT reference belonging to an authorized fixed completed cache node.',risk=CapabilityRisk.WRITE,confirmation='none',permissions=('simulation.use',),input_schema=REQUEST,output_schema=ADMISSION,tags=('experimental',)),request
    yield CapabilitySpec(id='simulation.model_cache.file.fetch.result',version=1,owner='simulation',description='Read the exact file acquisition state and verified artifact bound to the selected cache node and request.',risk=CapabilityRisk.READ,confirmation='none',permissions=('simulation.use',),input_schema=obj({**REQUEST['properties'],'operation_id':TEXT},(*REQUEST['required'],'operation_id')),output_schema=RESULT,tags=('experimental',)),provider.result
    yield CapabilitySpec(id='simulation.teamcenter.model_files.size.preflight',version=1,owner='simulation',description='Read ImanFile sizes for up to eight exact cached JT references and reject before download when a multi-file group exceeds 100 MiB or a single JT exceeds 512 MiB.',execution='local',risk=CapabilityRisk.READ,confirmation='none',permissions=('simulation.use',),input_schema=PREFLIGHT_INPUT,output_schema=PREFLIGHT_RESULT,tags=('experimental',)),local_only
    @transactional_provider
    def request_batch(payload,context):return provider.request_batch(payload,context)
    yield CapabilitySpec(id='simulation.model_cache.file.fetch.batch.request',version=1,owner='simulation',description='Queue one fixed-snapshot Teamcenter preflight and up to eight independently receipted JT acquisitions.',risk=CapabilityRisk.WRITE,confirmation='none',permissions=('simulation.use',),input_schema=BATCH_REQUEST,output_schema=BATCH_ADMISSION,tags=('experimental',)),request_batch
    yield CapabilitySpec(id='simulation.model_cache.file.fetch.batch.result',version=1,owner='simulation',description='Read the signed preflight and per-file results for one exact cached acquisition batch.',risk=CapabilityRisk.READ,confirmation='none',permissions=('simulation.use',),input_schema=BATCH_RESULT_INPUT,output_schema=BATCH_RESULT,tags=('experimental',)),provider.batch_result
