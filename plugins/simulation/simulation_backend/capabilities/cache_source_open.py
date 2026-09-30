"""Materialize only the valid subset of an owned pinned cache source; never launch TC."""
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextvars import copy_context
from collections import OrderedDict
from contextlib import nullcontext
from datetime import timedelta
import json
import hashlib
from threading import RLock
from time import monotonic
import jsonschema
from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilitySpec, CapabilityRisk
from backend.platform_sdk.artifacts import create_artifact, require_artifact
from ..application.cache_open_evidence import CacheBinding, cache_package_hash, CACHE_OPEN_CONTRACT_HASH
from ..application.cache_source_materialization import select_cached_assembly, materialize_cache_nodes
from ..data.cache_assembly_reader import read_assembly
from ..data.cache_file_receipt_index import list_completed
from ..data.cached_assembly_projection import PLMXML_AUTHORITY
from ..data.cloud_model_cache_repository import CacheError
from ..data.connection import get_simulation_conn, open_simulation_transaction
from ..data.workspace_repository import WorkspaceRepository, WorkspaceRepositoryError
from ..domain.cache_snapshot_package import build_cache_snapshot_package
from .cloud_model_cache_files import CacheFileProvider
from .connector_contracts import obj
from .environment_documents import _output

GID = {'type':'string','pattern':'^[1-9][0-9]*$'}
TEXT = {'type':'string','minLength':1}
HASH = {'type':'string','pattern':'^sha256:[0-9a-f]{64}$'}
IDENTITY = CacheBinding.model_json_schema()
EXCLUDED = {'type':'array','items':obj(dict(node_key=TEXT,name=TEXT,error_code=TEXT))}
FILE = obj(dict(node_key=TEXT,item_revision_uid=TEXT,dataset_uid=TEXT,file_uid=TEXT,file_name=TEXT,
    relation_type={'type':'string','const':'IMAN_Rendering'},operation_id={'type':['string','null']}))
SCOPE_KEY = {'type':'string','minLength':1,'maxLength':191}
INSPECT_INPUT = obj(dict(workspace_gid=GID,document_gid=GID,root_node_key=SCOPE_KEY,cursor={'type':'integer','minimum':0},
    page_size={'type':'integer','minimum':1,'maximum':500}), ['workspace_gid','document_gid'])
OPEN_INPUT = obj(dict(workspace_gid=GID,document_gid=GID,root_node_key=SCOPE_KEY,expected_workspace_row_version={'type':'integer','minimum':1},materialization_hash=HASH),
    ['workspace_gid','document_gid','expected_workspace_row_version','materialization_hash'])
INSPECT_OUTPUT = obj(dict(identity=IDENTITY,materialization_hash=HASH,node_count={'type':'integer','minimum':0},
    file_count={'type':'integer','minimum':0},excluded=EXCLUDED,files={'type':'array','maxItems':500,'items':FILE},
    next_cursor={'type':['integer','null'],'minimum':0}))
NODE_MAP = {'type':'object','patternProperties':{'.+':obj(dict(instance_id=TEXT,parent_node_key={'type':['string','null']}))},'additionalProperties':False}
OPEN_OUTPUT = obj(dict(operation_id=TEXT,package_hash=HASH,node_map=NODE_MAP,excluded=EXCLUDED,identity=IDENTITY))

class CacheSourceOpenProvider:
    open_operation="vismockup.model.open@2"
    open_contract=CACHE_OPEN_CONTRACT_HASH
    def __init__(self,files=None,*,connect=get_simulation_conn,reader=read_assembly,find_bulk=None,
                 create=create_artifact,authorize=require_artifact,list_receipts=list_completed):
        self.files=files or CacheFileProvider()
        self.cache,self.connector=self.files.cache,self.files.connector
        self.connect,self.reader,self.find_bulk,self.create,self.authorize=connect,reader,find_bulk,create,authorize
        self.list_receipts=list_receipts
        self.projections=OrderedDict();self.candidates=OrderedDict();self.lock=RLock()

    @staticmethod
    def validate(payload,context,schema):
        if context.source!='web' or not context.user_gid or not context.team_gid:
            raise CacheError('cache_source_owner_required')
        try:jsonschema.validate(payload,schema)
        except jsonschema.ValidationError as exc:raise CacheError('cache_source_input_invalid') from exc

    def source(self,payload,context,cursor=None):
        with (self.connect() if cursor is None else nullcontext()) as conn, (conn.cursor() if cursor is None else nullcontext(cursor)) as cur:
            cur.execute('SELECT w.row_version,w.status,w.name AS workspace_name,d.artifact_ref_json FROM workmanship_sim_workspaces w '
                'JOIN workmanship_sim_vm_documents d ON d.workspace_gid=w.gid '
                'WHERE w.gid=%s AND w.tenant_gid=%s AND w.owner_gid=%s AND w.removed_at IS NULL '
                "AND d.gid=%s AND d.tenant_gid=%s AND d.owner_gid=%s AND d.source_kind='teamcenter_cache_snapshot' "
                "AND d.document_role IN ('primary','inserted') AND d.removed_at IS NULL" + (' FOR UPDATE' if cursor else ''),
                (payload['workspace_gid'],context.team_gid,context.user_gid,payload['document_gid'],context.team_gid,context.user_gid))
            row=cur.fetchone()
        if not row:raise CacheError('cache_model_document_not_found')
        envelope=row['artifact_ref_json'];envelope=json.loads(envelope) if isinstance(envelope,str) else envelope
        binding=CacheBinding.model_validate(envelope['cache_binding']).model_dump()
        self.cache._read(binding['batch_id'],context)
        pinned=self.cache.repo.query_pinned(binding['batch_id'],context.team_gid,scope='roots',projection='structure',page_size=1,
            expected_generation=binding['generation'],expected_snapshot_hash=binding['snapshot_hash'])
        if pinned['identity']!=binding:raise CacheError('cache_snapshot_mismatch')
        return row,binding

    def selection(self,binding,context,*,fresh=False,root_node_key=None):
        key=cache_package_hash([context.team_gid,context.user_gid,binding,root_node_key])
        with self.lock:
            cached=self.projections.get(key)
            if not fresh and cached and monotonic()-cached[0]<60:return cached[1]
        try:value=select_cached_assembly(self.reader(self.cache,binding,context),root_node_key=root_node_key)
        except ValueError as exc:
            if str(exc)=='cache_scope_node_not_found':raise CacheError(str(exc)) from exc
            raise
        if len(value['files'])>10000:raise CacheError('cache_package_dependency_limit')
        value['materialization_hash']=cache_package_hash(dict(identity=binding,nodes=value['nodes'],excluded=value['excluded'],files=value['files']))
        with self.lock:
            self.projections[key]=(monotonic(),value);self.projections.move_to_end(key)
            while len(self.projections)>2:self.projections.popitem(last=False)
        return value

    def receipts(self,identity,files,context):
        if not files:return []
        finder=self.find_bulk
        if finder is None:
            from ..data.cache_file_receipts_bulk import find_completed_bulk
            finder=find_completed_bulk
        members=[dict(node_key=file['node_key'],item_revision_uid=file['item_revision_uid'],
            file_ref={key:file[key] for key in ('dataset_uid','file_uid','file_name','relation_type')}) for file in files]
        result=finder(identity,members,context,provider=self.files)
        if result['identity']!=identity or len(result['results'])!=len(files):raise CacheError('cache_snapshot_mismatch')
        return result['results']

    def authorize_refs(self,refs,identity,context):
        artifacts=iter(refs.values())
        resource_refs=('simulation://model-cache/'+identity['batch_id'],)
        with ThreadPoolExecutor(max_workers=4,thread_name_prefix='cache-artifact-auth') as workers:
            pending=set()
            def submit_next():
                artifact=next(artifacts,None)
                if artifact is not None:
                    pending.add(workers.submit(copy_context().run,self.authorize,artifact,context,resource_refs=resource_refs))
            try:
                for _ in range(4):submit_next()
                while pending:
                    completed,_=wait(pending,return_when=FIRST_COMPLETED)
                    for future in completed:future.result()
                    pending.difference_update(completed)
                    for _ in completed:submit_next()
            except BaseException:
                for future in pending:future.cancel()
                raise  # Executor exit settles active workers before admission can fail.

    def completed_candidates(self,identity,context):
        key=cache_package_hash([context.team_gid,context.user_gid,identity])
        with self.lock:
            prior=self.candidates.get(key)
            if prior and monotonic()-prior[0]<10:return prior[1]
        members=set();cursor=None
        while True:
            page=self.list_receipts(identity['batch_id'],context,provider=self.files,
                expected_generation=identity['generation'],expected_snapshot_hash=identity['snapshot_hash'],page_size=500,cursor=cursor)
            if page['identity']!=identity:raise CacheError('cache_snapshot_mismatch')
            members.update((r['node_key'],r['item_revision_uid'],r['dataset_uid'],r['file_uid']) for r in page['receipts'])
            cursor=page['next_cursor']
            if cursor is None:break
        with self.lock:
            self.candidates[key]=(monotonic(),members);self.candidates.move_to_end(key)
            while len(self.candidates)>2:self.candidates.popitem(last=False)
        return members

    def inspect(self,payload,context):
        try:
            self.validate(payload,context,INSPECT_INPUT)
            _,identity=self.source(payload,context);selected=self.selection(identity,context,root_node_key=payload.get('root_node_key'))
            start=payload.get('cursor',0);size=payload.get('page_size',100)
            if start>len(selected['files']):raise CacheError('cache_cursor_invalid')
            files=[];candidates=self.completed_candidates(identity,context)
            page=selected['files'][start:start+size]
            present=[file for file in page if (file['node_key'],file['item_revision_uid'],file['dataset_uid'],file['file_uid']) in candidates]
            verified=iter(self.receipts(identity,present,context))
            for file in page:
                member=(file['node_key'],file['item_revision_uid'],file['dataset_uid'],file['file_uid'])
                receipt=next(verified) if member in candidates else None
                files.append({key:file[key] for key in FILE['properties'] if key!='operation_id'}|{'operation_id':receipt['operation_id'] if receipt else None})
            return _output(dict(identity=identity,materialization_hash=selected['materialization_hash'],node_count=len(selected['nodes']),
                file_count=len(selected['files']),excluded=selected['excluded'],files=files,
                next_cursor=start+size if start+size<len(selected['files']) else None),'cache_materialization_inspected',payload['workspace_gid'])
        except (CacheError,ValueError,KeyError,TypeError) as exc:
            raise CapabilityBusinessError(str(exc) if isinstance(exc,CacheError) else 'cache_materialization_invalid',str(exc)) from exc

    @staticmethod
    def request_identity(payload,context):
        key='cache-open:'+str(context.idempotency_key or context.request_id or '')
        if key=='cache-open:' or len(key)>191:raise CacheError('idempotency_key_invalid')
        request=dict(op='cache_source_open',actor_gid=context.user_gid,tenant_gid=context.team_gid,**payload)
        digest=hashlib.sha256(json.dumps(request,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        return key,request,digest

    def runtime(self,context):
        from ..data.connector_repository import _utc
        runtime=self.connector.repository.bound_runtime_for_user(context.user_gid,context.team_gid)
        now=self.connector.clock()
        if (not runtime or runtime['owner_user_gid']!=context.user_gid or runtime['tenant_gid']!=context.team_gid
            or runtime['status']!='active' or runtime['runtime_type']!='electron' or runtime['protocol']!='ai00.connector.execution-plan.v2'
            or not runtime['session_token_hash'] or not now-timedelta(seconds=120)<=_utc(runtime['heartbeat_at'])<=now
            or _utc(runtime['session_expires_at'])<=now):raise CacheError('connector_offline')
        health=runtime['adapter_health_json'];health=json.loads(health) if isinstance(health,str) else health
        if ((health['runtime_generation'],health['runtime_instance_id'])!=(runtime['runtime_generation'],runtime['current_runtime_instance_id'])
            or health['adapter']['adapter_id']!='ai00.vismockup'
            or not any(x['operation_id']==self.open_operation and x['contract_hash']==self.open_contract for x in health['adapter']['operations'])):
            raise CacheError('adapter_contract_mismatch')
        return runtime,now

    def prepare(self,payload,context):
        from .connector_runtime import ConnectorError
        try:return self._prepare(payload,context)
        except (CacheError,ConnectorError,WorkspaceRepositoryError,ValueError,KeyError,TypeError) as exc:
            code=str(exc) if isinstance(exc,(CacheError,ConnectorError,WorkspaceRepositoryError)) else 'cache_materialization_invalid'
            raise CapabilityBusinessError(code,code) from exc

    def _prepare(self,payload,context):
        self.validate(payload,context,OPEN_INPUT)
        row,identity=self.source(payload,context)
        if row['status']=='frozen':raise CacheError('workspace_frozen')
        key,_,digest=self.request_identity(payload,context)
        with self.connect() as conn,conn.cursor() as cursor:
            cursor.execute('SELECT request_hash,response_json FROM workmanship_sim_workspace_idempotency WHERE workspace_gid=%s AND idempotency_key=%s',
                (payload['workspace_gid'],key))
            prior=cursor.fetchone()
        if prior:
            if prior['request_hash']!=digest:raise CacheError('idempotency_conflict')
            return dict(identity=identity,replay=True)
        if row['row_version']!=payload['expected_workspace_row_version']:raise CacheError('version_conflict')
        selected=self.selection(identity,context,fresh=True,root_node_key=payload.get('root_node_key'))
        if selected['materialization_hash']!=payload['materialization_hash']:raise CacheError('cache_materialization_changed')
        if not selected['nodes'] or not selected['files']:raise CacheError('cache_assembly_empty')
        self.runtime(context)
        refs={}
        for file,receipt in zip(selected['files'],self.receipts(identity,selected['files'],context)):
            if not receipt:raise CacheError('cache_package_file_missing')
            artifact=receipt['file']['artifact_ref']
            refs[file['dataset_uid'],file['file_uid']]=artifact
        self.authorize_refs(refs,identity,context)
        nodes=materialize_cache_nodes(selected,refs)
        semantics=dict(status='documented',evidence_ref=PLMXML_AUTHORITY['url'],unit=PLMXML_AUTHORITY['unit'],
            layout='row_major',vector_convention='row_vector',reference_frame='parent',direction='local_to_parent')
        package=build_cache_snapshot_package(identity=identity,nodes=nodes,spatial_semantics=semantics,
            environment=dict(workspace_gid=payload['workspace_gid'],document_gid=payload['document_gid'],name=row['workspace_name']))
        node_map={node['node_key']:dict(instance_id=package.node_map[node['node_key']]['instance_id'],
            parent_node_key=node['parent_node_key']) for node in selected['nodes']}
        if len(json.dumps(dict(node_map=node_map,excluded=selected['excluded']),ensure_ascii=False).encode('utf-8'))>7*1024*1024:
            raise CacheError('cache_package_result_limit')
        return dict(identity=identity,selected=selected,package=package,node_map=node_map)

    def request(self,payload,context):
        from backend.capability_v2.reliability import TransactionalCapabilityOutput
        try:prepared=self.prepare(payload,context)
        except (CacheError,ValueError,KeyError,TypeError) as exc:
            code=str(exc) if isinstance(exc,CacheError) else 'cache_materialization_invalid'
            raise CapabilityBusinessError(code,code) from exc
        transaction=open_simulation_transaction()
        try:
            with transaction.cursor() as cur:value=self.admit(payload,context,cur,prepared=prepared)
            return TransactionalCapabilityOutput(data=value.data,evidence=value.evidence,transaction=transaction)
        except BaseException:
            try:transaction.rollback()
            finally:transaction.close()
            raise

    def admit(self,payload,context,cursor,*,prepared):
        from .connector_runtime import _direct_vismockup_plan_v2,ConnectorError
        try:
            row,identity=self.source(payload,context,cursor)
            if identity!=prepared['identity']:raise CacheError('cache_snapshot_mismatch')
            if row['status']=='frozen':raise CacheError('workspace_frozen')
            key,request,_=self.request_identity(payload,context)
            repository=WorkspaceRepository()
            request_hash,replay=repository._idempotency_begin(cursor,workspace_gid=payload['workspace_gid'],idempotency_key=key,request=request)
            if replay is not None:return _output(replay,'cache_open_replayed',payload['workspace_gid'])
            if prepared.get('replay'):raise CacheError('cache_open_replay_conflict')
            if row['row_version']!=payload['expected_workspace_row_version']:raise CacheError('version_conflict')
            selected,package,node_map=prepared['selected'],prepared['package'],prepared['node_map']
            runtime,now=self.runtime(context)
            # Check deterministic admission before creating another top-level artifact.
            draft=_direct_vismockup_plan_v2(action='cache_open',connector_id=runtime['device_id'],payload={},context=context,now=now)
            cursor.execute('SELECT plan_json FROM workmanship_sim_connector_runtime_plans WHERE plan_id=%s AND actor_gid=%s AND tenant_gid=%s',
                (draft['plan_id'],context.user_gid,context.team_gid))
            prior=cursor.fetchone()
            if prior:
                saved=prior['plan_json'];saved=json.loads(saved) if isinstance(saved,str) else saved
                packet=saved['steps'][0]['payload']
                if packet['cache_binding']!=identity or packet['package_dependencies']!=list(package.dependencies) or packet['artifact_ref']['sha256']!=package.content_hash[7:]:
                    raise CacheError('cache_open_replay_conflict')
            else:
                artifact=self.create(package.plmxml,'application/vnd.siemens.plmxml+xml',context,maximum=64*1024*1024)
                packet=dict(artifact_ref=artifact,package_dependencies=list(package.dependencies),cache_binding=identity)
                packet['package_hash']=cache_package_hash(packet)
                runtime,now=self.runtime(context)
                draft=_direct_vismockup_plan_v2(action='cache_open',connector_id=runtime['device_id'],payload=packet,context=context,now=now)
                self.connector.queue_v2(draft,context,runtime_row=runtime)
            result=dict(operation_id=draft['plan_id'],package_hash=packet['package_hash'],node_map=node_map,excluded=selected['excluded'],identity=identity)
            repository._idempotency_finish(cursor,workspace_gid=payload['workspace_gid'],idempotency_key=key,request_hash=request_hash,response=result)
            return _output(result,'cache_open_queued',payload['workspace_gid'])
        except (CacheError,ConnectorError,WorkspaceRepositoryError,ValueError,KeyError,TypeError) as exc:
            code=str(exc) if isinstance(exc,(CacheError,ConnectorError,WorkspaceRepositoryError)) else 'cache_materialization_invalid'
            raise CapabilityBusinessError(code,code) from exc


def specs(provider=None):
    from backend.capability_v2.reliability import transactional_provider
    from .cache_tc_open import TcCacheSourceOpenProvider
    provider=provider or TcCacheSourceOpenProvider()
    @transactional_provider
    def request(payload,context):return provider.request(payload,context)
    yield CapabilitySpec(id='simulation.environment.cache_source.materialization.inspect',version=1,owner='simulation',
        description='Inspect the selected subtree (or explicit whole document) and prepared TC file references of one owned fixed cache source.',
        risk=CapabilityRisk.READ,confirmation='none',permissions=('simulation.use',),input_schema=INSPECT_INPUT,output_schema=INSPECT_OUTPUT,tags=('experimental',)),provider.inspect
    yield CapabilitySpec(id='simulation.environment.cache_source.open.request',version=1,owner='simulation',
        description='Use shared prepared assembly metadata and client-local TC/FMS downloads for the selected subtree (or explicit whole document) of an owned fixed cache and queue its exact native open.',
        risk=CapabilityRisk.WRITE,confirmation='none',permissions=('simulation.use',),input_schema=OPEN_INPUT,output_schema=OPEN_OUTPUT,tags=('experimental',)),request
