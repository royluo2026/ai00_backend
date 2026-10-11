"""Project-shared TC cache capabilities; all dispatch remains Simulation-owned."""
from backend.capability_v2.provider_contracts import CapabilitySpec, CapabilityRisk, CapabilityOutput, CapabilityBusinessError, EvidenceRef
from backend.platform_sdk.project_access import can_manage_project, list_user_project_memberships
from backend.platform_sdk.access import team_in_access_scope
from ..data.cloud_model_cache_repository import CloudModelCacheRepository, CacheError, canonical, digest
from .connector_contracts import TC_VISUALIZATION_SOURCE_SELECTOR, TC_CHILDREN_INPUT, TC_NODE_PROPERTIES_INPUT, TC_CACHE_INPUT, TC_CACHE_OUTPUT, TC_CACHE_V2_INPUT, TC_CACHE_V2_OUTPUT, obj
from .connector_runtime import connector_control_plane, _direct_vismockup_plan_v2, ConnectorError, DIRECT_VISMOCKUP_OPERATIONS
from jsonschema import ValidationError
from contextlib import contextmanager
from backend.capability_v2.reliability import TransactionalCapabilityOutput,transactional_provider

PREFIX='simulation.model_cache.'
WORKER_ID='simulation.model_cache.worker'
TEXT={'type':'string','maxLength':512}
BID={'type':'string','pattern':'^[a-f0-9]{32}$'}
GID={'type':'string','pattern':'^[1-9][0-9]*$'}
DATA_STAGES=('Pre-TG0','TG0','TG1','PreTG2','TG2','EP1','EP2','PPV','PP','P','SOP')
BATCH=obj({
    'batch_id':BID,'project_gid':GID,'project_name':TEXT,'phase':TEXT,'display_name':TEXT,
    'source_hash':{'type':'string'},'source_selector':TC_VISUALIZATION_SOURCE_SELECTOR,
    'status':{'type':'string','enum':['queued','running','paused','waiting_connector','waiting_auth','needs_refresh','failed','completed']},
    'preparation_status':{'type':'string','enum':['not_prepared','queued','ready','partial','failed']},
    'preparation_error':{'type':['string','null']},
    'created_at':TEXT,'updated_at':TEXT,'completed_at':{'type':['string','null']},
    'row_version':{'type':'integer'},'node_count':{'type':'integer'},'error_code':{'type':['string','null']},'trigger_kind':{'const':'manual','type':'string'},
},('batch_id','project_gid','project_name','phase','display_name','source_hash','source_selector','status','created_at','updated_at','completed_at','row_version','node_count','error_code','trigger_kind'))
FILTER=obj({'field':TEXT,'op':{'type':'string','enum':['eq','ne','contains','exists','empty','not_empty','gt','gte','lt','lte']},'value_json':{'type':'string','maxLength':4096}},('field','op','value_json'))
QUERY=obj({'batch_id':BID,'search':{'type':'string','maxLength':512},'filters':{'type':'array','maxItems':20,'items':FILTER},'mode':{'type':'string','enum':['and','or']},'cursor':{'type':'integer','minimum':0},'page_size':{'type':'integer','minimum':1,'maximum':500}},('batch_id','search','filters','mode','cursor','page_size'))
QUERY_RESULT=obj({'batch':BATCH,'rows':{'type':'array','maxItems':500,'items':obj({'node_key':{'type':'string'},'data_json':{'type':'string','maxLength':8388608}},('node_key','data_json'))},'fields':{'type':'array','maxItems':10000,'items':TEXT},'total':{'type':'integer'},'next_cursor':{'type':['integer','null']}},('batch','rows','fields','total','next_cursor'))


def admin(context): return 'super_admin' in context.active_roles


def bulk_supported(runtime):
    """Use only the bound runtime's current, exact contract advertisement."""
    import json
    if not runtime:return False
    raw=runtime.get('adapter_health_json')
    if raw is None:return False
    try:health=json.loads(raw) if isinstance(raw,str) else raw
    except (TypeError,ValueError) as exc:raise ConnectorError('adapter_health_unavailable') from exc
    if not isinstance(health,dict) or (health.get('runtime_generation'),health.get('runtime_instance_id'))!=(runtime.get('runtime_generation'),runtime.get('current_runtime_instance_id')):return False
    adapter=health.get('adapter')
    if not isinstance(adapter,dict) or not isinstance(adapter.get('operations'),list) or len(adapter['operations'])>256:raise ConnectorError('adapter_health_unavailable')
    operations=adapter['operations']
    seen=set();supported=False;wanted,expected=DIRECT_VISMOCKUP_OPERATIONS['tc_cache_v2']
    for item in operations:
        if not isinstance(item,dict) or not isinstance(item.get('operation_id'),str) or item['operation_id'] in seen:raise ConnectorError('adapter_health_unavailable')
        seen.add(item.get('operation_id'))
        if item.get('operation_id')==wanted:
            if item.get('contract_hash')!=expected:raise ConnectorError('contract_hash_mismatch')
            supported=True
    return supported


class CloudModelCacheProvider:
    def __init__(self,repository=None,control_plane=None,project_reader=None):
        self.repo=repository or CloudModelCacheRepository(); self.connector=control_plane or connector_control_plane
        self.project_reader=project_reader

    def transactional_handler(self,name):
        @contextmanager
        def participant():
            from ..data.connection import open_simulation_transaction
            transaction=open_simulation_transaction()
            try:
                bound=CloudModelCacheProvider(self.repo.in_transaction(transaction),self.connector,self.project_reader)
                yield bound,transaction
            except BaseException:
                try:transaction.rollback()
                finally:transaction.close()
                raise
        def output(result,transaction):
            return TransactionalCapabilityOutput(data=result.data,transaction=transaction,evidence=result.evidence)
        if name=='create':
            @transactional_provider
            async def handler(payload,context):
                with participant() as (bound,transaction):
                    return output(await bound.create(payload,context),transaction)
        else:
            @transactional_provider
            def handler(payload,context):
                with participant() as (bound,transaction):
                    if name=='advance':
                        bound._admin(context)
                        # Lock before any ordinary batch/task read, so a worker
                        # waiting under REPEATABLE READ cannot retain an old task snapshot.
                        try:
                            with transaction.cursor() as cur:
                                bound.repo._batch(cur,payload['batch_id'],context.team_gid,True)
                        except CacheError as exc:raise CapabilityBusinessError(str(exc),str(exc)) from exc
                    return output(getattr(bound,name)(payload,context),transaction)
        return handler

    @staticmethod
    def _admin(context):
        if not context.user_gid or not context.team_gid or not admin(context):
            raise CapabilityBusinessError('cache_trigger_forbidden','cache_trigger_forbidden')

    def _read(self,batch_id,context):
        try: batch=self.repo.get(batch_id,context.team_gid)
        except CacheError as exc: raise CapabilityBusinessError(str(exc),str(exc)) from exc
        if not admin(context) and not can_manage_project(context.user_gid,batch['project_gid']):
            raise CapabilityBusinessError('cache_project_forbidden','cache_project_forbidden')
        return batch

    @staticmethod
    def output(value):
        return CapabilityOutput(data=value,evidence=(EvidenceRef(kind='simulation.model_cache',reference='simulation://model-cache/'+str(value.get('batch_id') or value.get('batch',{}).get('batch_id') or value.get('identity',{}).get('batch_id') or 'index'),digest='sha256:'+digest(value)),))

    async def create(self,payload,context):
        self._admin(context)
        if payload.get('trigger_kind','manual')!='manual': raise CapabilityBusinessError('cache_trigger_disabled','cache_trigger_disabled')
        if self.project_reader:
            project=await self.project_reader(payload['project_gid'],context)
        else:
            from backend.domain_ports.simulation_runtime import GovernedSimulationRuntimeClient
            from backend.capability_v2.gateway import get_default_gateway
            from backend.capability_v2.domain_client import DomainInvocation
            project=await GovernedSimulationRuntimeClient(get_default_gateway())._invoke(DomainInvocation('project.project.read.atomic.projects_get',2,{'arguments':{'gid':payload['project_gid']}}),context)
        for _ in range(4):
            if isinstance(project,dict) and 'gid' not in project and isinstance(project.get('data'),dict): project=project['data']
        if not isinstance(project,dict) or str(project.get('gid'))!=payload['project_gid'] or project.get('is_deleted') or not team_in_access_scope(context.user_gid,context.team_gid,str(project.get('team_id') or '')):
            raise CapabilityBusinessError('cache_project_forbidden','The project must exist in the current tenant.')
        try:
            return self.output(self.repo.create(**{**payload,'project_name':str(project.get('name') or payload['project_name'])},tenant_gid=context.team_gid,actor_gid=context.user_gid,request_key=str(getattr(context,'idempotency_key','') or context.request_id)))
        except CacheError as exc: raise CapabilityBusinessError(str(exc),str(exc)) from exc

    def list(self,payload,context):
        projects=None if admin(context) else {str(row['project_gid']) for row in list_user_project_memberships(context.user_gid)}
        cursor=payload.get('cursor',0);size=payload.get('page_size',500)
        rows=self.repo.list(context.team_gid,projects,limit=size+1,cursor=cursor)
        return self.output({'batches':rows[:size],'next_cursor':cursor+size if len(rows)>size else None,'can_trigger':admin(context),'project_manager_enabled':False,'scheduled_enabled':False})

    def query(self,payload,context):
        self._read(payload['batch_id'],context)
        try: return self.output(self.repo.query(tenant_gid=context.team_gid,**payload))
        except (CacheError,ValueError) as exc: raise CapabilityBusinessError('cache_filter_invalid' if not isinstance(exc,CacheError) else str(exc),str(exc)) from exc

    def query_pinned(self,payload,context):
        self._read(payload['batch_id'],context)
        try:return self.output(self.repo.query_pinned(tenant_gid=context.team_gid,**payload))
        except (CacheError,ValueError) as exc:raise CapabilityBusinessError('cache_filter_invalid' if not isinstance(exc,CacheError) else str(exc),str(exc)) from exc

    def control(self,payload,context):
        self._admin(context); self._read(payload['batch_id'],context)
        try: return self.output(self.repo.control(payload['batch_id'],context.team_gid,payload['action'],payload['expected_version']))
        except CacheError as exc: raise CapabilityBusinessError(str(exc),str(exc)) from exc

    def advance(self,payload,context):
        self._admin(context)
        batch_id=payload['batch_id']; self._read(batch_id,context)
        with self.repo.connect() as conn, conn.cursor() as cur:
            batch=self.repo._batch(cur,batch_id,context.team_gid)
        if batch['actor_gid']!=context.user_gid: raise CapabilityBusinessError('cache_actor_mismatch','cache_actor_mismatch')
        if batch['status']=='completed':
            from ..data.cache_assembly_preparation import prepare_batch
            prepare_batch(self,batch_id,context)
            return self.output(self.repo.get(batch_id,context.team_gid))
        task=None
        try:
            runtime=self.connector.repository.bound_runtime_for_user(context.user_gid,context.team_gid)
            bulk=bulk_supported(runtime)
            def queue(batch,task):
                import json
                from jsonschema import validate
                if not runtime or runtime['runtime_type']!='electron': raise ConnectorError('runtime_v2_required')
                if batch['connector_device_id'] and batch['connector_device_id']!=runtime['device_id']: raise CacheError('cache_device_changed')
                if task['kind']=='snapshot':
                    if not bulk:raise ConnectorError('runtime_v2_required')
                    cache_payload={key:task['payload'][key] for key in ('cursor','page_size','generation')}
                    cache_payload.update(batch_id=batch_id,source_selector=json.loads(batch['selector_json']),expected_principal_hash=batch['principal_hash'])
                    validate(cache_payload,TC_CACHE_V2_INPUT);action='tc_cache_v2'
                else:
                    step_payload={**task['payload'],'source_selector':json.loads(batch['selector_json'])}
                    step_payload.pop('expected_child_count',None)
                    if task['kind']=='properties': step_payload.pop('node_key')
                    validate(step_payload,TC_CHILDREN_INPUT if task['kind']=='children' else TC_NODE_PROPERTIES_INPUT)
                    cache_payload={'kind':task['kind'],'read_payload_json':canonical(step_payload),'expected_principal_hash':batch['principal_hash']};action='tc_cache'
                ctx=context.model_copy(update={'idempotency_key':f"cache:{batch_id}:{task['task_key']}:{task['attempt']}"})
                plan=_direct_vismockup_plan_v2(action=action,connector_id=runtime['device_id'],payload=cache_payload,context=ctx,now=self.connector.clock(),capability_id=PREFIX+'advance')
                # A prior deterministic plan may already exist after a crash. Read
                # before queueing, preserving its exact pinned runtime and outcome.
                existing=self.connector.repository.get_plan_result(plan['plan_id'],context.user_gid,context.team_gid)
                return {'device_id':runtime['device_id'],'operation_id':plan['plan_id'] if existing else self.connector.queue_v2(plan,ctx,runtime_row=runtime).operation_id}
            task=self.repo.dispatch(batch_id,context.team_gid,queue,snapshot=bulk)
            if task:
                command=self.connector.repository.get_plan_result(task['operation_id'],context.user_gid,context.team_gid)
                if command and command['status']=='completed':
                    steps=(command.get('outcome') or {}).get('steps') or []
                    if not steps or not isinstance(steps[-1].get('result'),dict): raise CacheError('cache_page_invalid')
                    envelope=steps[-1]['result']
                    from jsonschema import validate
                    import json
                    validate(envelope,TC_CACHE_V2_OUTPUT if task['kind']=='snapshot' else TC_CACHE_OUTPUT)
                    result=json.loads(envelope['result_json'])
                    apply=self.repo.apply_snapshot_result if task['kind']=='snapshot' else self.repo.apply_result
                    apply(batch_id,context.team_gid,task,result,envelope['principal_hash'])
                elif command and command['status'] in ('failed','expired','cancelled','outcome_unknown','manual_review_required'):
                    code=((command.get('outcome') or {}).get('steps') or [{}])[-1].get('error_code') or command['status']
                    interrupted=getattr(self.connector.repository,'cache_read_interrupted_before_lease',None)
                    if command['status']=='failed' and command.get('outcome') is None and interrupted and interrupted(task['operation_id'],context.user_gid,context.team_gid):code='runtime_session_stale'
                    self.repo.failure(batch_id,context.team_gid,code,task)
        except ValidationError:
            self.repo.failure(batch_id,context.team_gid,'cache_page_invalid',task)
        except (CacheError,ConnectorError,ValueError) as exc:
            self.repo.failure(batch_id,context.team_gid,str(exc),task)
        return self.output(self.repo.get(batch_id,context.team_gid))


def specs(provider=None):
    provider=provider or CloudModelCacheProvider()
    from .cloud_model_cache_pinned import contracts
    pinned_input,pinned_output=contracts(BATCH)
    yield CapabilitySpec(id=PREFIX+'query',version=2,owner='simulation',description='Read the selected completed project snapshot by fixed batch identity, returning indexed roots, children or node properties without switching to live TC.',risk=CapabilityRisk.READ,confirmation='none',permissions=('simulation.use',),input_schema=pinned_input,output_schema=pinned_output,tags=('experimental',)),provider.query_pinned
    def local_only(payload,context): raise CapabilityBusinessError('local_runtime_required','local_runtime_required')
    yield CapabilitySpec(id='simulation.teamcenter.model_cache.read',version=1,owner='simulation',description='Read a principal-pinned cache page through existing TC children traversal or full raw property projection; preserve original field read states.',execution='local',risk=CapabilityRisk.READ,confirmation='none',permissions=('simulation.use',),input_schema=TC_CACHE_INPUT,output_schema=TC_CACHE_OUTPUT,tags=('experimental',)),local_only
    yield CapabilitySpec(id='simulation.teamcenter.model_cache.read',version=2,owner='simulation',description='Read a bounded complete occurrence page from a resumable project snapshot, preserving exact BOM parent edges, TC fields and JT file references.',execution='local',risk=CapabilityRisk.READ,confirmation='none',permissions=('simulation.use',),input_schema=TC_CACHE_V2_INPUT,output_schema=TC_CACHE_V2_OUTPUT,tags=('experimental',)),local_only
    create=obj({'project_gid':GID,'project_name':TEXT,'phase':{'type':'string','enum':list(DATA_STAGES)},'source_selector':TC_VISUALIZATION_SOURCE_SELECTOR,'trigger_kind':{'type':'string','enum':['manual','scheduled']}},('project_gid','project_name','phase','source_selector','trigger_kind'))
    listing=obj({'batches':{'type':'array','maxItems':500,'items':BATCH},'next_cursor':{'type':['integer','null']},'can_trigger':{'type':'boolean'},'project_manager_enabled':{'type':'boolean'},'scheduled_enabled':{'type':'boolean'}},('batches','next_cursor','can_trigger','project_manager_enabled','scheduled_enabled'))
    for name,input_schema,output_schema,risk in [
        ('create',create,BATCH,CapabilityRisk.WRITE),('list',obj({'cursor':{'type':'integer','minimum':0},'page_size':{'type':'integer','minimum':1,'maximum':500}},()),listing,CapabilityRisk.READ),
        ('query',QUERY,QUERY_RESULT,CapabilityRisk.READ),
        ('control',obj({'batch_id':BID,'action':{'type':'string','enum':['pause','resume','prepare']},'expected_version':{'type':'integer','minimum':1}},('batch_id','action','expected_version')),BATCH,CapabilityRisk.WRITE),
        ('advance',obj({'batch_id':BID},('batch_id',)),BATCH,CapabilityRisk.WRITE),
    ]:
        yield CapabilitySpec(id=PREFIX+name,version=1,owner='simulation',description={'create':'Create an independent project cache batch for one exact Teamcenter selector.','list':'List readable project cache batches newest first and current trigger policy.','query':'Search and filter every persisted TC field across a whole batch with bounded paging.','control':'Pause or resume a project cache batch with optimistic concurrency.','advance':'Advance one durable TC cache work item through signed read-only Connector contracts.'}[name],risk=risk,confirmation='none',permissions=('simulation.use',),input_schema=input_schema,output_schema=output_schema,tags=('experimental',)),provider.transactional_handler(name) if risk==CapabilityRisk.WRITE else getattr(provider,name)
