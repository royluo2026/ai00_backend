"""Bounded organization projections; incomplete graphs are never save payloads."""
from copy import deepcopy
from contextlib import contextmanager
from .models import BusinessNode, GraphDraft
from .repository import _require_graph_scope, _decoded, ResourceNotAccessible, RevisionConflict


def read_slice(repo, version_gid, *, tenant_gid, actor_gid, projection, view_gid=None, node_gid=None, expected_revision=None):
    _require_graph_scope(tenant_gid, None, True)
    if projection not in ('directory','view','node','full'):
        raise ValueError('unknown projection')
    with repo._connection_factory() as conn, conn.cursor() as cur:
        cur.execute("""SELECT v.mode,v.revision FROM workmanship_agent_orch_versions v
          JOIN workmanship_agent_orch_panoramas p ON p.gid=v.panorama_gid
          WHERE v.gid=%s AND v.tenant_gid=%s AND v.project_gid IS NULL
          AND p.tenant_gid=%s AND p.project_gid IS NULL AND p.scope_kind='organization'""",(version_gid,tenant_gid,tenant_gid))
        version=cur.fetchone()
        if not version: raise ResourceNotAccessible('organization version not accessible')
        revision=int(version['revision'])
        if expected_revision is not None and revision!=expected_revision: raise RevisionConflict('workspace revision changed; refresh required')
        @contextmanager
        def snapshot():
            yield conn
        reader=type(repo)(snapshot)
        if projection=='full':
            # Same read transaction snapshot; save still fences the exact revision.
            graph=reader.get_graph(version_gid,actor_gid=actor_gid,tenant_gid=tenant_gid,project_gid=None,organization=True,expected_revision=revision).model_dump(mode='json')
            return {'graph':graph,'complete':True,'revision':revision,'loaded_view_gids':[v['gid'] for v in (graph.get('workspace') or {}).get('views',[])],'loaded_node_gids':[n['gid'] for n in graph['nodes']]}
        cur.execute('SELECT x_items_json,y_items_json FROM workmanship_agent_orch_axis_views WHERE version_gid=%s AND tenant_gid=%s AND project_gid<=>%s ORDER BY created_at LIMIT 1',(version_gid,tenant_gid,None))
        axis=cur.fetchone() or {}
        cur.execute('SELECT definition_json FROM workmanship_agent_orch_workspaces WHERE version_gid=%s AND tenant_gid=%s AND project_gid<=>%s',(version_gid,tenant_gid,None))
        extension=_decoded((cur.fetchone() or {}).get('definition_json'),{})
        workspace=extension.get('workspace')
        if not workspace:
            # Old empty versions need no child-table sweep. Nonempty legacy
            # versions keep their compatible complete read for migration.
            cur.execute('SELECT gid FROM workmanship_agent_orch_business_nodes WHERE version_gid=%s AND tenant_gid=%s AND project_gid<=>%s LIMIT 1',(version_gid,tenant_gid,None))
            no_nodes=cur.fetchone() is None
            cur.execute('SELECT gid FROM workmanship_agent_orch_items WHERE version_gid=%s AND tenant_gid=%s AND project_gid<=>%s LIMIT 1',(version_gid,tenant_gid,None))
            if no_nodes and cur.fetchone() is None:
                graph=GraphDraft(mode=version.get('mode') or 'fixed',axis={'x_items':_decoded(axis.get('x_items_json'),['阶段']),'y_items':_decoded(axis.get('y_items_json'),['职责'])},nodes=[],edges=[]).model_dump(mode='json')
                return {'graph':graph,'complete':True,'revision':revision,'loaded_view_gids':[],'loaded_node_gids':[]}
            # Legacy versions need their original complete graph to infer hierarchy.
            graph=reader.get_graph(version_gid,actor_gid=actor_gid,tenant_gid=tenant_gid,project_gid=None,organization=True,expected_revision=revision).model_dump(mode='json')
            return {'graph':graph,'complete':True,'revision':revision,'loaded_view_gids':[],'loaded_node_gids':[n['gid'] for n in graph['nodes']]}
        graph={'mode':version.get('mode') or 'fixed','axis':{'x_items':_decoded(axis.get('x_items_json'),['阶段']),'y_items':_decoded(axis.get('y_items_json'),['职责'])},'nodes':[],'edges':[],'items':[],'item_edges':[],'capability_bindings':[],'context_bindings':[],'workspace':deepcopy(workspace)}
        for view in graph['workspace']['views']: view['placements']=[]
        for variant in graph['workspace']['variants']: variant.update(active_node_gids=None,node_overrides={})
        result={'graph':graph,'complete':False,'revision':revision,'loaded_view_gids':[],'loaded_node_gids':[]}
        if projection=='directory': return result
        local=set()
        if projection=='view':
            selected=next((v for v in workspace['views'] if v['gid']==view_gid),None)
            if not selected: raise ValueError('workspace view missing')
            local={p['node_gid'] for p in selected['placements']}
            rollup_views=[]
            if selected['view_type']=='org':
                children={s['gid'] for s in workspace['scopes'] if s.get('parent_gid')==selected['scope_gid']}
                for child_view in workspace['views']:
                    if child_view['view_type']!='org' or child_view['scope_gid'] not in children:continue
                    placements=[deepcopy(p) for p in child_view['placements'] if extension.get('nodes',{}).get(p['node_gid'],{}).get('level',2)==1 and extension.get('nodes',{}).get(p['node_gid'],{}).get('home_scope_gid')==child_view['scope_gid']]
                    local.update(p['node_gid'] for p in placements)
                    rollup_views.append((child_view['gid'],placements))

            result['loaded_view_gids']=[view_gid]
            for v in graph['workspace']['views']:
                if v['gid']==view_gid:v.update(deepcopy(selected))
                for gid,placements in rollup_views:
                    if v['gid']==gid:v['placements']=placements
            # Restore selected task overrides from the authority, not the stripped directory.
            graph['workspace']['variants']=[deepcopy(next(a for a in workspace['variants'] if a['gid']==v['gid'])) if v['task_gid']==selected.get('task_gid') else v for v in graph['workspace']['variants']]
        else:
            if not node_gid: raise ValueError('node_gid required')
            local={node_gid}
        ids=set(local)
        if projection=='view' and local:
            marks=','.join(['%s']*len(local));values=tuple(sorted(local))
            cur.execute(f'SELECT gid,edge_type,source_node_gid,target_node_gid,label,route_points_json FROM workmanship_agent_orch_flow_edges WHERE version_gid=%s AND tenant_gid=%s AND project_gid<=>%s AND (source_node_gid IN ({marks}) OR target_node_gid IN ({marks})) ORDER BY created_at LIMIT 2001',(version_gid,tenant_gid,None,*values,*values))
            for row in cur.fetchall():
                if len(graph['edges'])>=2000:raise ValueError('edge bound exceeded')
                edge={k:row[k] for k in ('gid','edge_type','source_node_gid','target_node_gid','label')}
                edge['route_points']=_decoded(row.get('route_points_json'),[])
                edge.update(extension.get('edges',{}).get(row['gid'],{}));graph['edges'].append(edge)
                ids.update((edge['source_node_gid'],edge['target_node_gid']))
            for v in graph['workspace']['views']:
                if v['gid']!=view_gid:
                    original=next(a for a in workspace['views'] if a['gid']==v['gid'])
                    kept={p['node_gid'] for p in v['placements']}
                    v['placements'] += [deepcopy(p) for p in original['placements'] if p['node_gid'] in ids-local and p['node_gid'] not in kept]
        if not ids:return result
        if len(ids)>500:raise ValueError('node bound exceeded')
        marks=','.join(['%s']*len(ids));values=tuple(sorted(ids))
        detail=',objective,owner_ref,acceptance_json' if projection=='node' else ''
        cur.execute(f'SELECT gid,node_key,title,x_item_key,y_item_key,position_json,inputs_json,outputs_json{detail} FROM workmanship_agent_orch_business_nodes WHERE version_gid=%s AND tenant_gid=%s AND project_gid<=>%s AND gid IN ({marks}) ORDER BY created_at LIMIT 501',(version_gid,tenant_gid,None,*values))
        for row in cur.fetchall():
            node={k:row[k] for k in ('gid','node_key','title','x_item_key','y_item_key')}
            node.update(position=_decoded(row.get('position_json'),{'x':0,'y':0}),inputs=_decoded(row.get('inputs_json'),[]),outputs=_decoded(row.get('outputs_json'),[]),objective=row.get('objective') or '',owner_ref=row.get('owner_ref') or '',acceptance_criteria=_decoded(row.get('acceptance_json'),[]))
            node.update(extension.get('nodes',{}).get(row['gid'],{}))
            graph['nodes'].append(BusinessNode.model_validate(node).model_dump(mode='json'))
        if projection=='node':
            if not graph['nodes']:raise ResourceNotAccessible('node not accessible')
            result['loaded_node_gids']=[node_gid]
            cur.execute('SELECT gid,business_node_gid,item_type,title,sequence_no,config_json FROM workmanship_agent_orch_items WHERE version_gid=%s AND tenant_gid=%s AND project_gid<=>%s AND business_node_gid=%s ORDER BY sequence_no,gid LIMIT 2001',(version_gid,tenant_gid,None,node_gid))
            for row in cur.fetchall():
                item={k:row[k] for k in ('gid','business_node_gid','item_type','title','sequence_no')};item['config']=_decoded(row.get('config_json'),{});graph['items'].append(item)
            item_ids=tuple(i['gid'] for i in graph['items'])
            if len(item_ids)>2000:raise ValueError('item bound exceeded')
            if item_ids:
                imarks=','.join(['%s']*len(item_ids))
                cur.execute(f'SELECT gid,source_item_gid,capability_version_gid,purpose,input_mapping_json,output_mapping_json,authorization_scope_json,execution_policy_json,evidence_policy_json FROM workmanship_agent_orch_capability_bindings WHERE version_gid=%s AND tenant_gid=%s AND project_gid<=>%s AND source_item_gid IN ({imarks}) LIMIT 4001',(version_gid,tenant_gid,None,*item_ids))
                for row in cur.fetchall():
                    policy=_decoded(row.get('execution_policy_json'),{})
                    binding={k:row[k] for k in ('gid','source_item_gid','capability_version_gid','purpose')}
                    binding.update({k:_decoded(row.get(k+'_json'),{}) for k in ('input_mapping','output_mapping','authorization_scope','evidence_policy')})
                    binding.update(timeout_seconds=policy.get('timeout_seconds',30),retry_policy=policy.get('retry',{}),fallback_policy=policy.get('fallback',{}));graph['capability_bindings'].append(binding)
                cur.execute(f'SELECT gid,source_item_gid,ref_type,ref_gid,ref_version,snapshot_gid,purpose FROM workmanship_agent_orch_context_bindings WHERE version_gid=%s AND tenant_gid=%s AND project_gid<=>%s AND source_item_gid IN ({imarks}) LIMIT 4001',(version_gid,tenant_gid,None,*item_ids))
                graph['context_bindings']=list(cur.fetchall())
                if len(graph['capability_bindings'])>4000 or len(graph['context_bindings'])>4000:raise ValueError('binding bound exceeded')
        return result
