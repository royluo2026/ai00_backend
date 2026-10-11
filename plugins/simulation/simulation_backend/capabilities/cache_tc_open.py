"""Open prepared shared TC metadata using client-local JT files, never OIS JT."""
import json
from .cache_source_open import (CacheSourceOpenProvider,INSPECT_INPUT,OPEN_INPUT,FILE,CacheError,
    WorkspaceRepository,WorkspaceRepositoryError,CapabilityBusinessError,_output,_log_materialization_error)
from ..application.cache_preparation import scoped_preparation
from ..application.cache_open_evidence import cache_package_hash
from ..application.cache_tc_open_contract import (TcCacheOpenPayload,TC_OPEN_CONTRACT_HASH,
    MAX_ASSEMBLY_XML_BYTES,MAX_CACHE_OPEN_PACKET_BYTES)
from ..data.cache_assembly_preparation import load_preparation

class TcCacheSourceOpenProvider(CacheSourceOpenProvider):
    open_operation='vismockup.model.open@3'
    open_contract=TC_OPEN_CONTRACT_HASH
    def __init__(self,*args,load=load_preparation,**kwargs):
        super().__init__(*args,**kwargs);self.load_prepared=load

    def selected(self,payload,context,environment=None):
        row,identity=self.source(payload,context)
        prepared=self.load_prepared(self.cache,identity,context)
        if prepared['identity']!=identity:raise CacheError('cache_snapshot_mismatch')
        scope=scoped_preparation(prepared,payload.get('root_node_key'),environment,verified=self.load_prepared is load_preparation)
        if len(scope['assembly_xml'].encode('utf-8'))>MAX_ASSEMBLY_XML_BYTES:
            raise CacheError('cache_package_result_limit')
        materialization_hash=cache_package_hash(dict(identity=identity,preparation_hash=prepared['preparation_hash'],root_node_key=payload.get('root_node_key')))
        return row,identity,prepared,scope,materialization_hash

    def inspect(self,payload,context):
        try:
            self.validate(payload,context,INSPECT_INPUT)
            row,identity,prepared,scope,fingerprint=self.selected(payload,context)
            start=payload.get('cursor',0);size=payload.get('page_size',100)
            files=[]
            representatives={}
            for node in scope['nodes']:
                for f in node['geometry_refs']:representatives.setdefault((f['dataset_uid'],f['file_uid']),node)
            for dependency in scope['dependencies']:
                ref=dependency['file_ref']
                node=representatives[ref['dataset_uid'],ref['file_uid']]
                files.append(dict(node_key=node['node_key'],item_revision_uid=node['item_revision_uid'],
                    **{k:ref[k] for k in ('dataset_uid','file_uid','file_name','relation_type')},operation_id=None))
            if start>len(files):raise CacheError('cache_cursor_invalid')
            return _output(dict(identity=identity,materialization_hash=fingerprint,node_count=len(scope['nodes']),file_count=len(files),
                excluded=scope['excluded'],files=files[start:start+size],next_cursor=start+size if start+size<len(files) else None),'cache_materialization_inspected',payload['workspace_gid'])
        except (ValueError,KeyError,TypeError) as exc:
            raise CapabilityBusinessError(str(exc) if isinstance(exc,ValueError) else 'cache_materialization_invalid',str(exc)) from exc

    def _prepare(self,payload,context):
        self.validate(payload,context,OPEN_INPUT)
        row,identity=self.source(payload,context)
        if row['status']=='frozen':raise CacheError('workspace_frozen')
        key,_,request_hash=self.request_identity(payload,context)
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute('SELECT request_hash,response_json FROM workmanship_sim_workspace_idempotency WHERE workspace_gid=%s AND idempotency_key=%s',(payload['workspace_gid'],key))
            prior=cur.fetchone()
        if prior:
            if prior['request_hash']!=request_hash:raise CacheError('idempotency_conflict')
            return dict(identity=identity,replay=True)
        if row['row_version']!=payload['expected_workspace_row_version']:raise CacheError('version_conflict')
        environment=dict(workspace_gid=payload['workspace_gid'],document_gid=payload['document_gid'],name=row['workspace_name'])
        _,_,prepared,scope,fingerprint=self.selected(payload,context,environment)
        if fingerprint!=payload['materialization_hash']:raise CacheError('cache_materialization_changed')
        if not scope['dependencies']:raise CacheError('cache_assembly_empty')
        batch=self.cache._read(identity['batch_id'],context)
        dependencies=[]
        representatives={}
        for node in scope['nodes']:
            for f in node['geometry_refs']:representatives.setdefault((f['dataset_uid'],f['file_uid']),node)
        for dependency in scope['dependencies']:
            ref=dependency['file_ref'];node=representatives[ref['dataset_uid'],ref['file_uid']]
            dependencies.append({**dependency,'node_key':node['node_key'],'item_revision_uid':node['item_revision_uid']})
        packet=dict(cache_binding=identity,preparation_hash=prepared['preparation_hash'],source_selector=batch['source_selector'],
            assembly_xml=scope['assembly_xml'],tc_dependencies=dependencies)
        packet['package_hash']=cache_package_hash(packet)
        packet=TcCacheOpenPayload.model_validate(packet).model_dump()
        if len(json.dumps(packet,ensure_ascii=False).encode('utf-8'))>MAX_CACHE_OPEN_PACKET_BYTES:raise CacheError('cache_package_result_limit')
        self.runtime(context)
        return dict(identity=identity,packet=packet,scope=scope)

    def admit(self,payload,context,cursor,*,prepared):
        from .connector_runtime import _direct_vismockup_plan_v2,ConnectorError
        try:
            row,identity=self.source(payload,context,cursor)
            if identity!=prepared['identity']:raise CacheError('cache_snapshot_mismatch')
            if row['status']=='frozen':raise CacheError('workspace_frozen')
            key,request,_=self.request_identity(payload,context);repository=WorkspaceRepository()
            request_hash,replay=repository._idempotency_begin(cursor,workspace_gid=payload['workspace_gid'],idempotency_key=key,request=request)
            if replay is not None:return _output(replay,'cache_open_replayed',payload['workspace_gid'])
            if prepared.get('replay'):raise CacheError('cache_open_replay_conflict')
            if row['row_version']!=payload['expected_workspace_row_version']:raise CacheError('version_conflict')
            runtime,now=self.runtime(context)
            draft=_direct_vismockup_plan_v2(action='cache_tc_open',connector_id=runtime['device_id'],payload=prepared['packet'],context=context,now=now)
            self.connector.queue_v2(draft,context,runtime_row=runtime)
            scope=prepared['scope']
            result=dict(operation_id=draft['plan_id'],package_hash=prepared['packet']['package_hash'],node_map=scope['node_map'],excluded=scope['excluded'],identity=identity)
            repository._idempotency_finish(cursor,workspace_gid=payload['workspace_gid'],idempotency_key=key,request_hash=request_hash,response=result)
            return _output(result,'cache_open_queued',payload['workspace_gid'])
        except (CacheError,ConnectorError,WorkspaceRepositoryError,ValueError,KeyError,TypeError) as exc:
            code=str(exc) if isinstance(exc,(CacheError,ConnectorError,WorkspaceRepositoryError)) else 'cache_materialization_invalid'
            if code=='cache_materialization_invalid':_log_materialization_error(exc)
            raise CapabilityBusinessError(code,code) from exc
