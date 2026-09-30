"""Shared immutable assembly metadata. No transport, JT bytes or personal state."""
from copy import deepcopy
from .cache_source_materialization import select_cached_assembly, materialize_cache_nodes
from ..data.cloud_model_cache_repository import digest
from ..data.cached_assembly_projection import PLMXML_AUTHORITY
from ..domain.cache_snapshot_package import build_cache_snapshot_package

SEMANTICS=dict(status='documented',evidence_ref=PLMXML_AUTHORITY['url'],unit=PLMXML_AUTHORITY['unit'],
    layout='row_major',vector_convention='row_vector',reference_frame='parent',direction='local_to_parent')

def _scope(projection, endpoint_id, root_node_key, environment):
    selected=select_cached_assembly(projection,root_node_key=root_node_key)
    if len(selected['files'])>10000:raise ValueError('cache_package_dependency_limit')
    refs={}
    for file in selected['files']:
        ref={k:file[k] for k in ('dataset_uid','file_uid','file_name','relation_type')}
        ref['endpoint_id']=endpoint_id
        ref['dependency_key']=digest(ref)
        refs[file['dataset_uid'],file['file_uid']]=ref
    nodes=materialize_cache_nodes(selected,refs,reference_field='tc_file_refs')
    package=build_cache_snapshot_package(identity=projection['identity'],nodes=nodes,spatial_semantics=SEMANTICS,
        environment=environment,tc_dependencies=True)
    return dict(assembly_xml=package.plmxml.decode('utf8'),dependencies=list(package.dependencies),
        node_map={n['node_key']:dict(instance_id=package.node_map[n['node_key']]['instance_id'],parent_node_key=n['parent_node_key']) for n in selected['nodes']},
        excluded=selected['excluded'],files=list(refs.values()),nodes=selected['nodes'])

def prepare_cached_assembly(projection, *, endpoint_id):
    if not isinstance(endpoint_id,str) or not endpoint_id:raise ValueError('cache_endpoint_invalid')
    # Keep only verified assembly inputs; full TC property bags do not belong here.
    projection=deepcopy({k:projection[k] for k in ('identity','nodes','spatial_authority')})
    scope=_scope(projection,endpoint_id,None,None)
    own={n['node_key']:set() for n in scope['nodes']}
    refs={(f['dataset_uid'],f['file_uid']):f['dependency_key'] for f in scope['files']}
    children={k:[] for k in own};roots=[]
    for n in scope['nodes']:
        own[n['node_key']].update(refs[f['dataset_uid'],f['file_uid']] for f in n['geometry_refs'])
        if n['parent_node_key'] is None:roots.append(n['node_key'])
        else:children[n['parent_node_key']].append(n['node_key'])
    order=[];pending=roots[:]
    while pending:
        key=pending.pop();order.append(key);pending.extend(children[key])
    for key in reversed(order):
        for child in children[key]:own[key].update(own[child])
    value=dict(identity=projection['identity'],preparation_version=1,endpoint_id=endpoint_id,projection=projection,
        status='partial' if scope['excluded'] else 'ready',assembly_xml=scope['assembly_xml'],files=scope['files'],
        node_dependencies={k:sorted(v) for k,v in own.items()},excluded=scope['excluded'])
    return {**value,'preparation_hash':'sha256:'+digest(value)}

def validate_preparation(prepared):
    if prepared.get('preparation_version')!=1 or prepared.get('preparation_hash')!='sha256:'+digest({k:v for k,v in prepared.items() if k!='preparation_hash'}):
        raise ValueError('cache_preparation_hash_mismatch')

def scoped_preparation(prepared, root_node_key=None, environment=None, *, verified=False):
    if not verified:validate_preparation(prepared)
    return _scope(prepared['projection'],prepared['endpoint_id'],root_node_key,environment)
